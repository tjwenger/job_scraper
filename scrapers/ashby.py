"""
Ashby ATS scraper — uses Ashby's public job board API.
Endpoint: https://api.ashbyhq.com/posting-api/job-board/{slug}

Add company slugs to ASHBY_COMPANIES to expand coverage.
The slug matches the subdomain at jobs.ashbyhq.com/<slug>.
"""
import httpx
import time
from config import KEYWORDS, EXCLUDE_KEYWORDS, USER_AGENT

ASHBY_COMPANIES = [
    # AI / ML
    "openai", "perplexity", "character", "anyscale", "modal",
    "midjourney", "runway", "deepgram", "cohere", "baseten",
    "langchain", "llamaindex", "vellum",
    # Dev Tools / Infrastructure
    "linear", "vercel", "railway", "depot", "neon", "supabase",
    "render", "inngest", "temporal", "sentry", "semgrep",
    # Data / Analytics
    "prefect", "airbyte", "confluent", "amplitude",
    # Fintech / Payments
    "mercury", "ramp", "deel", "plaid", "kraken", "marqeta", "zapier",
    # Productivity / Collaboration
    "notion", "loom", "miro", "superhuman", "n8n",
    # Security / Identity
    "1password", "snyk", "wiz", "workos",
    # Other growth-stage tech
    "posthog", "ashby", "benchling", "strava",
]

DELAY_SECONDS = 0.3


def scrape_ashby(keywords: list[str] | None = None) -> list[dict]:
    kws = [k.lower() for k in (keywords or KEYWORDS)]
    excl = [e.lower() for e in EXCLUDE_KEYWORDS]

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    jobs = []
    seen: set[str] = set()

    with httpx.Client(follow_redirects=True, timeout=15) as client:
        for slug in ASHBY_COMPANIES:
            try:
                resp = client.get(
                    f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
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
                if not post.get("isListed", True):
                    continue

                title = post.get("title", "")
                url = post.get("jobUrl", "") or f"https://jobs.ashbyhq.com/{slug}/{post.get('id','')}"
                location = post.get("location", "")
                workplace = post.get("workplaceType") or ""
                is_remote = post.get("isRemote", False)
                description = post.get("descriptionPlain", "") or ""
                published_at = post.get("publishedAt", "")

                # Drop non-remote roles
                loc_lower = location.lower()
                if workplace and workplace.lower() not in ("remote", "hybrid"):
                    pass  # allow hybrid — post-scrape filter will check description
                if not is_remote and workplace.lower() == "onsite":
                    continue
                if not is_remote and not any(r in loc_lower for r in (
                    "remote", "anywhere", "united states", "u.s.", "usa", "canada"
                )):
                    continue

                # Match keywords against title only
                title_lower = title.lower()
                if not any(kw in title_lower for kw in kws):
                    continue

                haystack = f"{title} {description[:1000]}".lower()
                if any(ex in haystack for ex in excl):
                    continue

                if url in seen:
                    continue
                seen.add(url)

                company = slug.replace("-", " ").title()
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location or ("Remote" if is_remote else ""),
                    "url": url,
                    "source": "ashby",
                    "description": description[:2000],
                    "salary": "",
                    "posted_at": published_at,
                })

            time.sleep(DELAY_SECONDS)

    return jobs
