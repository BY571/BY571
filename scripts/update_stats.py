#!/usr/bin/env python3
"""Generate the profile cards from the GitHub API.

Writes assets/{stars,langs}-{light,dark}.svg. Stdlib only; needs GITHUB_TOKEN.
Replaces github-readme-stats.vercel.app and the shields.io/star-counter chain,
both of which cached wrong numbers and eventually went down entirely.

Only stars and languages are reported. Contribution counts (PRs, issues,
repositories contributed to) are deliberately left out: the Actions GITHUB_TOKEN
sees fewer of them than a user token, so they render lower than reality in CI.
"""

import json
import os
import pathlib
import sys
import urllib.request

LOGIN = os.environ.get("STATS_LOGIN", "BY571")
TOKEN = os.environ.get("GITHUB_TOKEN")
ASSETS = pathlib.Path(__file__).resolve().parent.parent / "assets"

# Languages excluded from the top-langs card. Jupyter Notebook is stored as JSON
# with embedded output, so byte counts overstate it by roughly an order of magnitude.
HIDE_LANGS = {s.strip() for s in os.environ.get("HIDE_LANGS", "Jupyter Notebook").split(",") if s.strip()}
TOP_N = 6

FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Helvetica, Arial, sans-serif"
WIDTH = 420
THEMES = {
    "light": {"title": "#2b2b2b", "text": "#4a4a4a", "muted": "#8a8a8a", "track": "#e5e3df"},
    "dark": {"title": "#e8e6e1", "text": "#c9c5be", "muted": "#8b8781", "track": "#2f2d2a"},
}

QUERY = """
query($login:String!, $cursor:String) {
  user(login:$login) {
    repositories(first:100, after:$cursor, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first:10, orderBy:{field:SIZE, direction:DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def graphql(**variables):
    body = json.dumps({"query": QUERY, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": f"{LOGIN}-profile-stats",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise RuntimeError(json.dumps(payload["errors"])[:2000])
    return payload["data"]["user"]


def collect():
    stars = 0
    languages = {}
    cursor = None
    repo_count = 0

    while True:
        repos = graphql(login=LOGIN, cursor=cursor)["repositories"]
        repo_count = repo_count or repos["totalCount"]
        for repo in repos["nodes"]:
            stars += repo["stargazerCount"]
            for edge in repo["languages"]["edges"]:
                name = edge["node"]["name"]
                if name in HIDE_LANGS:
                    continue
                entry = languages.setdefault(name, {"size": 0, "color": edge["node"]["color"] or "#858585"})
                entry["size"] += edge["size"]
        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]

    ranked = sorted(languages.items(), key=lambda kv: -kv[1]["size"])[:TOP_N]
    total = sum(entry["size"] for _, entry in ranked) or 1

    return {
        "stars": stars,
        "repos": repo_count,
        "languages": [
            {"name": name, "color": entry["color"], "pct": 100 * entry["size"] / total}
            for name, entry in ranked
        ],
    }


def esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def stars_svg(data, theme):
    c = THEMES[theme]
    caption = f'total stars across {data["repos"]} public repositories'
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="62" '
        f'viewBox="0 0 {WIDTH} 62" role="img" '
        f'aria-label="{data["stars"]:,} {caption}">',
        f'<style>text{{font-family:{FONT};}}</style>',
        f'<text x="0" y="38" fill="{c["title"]}" font-size="40" font-weight="600" '
        f'letter-spacing="-1">{data["stars"]:,}</text>',
        f'<text x="0" y="56" fill="{c["muted"]}" font-size="12">{esc(caption)}</text>',
        "</svg>",
    ])


def langs_svg(data, theme):
    c = THEMES[theme]
    langs = data["languages"]
    bar_y, bar_h = 46, 9
    legend_top, row_h, cols = 78, 23, 2
    height = legend_top + row_h * (-(-len(langs) // cols))

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}" role="img" aria-label="Most used languages">',
        f'<style>text{{font-family:{FONT};}}</style>',
        f'<text x="0" y="20" fill="{c["title"]}" font-size="16" font-weight="600">Most used languages</text>',
        f'<rect x="0" y="{bar_y}" width="{WIDTH}" height="{bar_h}" rx="{bar_h/2}" fill="{c["track"]}"/>',
        f'<clipPath id="bar"><rect x="0" y="{bar_y}" width="{WIDTH}" height="{bar_h}" rx="{bar_h/2}"/></clipPath>',
        '<g clip-path="url(#bar)">',
    ]
    x = 0.0
    for lang in langs:
        w = WIDTH * lang["pct"] / 100
        out.append(f'<rect x="{x:.2f}" y="{bar_y}" width="{w:.2f}" height="{bar_h}" fill="{lang["color"]}"/>')
        x += w
    out.append("</g>")

    col_w = WIDTH / cols
    for i, lang in enumerate(langs):
        cx = (i % cols) * col_w
        cy = legend_top + (i // cols) * row_h
        out.append(f'<circle cx="{cx + 5:.1f}" cy="{cy - 4}" r="5" fill="{lang["color"]}"/>')
        out.append(
            f'<text x="{cx + 17:.1f}" y="{cy}" fill="{c["text"]}" font-size="12">'
            f'{esc(lang["name"])} <tspan fill="{c["muted"]}">{lang["pct"]:.1f}%</tspan></text>'
        )
    out.append("</svg>")
    return "\n".join(out)


def main():
    if not TOKEN:
        sys.exit("GITHUB_TOKEN is not set")
    data = collect()
    ASSETS.mkdir(exist_ok=True)
    for theme in THEMES:
        (ASSETS / f"stars-{theme}.svg").write_text(stars_svg(data, theme) + "\n")
        (ASSETS / f"langs-{theme}.svg").write_text(langs_svg(data, theme) + "\n")
    print(f'{data["stars"]:,} stars across {data["repos"]} repositories')
    print("languages:", ", ".join(f"{l['name']} {l['pct']:.1f}%" for l in data["languages"]))


if __name__ == "__main__":
    main()
