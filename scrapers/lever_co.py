"""
Lever ATS scraper — uses Lever's public postings API.
Endpoint: https://api.lever.co/v0/postings/{slug}?mode=json

Add company slugs to LEVER_COMPANIES to expand coverage.
The slug matches the subdomain at jobs.lever.co/<slug>.

NOTE: the sibling file scrapers/lever.py is (confusingly) the Greenhouse
scraper — this module is the actual Lever integration.
"""
import httpx
import time
from datetime import datetime, timezone
from config import KEYWORDS, EXCLUDE_KEYWORDS, USER_AGENT

LEVER_COMPANIES = [
    # Consumer / Marketplace
    "spotify", "gopuff", "ro",
    # Data / Enterprise
    "palantir", "zoox",
    # Fintech
    "anchorage", "wealthfront",
    # Security
    "sysdig", "secureframe",
    # HR / Recruiting
    "15five", "findem",
    # Identity / Risk
    "alloy",
]

DELAY_SECONDS = 0.3


def _iso_from_ms(ms) -> str:
    """Lever createdAt is epoch milliseconds — convert to ISO date string."""
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return ""


def scrape_lever_co(keywords: list[str] | None = None) -> list[dict]:
    kws = [k.lower() for k in (keywords or KEYWORDS)]
    excl = [e.lower() for e in EXCLUDE_KEYWORDS]

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    jobs = []
    seen: set[str] = set()

    with httpx.Client(follow_redirects=True, timeout=15) as client:
        for slug in LEVER_COMPANIES:
            try:
                resp = client.get(
                    f"https://api.lever.co/v0/postings/{slug}?mode=json",
                    headers=headers,
                )
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                postings = resp.json()
            except Exception:
                time.sleep(DELAY_SECONDS)
                continue

            for post in postings:
                title = post.get("text", "")
                url = post.get("hostedUrl", "") or f"https://jobs.lever.co/{slug}/{post.get('id','')}"

                cats = post.get("categories") or {}
                location = cats.get("location", "") or ""
                all_locs = cats.get("allLocations") or []
                if not location and all_locs:
                    location = all_locs[0]
                department = cats.get("department", "") or ""
                team = cats.get("team", "") or ""
                commitment = cats.get("commitment", "") or ""

                workplace = (post.get("workplaceType") or "").lower()
                country = (post.get("country") or "").upper()
                body = post.get("descriptionPlain", "") or ""

                # Drop clearly-onsite roles at the source; the central gate does
                # the finer onsite/hybrid + software-role checks afterward.
                loc_lower = " ".join([location] + all_locs).lower()
                if workplace == "on-site" or workplace == "onsite":
                    if not any(r in loc_lower for r in ("remote", "anywhere")):
                        continue
                # US/remote scope — keep US, remote, or unspecified-country roles.
                if country and country not in ("US", "USA", ""):
                    if not any(r in loc_lower for r in ("remote", "anywhere", "united states")):
                        continue

                # Match keywords against title only (description matching causes
                # false positives like "reports to the Director of Engineering").
                title_lower = title.lower()
                if not any(kw in title_lower for kw in kws):
                    continue

                haystack = f"{title} {body[:1000]}".lower()
                if any(ex in haystack for ex in excl):
                    continue

                if url in seen:
                    continue
                seen.add(url)

                # Prepend structured category signals — department/team/workplace
                # help the central software-role and remote filters judge the job.
                prefix_bits = [b for b in [
                    f"Department: {department}" if department else "",
                    f"Team: {team}" if team else "",
                    f"Workplace: {workplace}" if workplace else "",
                    f"Commitment: {commitment}" if commitment else "",
                ] if b]
                prefix = (" | ".join(prefix_bits) + "\n\n") if prefix_bits else ""

                company = slug.replace("-", " ").title()
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location or ("Remote" if "remote" in workplace else ""),
                    "url": url,
                    "source": "lever",
                    "description": (prefix + body)[:2000],
                    "salary": "",
                    "posted_at": _iso_from_ms(post.get("createdAt")),
                })

            time.sleep(DELAY_SECONDS)

    return jobs
