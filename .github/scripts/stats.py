"""Lifetime GitHub stats card for the profile README.

Sums contributions for every year since the account was created, including
private and organization work (counts only: no repo names are written).
With the default Actions token, private work appears as a single
"private contributions" total. With a personal token in the METRICS_TOKEN
secret, private commits, PRs, issues and reviews are counted by type.
"""
import json, os, sys, urllib.request
from datetime import datetime, timezone

LOGIN = os.environ.get("LOGIN", "IamSupun")
TOKEN = os.environ["GH_TOKEN"]
OUT = sys.argv[1] if len(sys.argv) > 1 else "dist/stats.svg"
HIDE_LANGS = {"HTML", "CSS", "SCSS", "Less", "Jupyter Notebook", "Dockerfile", "Shell", "Makefile", "Procfile"}


def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json", "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    if data.get("errors"):
        print("GraphQL warnings:", json.dumps(data["errors"])[:800], file=sys.stderr)
    return data.get("data") or {}


user = gql("query($l:String!){user(login:$l){createdAt name}}", {"l": LOGIN})["user"]
created = datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
now = datetime.now(timezone.utc)

YEAR_Q = """query($l:String!,$f:DateTime!,$t:DateTime!){user(login:$l){contributionsCollection(from:$f,to:$t){
  totalCommitContributions totalPullRequestContributions totalIssueContributions
  totalPullRequestReviewContributions totalRepositoryContributions restrictedContributionsCount
  contributionCalendar{totalContributions}}}}"""

tot = dict(commits=0, prs=0, issues=0, reviews=0, repos=0, private=0, all=0)
last_year = 0
for year in range(created.year, now.year + 1):
    f = max(created, datetime(year, 1, 1, tzinfo=timezone.utc))
    t = min(now, datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc))
    c = gql(YEAR_Q, {"l": LOGIN, "f": f.isoformat(), "t": t.isoformat()})["user"]["contributionsCollection"]
    tot["commits"] += c["totalCommitContributions"]
    tot["prs"] += c["totalPullRequestContributions"]
    tot["issues"] += c["totalIssueContributions"]
    tot["reviews"] += c["totalPullRequestReviewContributions"]
    tot["repos"] += c["totalRepositoryContributions"]
    tot["private"] += c["restrictedContributionsCount"]
    tot["all"] += c["contributionCalendar"]["totalContributions"]

# rolling last 365 days
ly = gql("query($l:String!){user(login:$l){contributionsCollection{contributionCalendar{totalContributions}}}}", {"l": LOGIN})
last_year = ly["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"]

# repositories contributed to + languages across owned and contributed repos
REPO_FIELDS = "nameWithOwner isFork languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}"
repos, langs = {}, {}
for kind in ("repositories", "repositoriesContributedTo"):
    after = None
    while True:
        args = "first:100,after:$a,ownerAffiliations:[OWNER]" if kind == "repositories" else \
            "first:100,after:$a,includeUserRepositories:true,contributionTypes:[COMMIT,PULL_REQUEST,ISSUE,REPOSITORY,PULL_REQUEST_REVIEW]"
        d = gql(f"query($l:String!,$a:String){{user(login:$l){{{kind}({args}){{totalCount pageInfo{{hasNextPage endCursor}} nodes{{{REPO_FIELDS}}}}}}}}}",
                {"l": LOGIN, "a": after})
        conn = (d.get("user") or {}).get(kind)
        if not conn:
            break
        for n in conn["nodes"]:
            if n and not n["isFork"]:
                repos[n["nameWithOwner"]] = n
        if not conn["pageInfo"]["hasNextPage"]:
            break
        after = conn["pageInfo"]["endCursor"]
for n in repos.values():
    for e in n["languages"]["edges"]:
        name = e["node"]["name"]
        if name in HIDE_LANGS:
            continue
        cur = langs.setdefault(name, [0, e["node"]["color"] or "#8b949e"])
        cur[0] += e["size"]
top = sorted(langs.items(), key=lambda kv: -kv[1][0])[:6]
lang_total = sum(v[0] for _, v in top) or 1
years = now.year - created.year - (0 if (now.month, now.day) >= (created.month, created.day) else 1)


def fmt(n):
    return f"{n/1000:.1f}k".replace(".0k", "k") if n >= 10000 else f"{n:,}"


