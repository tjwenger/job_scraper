"""
Discover Lever company slugs via search-engine dorking (site:jobs.lever.co).

Lever exposes no company directory, so we harvest slugs from DuckDuckGo's
HTML endpoint across many queries, validate each against the public API, and
(optionally) keep only boards that currently list VP/Director engineering
roles. Prints a ready-to-paste LEVER_COMPANIES list.

NOTE ON YIELD: DuckDuckGo's HTML endpoint returns only the first result page
and rate-limits (HTTP 202) after a burst, so a single run harvests only a
handful of slugs. For broader coverage, run this a few times spaced apart, or
seed it by pasting `site:jobs.lever.co ...` queries into a real search engine
and adding the resulting slugs. The committed LEVER_COMPANIES list was built
this way. The validate() step below is the reliable part — it confirms any
candidate slug and reports its open leadership-role count.

Run:  python scripts/discover_lever.py            # discover + validate
      python scripts/discover_lever.py --leadership # only boards w/ matching roles
      python scripts/discover_lever.py --merge       # merge into current scraper list
"""
import sys
import re
import time
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from config import KEYWORDS  # noqa: E402
from scrapers.lever_co import LEVER_COMPANIES as CURRENT  # noqa: E402

LEADERSHIP_ONLY = "--leadership" in sys.argv
MERGE = "--merge" in sys.argv

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Search queries — broad + role-specific to surface engineering-heavy boards.
QUERIES = [
    "site:jobs.lever.co",
    "site:jobs.lever.co engineering",
    "site:jobs.lever.co software",
    'site:jobs.lever.co "Director of Engineering"',
    'site:jobs.lever.co "VP of Engineering"',
    'site:jobs.lever.co "Vice President Engineering"',
    'site:jobs.lever.co "Head of Engineering"',
    "site:jobs.lever.co remote engineering",
    "site:jobs.lever.co platform",
    "site:jobs.lever.co backend",
    "site:jobs.lever.co infrastructure",
    "site:jobs.lever.co startup engineering leadership",
]

# Slugs that are Lever's own paths / not real company boards.
_SKIP = {"static", "img", "css", "js", "api", "www", "jobs", "postings"}


def harvest_slugs() -> set[str]:
    slugs: set[str] = set()
    headers = {"User-Agent": _UA, "Accept": "text/html"}
    with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as client:
        for q in QUERIES:
            try:
                r = client.post("https://html.duckduckgo.com/html/", data={"q": q})
                html = unquote(r.text)  # decode uddg= redirect links
                for m in re.findall(r"jobs\.lever\.co/([A-Za-z0-9\-]+)", html):
                    s = m.lower()
                    if s not in _SKIP and len(s) > 1:
                        slugs.add(s)
            except Exception as e:
                print(f"  ! query failed: {q!r} ({e})", file=sys.stderr)
            time.sleep(2.0)  # polite delay between searches
            print(f"  after {q!r}: {len(slugs)} unique slugs so far")
    return slugs


def validate(slugs: set[str]) -> list[tuple[str, int, int]]:
    """Return [(slug, total_jobs, leadership_jobs)] for boards that resolve."""
    kws = [k.lower() for k in KEYWORDS]
    headers = {"User-Agent": _UA, "Accept": "application/json"}
    out = []
    with httpx.Client(timeout=12, headers=headers) as client:
        for s in sorted(slugs):
            try:
                r = client.get(f"https://api.lever.co/v0/postings/{s}?mode=json")
                if r.status_code != 200:
                    continue
                posts = r.json()
                if not posts:
                    continue
                lead = sum(
                    1 for p in posts
                    if any(k in (p.get("text", "") or "").lower() for k in kws)
                )
                out.append((s, len(posts), lead))
            except Exception:
                pass
            time.sleep(0.05)
    return out


def main():
    print("Harvesting slugs from DuckDuckGo…")
    slugs = harvest_slugs()
    print(f"\n{len(slugs)} candidate slugs harvested. Validating against Lever API…\n")

    results = validate(slugs)
    results.sort(key=lambda t: (-t[2], -t[1]))

    print(f"{len(results)} live Lever boards:\n")
    print(f"  {'slug':28} {'jobs':>5} {'leadership':>10}")
    for s, total, lead in results:
        mark = " *" if lead else ""
        print(f"  {s:28} {total:>5} {lead:>10}{mark}")

    keep = [s for s, total, lead in results if (lead > 0 or not LEADERSHIP_ONLY)]
    if MERGE:
        keep = sorted(set(keep) | set(CURRENT))

    print(f"\n{'Merged' if MERGE else 'Discovered'} LEVER_COMPANIES "
          f"({'leadership-only' if LEADERSHIP_ONLY else 'all live'}): {len(keep)}\n")
    print("LEVER_COMPANIES = [")
    for s in keep:
        print(f'    "{s}",')
    print("]")


if __name__ == "__main__":
    main()
