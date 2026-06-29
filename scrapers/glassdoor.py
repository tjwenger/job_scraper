"""
Glassdoor scraper — Glassdoor is heavily protected by Cloudflare/bot detection.
This implementation uses their internal GraphQL-like API endpoint that some
clients hit. It may break if Glassdoor changes their API.

If this returns empty results, the most reliable alternative is to use
Glassdoor's official Job Alerts email feature manually, or a paid proxy service.
"""
import httpx
import json
from config import KEYWORDS, EXCLUDE_KEYWORDS, USER_AGENT, MAX_PAGES_PER_SOURCE


SEARCH_URL = "https://www.glassdoor.com/graph"


def scrape_glassdoor(keywords: list[str] | None = None) -> list[dict]:
    kws = keywords or KEYWORDS
    excl = [e.lower() for e in EXCLUDE_KEYWORDS]

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Referer": "https://www.glassdoor.com/Job/jobs.htm",
        "gd-csrf-token": "undefined",
    }

    jobs = []
    seen = set()

    # Use the most specific leadership terms first to stay within rate limits
    priority = [k for k in kws if any(t in k.lower() for t in ("vp", "vice president", "director"))]
    search_kws = (priority or kws)[:4]
    for keyword in search_kws:
        for page in range(1, MAX_PAGES_PER_SOURCE + 1):
            payload = [
                {
                    "operationName": "JobSearchResultsQuery",
                    "variables": {
                        "keyword": keyword,
                        "locationId": 1,  # United States
                        "numJobsToShow": 30,
                        "pageNumber": page,
                        "filterParams": [{"filterKey": "remoteWorkType", "values": "1"}],
                        "originalPageUrl": "https://www.glassdoor.com/Job/jobs.htm",
                        "seoFriendlyUrlInput": "",
                        "parameterUrlInput": "",
                        "seoUrl": False,
                    },
                    "query": (
                        "query JobSearchResultsQuery($keyword: String, $locationId: Int, "
                        "$numJobsToShow: Int, $pageNumber: Int, $filterParams: [FilterParams], "
                        "$originalPageUrl: String, $seoFriendlyUrlInput: String, "
                        "$parameterUrlInput: String, $seoUrl: Boolean) { "
                        "jobListings(contextHolder: {searchParams: {keyword: $keyword, "
                        "locationId: $locationId, numPerPage: $numJobsToShow, "
                        "pageNumber: $pageNumber, filterParams: $filterParams, "
                        "originalPageUrl: $originalPageUrl, "
                        "seoFriendlyUrlInput: $seoFriendlyUrlInput, "
                        "parameterUrlInput: $parameterUrlInput, seoUrl: $seoUrl}}) { "
                        "jobListings { jobview { header { jobTitleText employerNameFromSearch "
                        "locationName salarySource.salaryEstimate jobLink } } } } }"
                    ),
                }
            ]

            try:
                resp = httpx.post(
                    SEARCH_URL,
                    headers=headers,
                    json=payload,
                    timeout=20,
                    follow_redirects=True,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                # Glassdoor blocks frequently — silently skip rather than crash
                break

            try:
                listings = (
                    data[0]["data"]["jobListings"]["jobListings"]
                )
            except (KeyError, IndexError, TypeError):
                break

            if not listings:
                break

            for item in listings:
                header = item.get("jobview", {}).get("header", {})
                title = header.get("jobTitleText", "")
                company = header.get("employerNameFromSearch", "")
                location = header.get("locationName", "")
                link = header.get("jobLink", "")
                salary = str(header.get("salarySource.salaryEstimate") or "")

                if not link or link in seen:
                    continue
                url = f"https://www.glassdoor.com{link}" if link.startswith("/") else link

                haystack = f"{title} {company}".lower()
                if not any(k.lower() in haystack for k in kws):
                    continue
                if any(ex in haystack for ex in excl):
                    continue

                seen.add(link)
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "url": url,
                    "source": "glassdoor",
                    "description": "",
                    "salary": salary,
                    "posted_at": "",
                })

    return jobs