# ---------- SVG ----------
W, H = 840, 300
items = [
    ("Commits", tot["commits"], "#22d3ee", "M3 12h6m6 0h6M12 9a3 3 0 1 0 0 6a3 3 0 1 0 0-6"),
    ("Pull requests", tot["prs"], "#c084fc", "M6 3v12M6 15a3 3 0 1 0 0 6a3 3 0 1 0 0-6M6 3a3 3 0 1 0 0 0M18 21V9a3 3 0 0 0-3-3h-4M13 4l-2 2l2 2"),
    ("Issues", tot["issues"], "#f472b6", "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M12 8v5M12 16h.01"),
    ("Code reviews", tot["reviews"], "#22d3ee", "M2 12s4-7 10-7s10 7 10 7s-4 7-10 7S2 12 2 12M12 9a3 3 0 1 0 0 6a3 3 0 1 0 0-6"),
    ("Repos contributed to", len(repos), "#c084fc", "M4 4h12a2 2 0 0 1 2 2v14H6a2 2 0 0 1-2-2zM8 4v16"),
]
if tot["private"]:
    items.append(("Private &amp; org work", tot["private"], "#f472b6", "M6 11h12v10H6zM8 11V7a4 4 0 0 1 8 0v4"))
else:
    items.append(("New repositories", tot["repos"], "#f472b6", "M12 5v14M5 12h14"))

stat_svg = []
for i, (label, val, col, icon) in enumerate(items):
    x = 300 + (i % 3) * 180
    y = 92 + (i // 3) * 74
    stat_svg.append(f'''<g class="fade" style="animation-delay:{0.15*i+0.3:.2f}s" transform="translate({x},{y})">
      <path d="{icon}" fill="none" stroke="{col}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" transform="scale(.85)"/>
      <text x="28" y="16" class="num" fill="#f1f5f9">{fmt(val)}</text>
      <text x="0" y="40" class="lbl">{label}</text></g>''')

bar, bx = [], 40
legend = []
for i, (name, (size, color)) in enumerate(top):
    w = max(2, 760 * size / lang_total)
    bar.append(f'<rect x="{bx:.1f}" y="244" width="{w:.1f}" height="10" fill="{color}"/>')
    bx += w
    lx, ly2 = 40 + (i % 6) * 128, 278
    legend.append(f'<circle cx="{lx+5}" cy="{ly2-4}" r="5" fill="{color}"/><text x="{lx+16}" y="{ly2}" class="lg">{name} {100*size/lang_total:.1f}%</text>')

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
  <linearGradient id="g" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#22d3ee"/><stop offset=".5" stop-color="#c084fc"/><stop offset="1" stop-color="#f472b6"/></linearGradient>
  <filter id="glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <clipPath id="bar"><rect x="40" y="244" width="760" height="10" rx="5"/></clipPath>
  <style>
    text {{ font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif; }}
    .num {{ font-size: 24px; font-weight: 800; }}
    .lbl {{ font-size: 12.5px; fill: #94a3b8; letter-spacing: .5px; }}
    .lg {{ font-size: 12px; fill: #cbd5e1; }}
    .fade {{ opacity: 0; animation: in .6s ease-out forwards; }}
    @keyframes in {{ from {{ opacity: 0; transform: translateY(6px) }} to {{ opacity: 1 }} }}
    .ring {{ stroke-dasharray: 403; stroke-dashoffset: 403; animation: ring 1.6s ease-out .2s forwards; }}
    @keyframes ring {{ to {{ stroke-dashoffset: 0 }} }}
  </style>
</defs>
<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="14" fill="#0b0820" stroke="#7c3aed" stroke-width="1.5"/>
<text x="40" y="44" font-size="19" font-weight="700" fill="#c084fc">{(user.get("name") or LOGIN)}'s lifetime GitHub stats</text>
<text x="{W-40}" y="44" font-size="12" fill="#64748b" text-anchor="end">{years}+ years on GitHub · updated {now:%b %d, %Y}</text>
<g transform="translate(150,138)">
  <circle r="64" fill="none" stroke="#1e1b3a" stroke-width="10"/>
  <circle r="64" fill="none" stroke="url(#g)" stroke-width="10" stroke-linecap="round" class="ring" transform="rotate(-90)" filter="url(#glow)"/>
  <text y="6" text-anchor="middle" font-size="30" font-weight="800" fill="#f1f5f9">{fmt(tot["all"])}</text>
  <text y="26" text-anchor="middle" font-size="11" fill="#94a3b8">total contributions</text>
  <text y="88" text-anchor="middle" font-size="12" font-weight="600" fill="#22d3ee">{fmt(last_year)} in the last year</text>
</g>
{''.join(stat_svg)}
<g clip-path="url(#bar)"><rect x="40" y="244" width="760" height="10" fill="#1e1b3a"/>{''.join(bar)}</g>
{''.join(legend)}
</svg>'''

os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
open(OUT, "w").write(svg)
print(json.dumps({**tot, "last_year": last_year, "repos_contributed": len(repos), "langs": [t[0] for t in top]}))
