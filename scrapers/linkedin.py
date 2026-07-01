"""
LinkedIn — uses the public guest jobs API (no login required).
Endpoint: linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
Detail:   linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}

f_TPR=r2592000 restricts results to the last 30 days (2592000 seconds).
f_WT=2 (remote filter) is intentionally omitted — we fetch each job's full
description and filter out on-site/hybrid roles ourselves so we don't miss
jobs that are remote but not tagged as such by the poster.

LinkedIn will rate-limit aggressive scrapers; the per-keyword delay below
keeps it polite. If you start seeing empty responses, increase DELAY_SECONDS.
"""
import re
import time
import httpx
from bs4 import BeautifulSoup
from config import KEYWORDS, EXCLUDE_KEYWORDS, USER_AGENT, MAX_PAGES_PER_SOURCE

BASE_URL    = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL  = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
RESULTS_PER_PAGE = 25
DELAY_SECONDS    = 2.0

# Onsite/hybrid filtering lives in scrapers/filters.py (shared with the
# scheduler) so every source applies the exact same positive-remote gate.
from .filters import is_remote_ok

# Deduplicate by grouping similar keywords so we don't hammer LinkedIn
# with 20 separate queries. We pick the most distinct search terms.
PRIORITY_TERMS = [
    "VP of Engineering",
    "Vice President Engineering",
    "Director of Engineering",
    "Senior Director of Engineering",
    "Senior Director Engineering",
    "VP Technology",
    "Director of Technology",
    "VP Software Engineering",
    "Director of Software Engineering",
]

_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.linkedin.com/jobs/search/",
}


def _job_id_from_url(url: str) -> str | None:
    """Extract numeric job ID from a LinkedIn jobs/view URL.

    URLs are slug-based — the numeric ID is the trailing run of digits, e.g.
    /jobs/view/director-of-engineering-at-ideal-aerosmith-inc-4431764370
    """
    m = re.search(r"(\d{6,})(?:[/?#]|$)", url)
    return m.group(1) if m else None


def _fetch_description(job_id: str, client: httpx.Client) -> str:
    """Fetch full job description HTML from the detail endpoint. Returns empty string on failure."""
    try:
        resp = client.get(
            DETAIL_URL.format(job_id=job_id),
            headers=_HEADERS,
            timeout=20,
        )
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        desc_el = soup.select_one(".description__text, .show-more-less-html__markup")
        return desc_el.get_text(" ", strip=True) if desc_el else soup.get_text(" ", strip=True)
    except Exception:
        return ""


def _search(keyword: str, start: int, client: httpx.Client) -> list[dict]:
    params = {
        "keywords": keyword,
        "location": "United States",
        "f_TPR": "r2592000",  # last 30 days
        "f_TP":  "1,2",       # full-time + part-time (excludes contract noise)
        "start": start,
    }

    try:
        resp = client.get(BASE_URL, params=params, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            raise RuntimeError("LinkedIn rate limit hit — try again later or increase DELAY_SECONDS")
        raise RuntimeError(f"LinkedIn request failed ({e.response.status_code})")
    except Exception as e:
        raise RuntimeError(f"LinkedIn request error: {e}")

    soup = BeautifulSoup(resp.text, "html.parser")
    jobs = []

    for card in soup.select("li"):
        title_el    = card.select_one(".base-search-card__title")
        company_el  = card.select_one(".base-search-card__subtitle")
        location_el = card.select_one(".job-search-card__location")
        link_el     = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
        time_el     = card.select_one("time[datetime]")

        if not title_el or not link_el:
            continue

        url = link_el.get("href", "").split("?")[0]  # strip tracking params
        if not url:
            continue

        jobs.append({
            "title":     title_el.get_text(strip=True),
            "company":   company_el.get_text(strip=True) if company_el else "",
            "location":  location_el.get_text(strip=True) if location_el else "",
            "url":       url,
            "source":    "linkedin",
            "description": "",
            "salary":    "",
            "posted_at": time_el.get("datetime", "") if time_el else "",
        })

    return jobs


def scrape_linkedin(keywords: list[str] | None = None) -> list[dict]:
    kws  = keywords or KEYWORDS
    excl = [e.lower() for e in EXCLUDE_KEYWORDS]
    search_terms = keywords if keywords else PRIORITY_TERMS

    seen: set[str] = set()
    candidates: list[dict] = []

    with httpx.Client(follow_redirects=True) as client:
        # --- Pass 1: collect matching job cards ---
        for term in search_terms:
            for page in range(MAX_PAGES_PER_SOURCE):
                start = page * RESULTS_PER_PAGE
                try:
                    batch = _search(term, start, client)
                except RuntimeError as e:
                    import logging
                    logging.getLogger(__name__).warning(str(e))
                    break

                if not batch:
                    break

                for job in batch:
                    if job["url"] in seen:
                        continue
                    haystack = f"{job['title']} {job['company']}".lower()
                    if not any(kw.lower() in haystack for kw in kws):
                        continue
                    if any(ex in haystack for ex in excl):
                        continue
                    seen.add(job["url"])
                    candidates.append(job)

                if len(batch) < RESULTS_PER_PAGE:
                    break

                time.sleep(DELAY_SECONDS)

            time.sleep(DELAY_SECONDS)

        # --- Pass 2: fetch descriptions and filter on-site/hybrid roles ---
        all_jobs: list[dict] = []
        for job in candidates:
            job_id = _job_id_from_url(job["url"])
            if job_id:
                description = _fetch_description(job_id, client)
                time.sleep(DELAY_SECONDS)
            else:
                description = ""

            job["description"] = description[:2000]

            # Positive-remote gate — keep only genuinely remote-eligible roles.
            if not is_remote_ok(job):
                continue

            all_jobs.append(job)

    return all_jobs
