#!/usr/bin/env python3
"""Build the profile's stat cards from GitHub data. Standard library only.

Writes assets/<card>-{dark,light}.svg. Needs GITHUB_TOKEN (read-only is enough).
"""
import base64
import datetime as dt
import json
import math
import os
import urllib.request
from collections import Counter, defaultdict
from xml.sax.saxutils import escape

USER = os.environ.get("STATS_USER", "officialasishkumar")
TOKEN = os.environ["GITHUB_TOKEN"]
OUT = os.path.join(os.path.dirname(__file__), "..", "assets")

THEMES = {
    "dark": dict(bg="#0d1117", card="#161b22", border="#30363d", text="#e6edf3",
                 muted="#8b949e", accent="#4f8cff", accent2="#22c55e", track="#21262d"),
    "light": dict(bg="#ffffff", card="#f6f8fa", border="#d0d7de", text="#1f2328",
                  muted="#59636e", accent="#2563eb", accent2="#16a34a", track="#eaeef2"),
}
FONT = "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"


def gql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": USER},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if body.get("errors"):
        raise SystemExit(body["errors"])
    return body["data"]


SEARCH = """
query($q: String!, $after: String) {
  search(query: $q, type: ISSUE, first: 100, after: $after) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes { ... on PullRequest {
      url mergedAt
      repository { nameWithOwner stargazerCount owner { login } primaryLanguage { name color } }
    } }
  }
}"""


def merged_prs():
    """All merged PRs into repos USER doesn't own. Sliced by year to stay under the 1000-result cap."""
    seen, prs = set(), []
    for year in range(2019, dt.date.today().year + 1):
        q = f"is:pr is:merged author:{USER} -user:{USER} created:{year}-01-01..{year}-12-31"
        after = None
        while True:
            s = gql(SEARCH, q=q, after=after)["search"]
            for n in s["nodes"]:
                if n and n["url"] not in seen:
                    seen.add(n["url"])
                    prs.append(n)
            if not s["pageInfo"]["hasNextPage"]:
                break
            after = s["pageInfo"]["endCursor"]
    return prs


def avatar(login):
    try:
        req = urllib.request.Request(f"https://github.com/{login}.png?size=48", headers={"User-Agent": USER})
        with urllib.request.urlopen(req, timeout=30) as r:
            return "data:image/png;base64," + base64.b64encode(r.read()).decode()
    except Exception:
        return None


def human(n):
    for div, suffix in ((1_000_000, "M"), (1_000, "k")):
        if n >= div:
            return f"{n/div:.1f}".rstrip("0").rstrip(".") + suffix
    return str(n)


def svg(w, h, t, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{escape(title)}"><title>{escape(title)}</title>'
            f'<style>text{{{FONT}}}</style>'
            f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="12" fill="{t["card"]}" stroke="{t["border"]}"/>'
            f'{body}</svg>')


def card_tiles(t, tiles):
    w, h = 840, 110
    cw = (w - 40) / len(tiles)
    body = ""
    for i, (value, label, color) in enumerate(tiles):
        x = 20 + i * cw + cw / 2
        if i:
            body += f'<line x1="{20+i*cw}" y1="26" x2="{20+i*cw}" y2="{h-26}" stroke="{t["border"]}"/>'
        body += (f'<text x="{x}" y="58" text-anchor="middle" font-size="32" font-weight="700" fill="{t[color]}">{value}</text>'
                 f'<text x="{x}" y="84" text-anchor="middle" font-size="13" fill="{t["muted"]}">{escape(label)}</text>')
    return svg(w, h, t, body, "Open source stats")


def card_orgs(t, orgs, avatars):
    w, rowh = 412, 30
    h = 56 + rowh * len(orgs) + 10
    top = orgs[0][1]
    body = f'<text x="20" y="34" font-size="15" font-weight="600" fill="{t["text"]}">Top orgs by merged PRs</text>'
    for i, (org, n) in enumerate(orgs):
        y = 56 + i * rowh
        img = avatars.get(org)
        if img:
            body += (f'<clipPath id="c{i}"><rect x="20" y="{y}" width="20" height="20" rx="5"/></clipPath>'
                     f'<image href="{img}" x="20" y="{y}" width="20" height="20" clip-path="url(#c{i})"/>')
        body += f'<text x="48" y="{y+15}" font-size="13" fill="{t["text"]}">{escape(org[:18])}</text>'
        bx, bw = 180, 170
        body += f'<rect x="{bx}" y="{y+5}" width="{bw}" height="10" rx="5" fill="{t["track"]}"/>'
        body += f'<rect x="{bx}" y="{y+5}" width="{max(6, bw*n/top):.1f}" height="10" rx="5" fill="{t["accent"]}"/>'
        body += f'<text x="{w-20}" y="{y+15}" text-anchor="end" font-size="13" font-weight="600" fill="{t["text"]}">{n}</text>'
    return svg(w, h, t, body, "Top orgs by merged PRs")


