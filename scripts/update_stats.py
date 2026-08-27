#!/usr/bin/env python3
"""Generate the profile stat cards from the GitHub API.

Writes assets/{stats,langs}-{light,dark}.svg. Stdlib only; needs GITHUB_TOKEN.
Replaces github-readme-stats.vercel.app and the shields.io/star-counter chain,
both of which cached wrong numbers and eventually went down entirely.
"""

import datetime
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

LOGIN = os.environ.get("STATS_LOGIN", "BY571")
TOKEN = os.environ.get("GITHUB_TOKEN")
ASSETS = pathlib.Path(__file__).resolve().parent.parent / "assets"

# Languages excluded from the top-langs card. Jupyter Notebook is stored as JSON
# with embedded output, so byte counts overstate it by roughly an order of magnitude.
HIDE_LANGS = {s.strip() for s in os.environ.get("HIDE_LANGS", "Jupyter Notebook").split(",") if s.strip()}
TOP_N = 6

FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Helvetica, Arial, sans-serif"
THEMES = {
    "light": {"title": "#2b2b2b", "text": "#4a4a4a", "muted": "#8a8a8a", "track": "#e5e3df"},
    "dark": {"title": "#e8e6e1", "text": "#c9c5be", "muted": "#8b8781", "track": "#2f2d2a"},
}


def graphql(query, **variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
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
    return payload["data"]


REPOS_QUERY = """
query($login:String!, $cursor:String) {
  user(login:$login) {
    createdAt
    repositories(first:100, after:$cursor, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        forkCount
        languages(first:10, orderBy:{field:SIZE, direction:DESC}) {
          edges { size node { name color } }
        }
      }
    }
    pullRequests(states:[OPEN,CLOSED,MERGED]) { totalCount }
    issues { totalCount }
    repositoriesContributedTo(first:1, contributionTypes:[COMMIT,ISSUE,PULL_REQUEST,REPOSITORY]) { totalCount }
  }
}
"""

COMMITS_QUERY = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) {
    contributionsCollection(from:$from, to:$to) { totalCommitContributions }
  }
}
"""


def collect():
    stars = forks = 0
    languages = {}
    cursor = None
    head = None

    while True:
        user = graphql(REPOS_QUERY, login=LOGIN, cursor=cursor)["user"]
        head = head or user
        repos = user["repositories"]
        for repo in repos["nodes"]:
            stars += repo["stargazerCount"]
            forks += repo["forkCount"]
            for edge in repo["languages"]["edges"]:
                name = edge["node"]["name"]
                if name in HIDE_LANGS:
                    continue
                entry = languages.setdefault(name, {"size": 0, "color": edge["node"]["color"] or "#858585"})
                entry["size"] += edge["size"]
        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]

    # contributionsCollection caps at one year per call, so walk year by year.
    commits = 0
    for year in range(int(head["createdAt"][:4]), datetime.date.today().year + 1):
        data = graphql(
            COMMITS_QUERY,
            login=LOGIN,
            **{"from": f"{year}-01-01T00:00:00Z", "to": f"{year}-12-31T23:59:59Z"},
        )
        commits += data["user"]["contributionsCollection"]["totalCommitContributions"]

    ranked = sorted(languages.items(), key=lambda kv: -kv[1]["size"])[:TOP_N]
    total = sum(entry["size"] for _, entry in ranked) or 1

    return {
        "stars": stars,
        "forks": forks,
        "repos": head["repositories"]["totalCount"],
        "prs": head["pullRequests"]["totalCount"],
        "issues": head["issues"]["totalCount"],
        "contributed": head["repositoriesContributedTo"]["totalCount"],
        "commits": commits,
        "languages": [
            {"name": name, "color": entry["color"], "pct": 100 * entry["size"] / total}
            for name, entry in ranked
        ],
    }


def esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def stats_svg(data, theme):
    c = THEMES[theme]
    rows = [
        ("Total stars earned", data["stars"]),
        ("Total forks", data["forks"]),
        ("Public repositories", data["repos"]),
        ("Total commits", data["commits"]),
        ("Total pull requests", data["prs"]),
        ("Total issues", data["issues"]),
        ("Contributed to", data["contributed"]),
    ]
    width, top, step = 420, 62, 25
    height = top + step * len(rows) + 6

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{esc(LOGIN)} GitHub statistics">',
        f'<style>text{{font-family:{FONT};}}</style>',
        f'<text x="0" y="20" fill="{c["title"]}" font-size="16" font-weight="600">'
        f'{esc(LOGIN)}&#8217;s GitHub stats</text>',
        f'<line x1="0" y1="36" x2="{width}" y2="36" stroke="{c["track"]}" stroke-width="1"/>',
    ]
    for i, (label, value) in enumerate(rows):
        y = top + i * step
        out.append(f'<text x="0" y="{y}" fill="{c["text"]}" font-size="13">{esc(label)}</text>')
        out.append(
            f'<text x="{width}" y="{y}" fill="{c["title"]}" font-size="13" '
            f'font-weight="600" text-anchor="end">{value:,}</text>'
        )
    out.append("</svg>")
    return "\n".join(out)


def langs_svg(data, theme):
    c = THEMES[theme]
    langs = data["languages"]
    width, bar_y, bar_h = 420, 46, 9
    legend_top, row_h, cols = 78, 23, 2
    rows = -(-len(langs) // cols)
    height = legend_top + row_h * rows

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="Most used languages">',
        f'<style>text{{font-family:{FONT};}}</style>',
        f'<text x="0" y="20" fill="{c["title"]}" font-size="16" font-weight="600">Most used languages</text>',
        f'<rect x="0" y="{bar_y}" width="{width}" height="{bar_h}" rx="{bar_h/2}" fill="{c["track"]}"/>',
        f'<clipPath id="bar"><rect x="0" y="{bar_y}" width="{width}" height="{bar_h}" rx="{bar_h/2}"/></clipPath>',
        '<g clip-path="url(#bar)">',
    ]
    x = 0.0
    for lang in langs:
        w = width * lang["pct"] / 100
        out.append(f'<rect x="{x:.2f}" y="{bar_y}" width="{w:.2f}" height="{bar_h}" fill="{lang["color"]}"/>')
        x += w
    out.append("</g>")

    col_w = width / cols
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
        (ASSETS / f"stats-{theme}.svg").write_text(stats_svg(data, theme) + "\n")
        (ASSETS / f"langs-{theme}.svg").write_text(langs_svg(data, theme) + "\n")
    print(json.dumps({k: v for k, v in data.items() if k != "languages"}, indent=2))
    print("languages:", ", ".join(f"{l['name']} {l['pct']:.1f}%" for l in data["languages"]))


if __name__ == "__main__":
    main()
