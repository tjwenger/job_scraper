"""
Greenhouse ATS scraper — uses Greenhouse's public job board API.
Endpoint: https://boards-api.greenhouse.io/v1/boards/{company}/jobs

Most major tech companies use Greenhouse. The slug is the board token,
typically matching the company's subdomain on boards.greenhouse.io.
Add slugs to GREENHOUSE_COMPANIES to expand coverage.
"""
import re
import httpx
import time
from config import KEYWORDS, EXCLUDE_KEYWORDS, USER_AGENT

_US_STATE_RE = re.compile(
    r",\s*(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|"
    r"MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|"
    r"VT|VA|WA|WV|WI|WY|DC)\s*$",
    re.IGNORECASE,
)

GREENHOUSE_COMPANIES = [
    # AI / ML
    "anthropic", "imbue", "assemblyai",
    # Infrastructure / DevTools
    "vercel", "elastic", "mongodb", "cockroachlabs", "planetscale",
    "launchdarkly", "datadog", "encore", "gitlab",
    # Data / Analytics
    "databricks", "fivetran", "amplitude", "mixpanel",
    "hightouch", "algolia",
    # Payments / Fintech
    "stripe", "brex", "carta", "gusto", "mercury",
    "chime", "robinhood", "coinbase", "marqeta", "make",
    # Productivity / Collaboration
    "airtable", "figma", "airbnb", "instacart",
    # HR / People Ops
    "lattice", "okta",
    # Marketing / CX
    "braze", "klaviyo", "intercom", "contentful",
    # Other growth-stage tech
    "ironclad",
]

DELAY_SECONDS = 0.3


def scrape_lever(keywords: list[str] | None = None) -> list[dict]:
    """Scrapes Greenhouse ATS job boards for matching leadership roles."""
    kws = [k.lower() for k in (keywords or KEYWORDS)]
    excl = [e.lower() for e in EXCLUDE_KEYWORDS]

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    jobs = []
    seen: set[str] = set()

    with httpx.Client(follow_redirects=True, timeout=15) as client:
        for slug in GREENHOUSE_COMPANIES:
            try:
                resp = client.get(
                    f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
                    headers=headers,
                )
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                postings = resp.json().get("jobs", [])
            except Exception:
                time.sleep(DELAY_SECONDS)
                continue

            for post in postings:
                title = post.get("title", "")
                url = post.get("absolute_url", "") or f"https://boards.greenhouse.io/{slug}/jobs/{post.get('id','')}"
                description = post.get("content", "") or ""

                # Location — Greenhouse nests it under location.name
                location_obj = post.get("location") or {}
                location = location_obj.get("name", "") if isinstance(location_obj, dict) else ""

                # Remote / US filter — keep remote roles and US-based locations.
                loc_lower = location.lower()
                if loc_lower:
                    is_remote_or_us = (
                        any(r in loc_lower for r in (
                            "remote", "anywhere", "distributed", "worldwide",
                            "united states", "u.s.", "usa",
                        ))
                        or bool(_US_STATE_RE.search(location))  # "City, ST" pattern
                    )
                    if not is_remote_or_us:
                        continue

                # Match keywords against title only — description matching causes
                # false positives (e.g. "reports to Director of Engineering")
                title_lower = title.lower()
                if not any(kw in title_lower for kw in kws):
                    continue

                haystack = f"{title} {description}".lower()
                if any(ex in haystack for ex in excl):
                    continue
                if url in seen:
                    continue

                updated_at = post.get("updated_at", "")

                seen.add(url)
                jobs.append({
                    "title": title,
                    "company": slug.replace("-", " ").title(),
                    "location": location or "Remote",
                    "url": url,
                    "source": "greenhouse",
                    "description": description[:1000],
                    "salary": "",
                    "posted_at": updated_at,
                })

            time.sleep(DELAY_SECONDS)

    return jobs