def card_langs(t, langs, height):
    w, h = 412, height
    total = sum(n for _, n, _ in langs)
    cx, cy, r, sw = 110, 56 + (h - 56) / 2 - 6, 64, 22
    body = f'<text x="20" y="34" font-size="15" font-weight="600" fill="{t["text"]}">Merged PRs by language</text>'
    a0 = -math.pi / 2
    for name, n, color in langs:
        a1 = a0 + 2 * math.pi * n / total
        large = 1 if a1 - a0 > math.pi else 0
        x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
        x1, y1 = cx + r * math.cos(a1 - 0.012), cy + r * math.sin(a1 - 0.012)
        body += (f'<path d="M{x0:.2f},{y0:.2f} A{r},{r} 0 {large} 1 {x1:.2f},{y1:.2f}" fill="none" '
                 f'stroke="{color}" stroke-width="{sw}"/>')
        a0 = a1
    body += (f'<text x="{cx}" y="{cy+2}" text-anchor="middle" font-size="24" font-weight="700" fill="{t["text"]}">{total}</text>'
             f'<text x="{cx}" y="{cy+20}" text-anchor="middle" font-size="11" fill="{t["muted"]}">merged</text>')
    ly = cy - (len(langs) * 24) / 2 + 8
    for i, (name, n, color) in enumerate(langs):
        y = ly + i * 24
        body += (f'<rect x="215" y="{y-9}" width="10" height="10" rx="3" fill="{color}"/>'
                 f'<text x="233" y="{y}" font-size="13" fill="{t["text"]}">{escape(name)}</text>'
                 f'<text x="{w-20}" y="{y}" text-anchor="end" font-size="13" fill="{t["muted"]}">{100*n/total:.0f}%</text>')
    return svg(w, h, t, body, "Merged PRs by language")


def card_activity(t, months):
    w, h = 840, 200
    top = max(n for _, n in months) or 1
    body = f'<text x="20" y="34" font-size="15" font-weight="600" fill="{t["text"]}">Merged PRs per month</text>'
    body += f'<text x="{w-20}" y="34" text-anchor="end" font-size="12" fill="{t["muted"]}">last 12 months</text>'
    slot = (w - 40) / len(months)
    base, maxh = h - 34, h - 100
    for i, (label, n) in enumerate(months):
        bh = max(3, maxh * n / top)
        x = 20 + i * slot + slot * 0.2
        body += f'<rect x="{x:.1f}" y="{base-bh:.1f}" width="{slot*0.6:.1f}" height="{bh:.1f}" rx="5" fill="{t["accent"]}" opacity="{0.45 + 0.55*n/top:.2f}"/>'
        body += f'<text x="{x+slot*0.3:.1f}" y="{base-bh-7:.1f}" text-anchor="middle" font-size="12" font-weight="600" fill="{t["text"]}">{n}</text>'
        body += f'<text x="{x+slot*0.3:.1f}" y="{h-14}" text-anchor="middle" font-size="12" fill="{t["muted"]}">{label}</text>'
    return svg(w, h, t, body, "Merged PRs per month")


def main():
    prs = merged_prs()
    repos = {p["repository"]["nameWithOwner"]: p["repository"] for p in prs}
    orgs = Counter(p["repository"]["owner"]["login"] for p in prs)
    stars = sum(r["stargazerCount"] for r in repos.values())

    lang_n, lang_color = Counter(), {}
    for p in prs:
        lang = p["repository"]["primaryLanguage"]
        if lang:
            lang_n[lang["name"]] += 1
            lang_color[lang["name"]] = lang["color"] or "#8b949e"
    top_langs = lang_n.most_common(6)
    other = len(prs) - sum(n for _, n in top_langs)
    langs = [(k, n, lang_color[k]) for k, n in top_langs] + ([("Other", other, "#8b949e")] if other else [])

    today = dt.date.today()
    per_month = defaultdict(int)
    for p in prs:
        per_month[p["mergedAt"][:7]] += 1
    months = []
    for back in range(11, -1, -1):
        y, m = today.year, today.month - back
        while m <= 0:
            y, m = y - 1, m + 12
        months.append((dt.date(y, m, 1).strftime("%b"), per_month[f"{y}-{m:02d}"]))
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)).isoformat()
    last30 = sum(1 for p in prs if p["mergedAt"] >= cutoff)

    top_orgs = orgs.most_common(8)
    avatars = {o: avatar(o) for o, _ in top_orgs}
    orgs_h = 56 + 30 * len(top_orgs) + 10
    tiles = [(human(len(prs)), "PRs merged", "accent"), (human(len(repos)), "projects", "text"),
             (human(len(orgs)), "orgs", "text"), (human(stars), "stars on those projects", "text"),
             (str(last30), "merged in last 30 days", "accent2")]

    os.makedirs(OUT, exist_ok=True)
    for name, t in THEMES.items():
        for card, content in (("stats", card_tiles(t, tiles)), ("orgs", card_orgs(t, top_orgs, avatars)),
                              ("languages", card_langs(t, langs, orgs_h)), ("activity", card_activity(t, months))):
            with open(os.path.join(OUT, f"{card}-{name}.svg"), "w") as f:
                f.write(content)
    print(f"{len(prs)} merged, {len(repos)} repos, {len(orgs)} orgs, {stars} stars, {last30} last 30d")


if __name__ == "__main__":
    main()
