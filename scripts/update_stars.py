#!/usr/bin/env python3
"""Generate the total-stars card for the profile README.

Writes assets/stars-{light,dark}.svg. Stdlib only; needs GITHUB_TOKEN.
Replaces github-readme-stats.vercel.app and the shields.io/star-counter chain,
both of which cached wrong numbers and eventually went down entirely.
"""

import json
import os
import pathlib
import sys
import urllib.request

LOGIN = os.environ.get("STATS_LOGIN", "BY571")
TOKEN = os.environ.get("GITHUB_TOKEN")
ASSETS = pathlib.Path(__file__).resolve().parent.parent / "assets"

FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Helvetica, Arial, sans-serif"
WIDTH = 420
THEMES = {
    "light": {"title": "#2b2b2b", "muted": "#8a8a8a"},
    "dark": {"title": "#e8e6e1", "muted": "#8b8781"},
}

QUERY = """
query($login:String!, $cursor:String) {
  user(login:$login) {
    repositories(first:100, after:$cursor, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes { stargazerCount }
    }
  }
}
"""


def graphql(**variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": f"{LOGIN}-profile-stars",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise RuntimeError(json.dumps(payload["errors"])[:2000])
    return payload["data"]["user"]["repositories"]


def collect():
    stars, count, cursor = 0, 0, None
    while True:
        repos = graphql(login=LOGIN, cursor=cursor)
        count = count or repos["totalCount"]
        stars += sum(r["stargazerCount"] for r in repos["nodes"])
        if not repos["pageInfo"]["hasNextPage"]:
            return stars, count
        cursor = repos["pageInfo"]["endCursor"]


def render(stars, repos, theme):
    c = THEMES[theme]
    caption = f"total stars across {repos} public repositories"
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="62" '
        f'viewBox="0 0 {WIDTH} 62" role="img" aria-label="{stars:,} {caption}">',
        f"<style>text{{font-family:{FONT};}}</style>",
        f'<text x="{WIDTH/2}" y="38" fill="{c["title"]}" font-size="40" font-weight="600" '
        f'letter-spacing="-1" text-anchor="middle">{stars:,}</text>',
        f'<text x="{WIDTH/2}" y="56" fill="{c["muted"]}" font-size="12" '
        f'text-anchor="middle">{caption}</text>',
        "</svg>",
    ])


def main():
    if not TOKEN:
        sys.exit("GITHUB_TOKEN is not set")
    stars, repos = collect()
    ASSETS.mkdir(exist_ok=True)
    for theme in THEMES:
        (ASSETS / f"stars-{theme}.svg").write_text(render(stars, repos, theme) + "\n")
    print(f"{stars:,} stars across {repos} repositories")


if __name__ == "__main__":
    main()
