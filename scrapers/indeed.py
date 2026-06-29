"""
Indeed scraper — uses requests + BeautifulSoup.
Note: Indeed has bot detection. This works for casual scraping but may
return empty results if blocked. Try rotating USER_AGENT in config.py
or adding delays if you see 403/captcha responses.
"""
import httpx
from bs4 import BeautifulSoup
import time
from config import KEYWORDS, EXCLUDE_KEYWORDS, USER_AGENT, MAX_PAGES_PER_SOURCE


BASE_URL = "https://www.indeed.com/jobs"


def _build_query(keywords: list[str]) -> str:
    # Use quoted phrases for multi-word terms; take top 8 to stay within URL limits
    return " OR ".join(f'"{k}"' if " " in k else k for k in keywords[:8])


def scrape_indeed(keywords: list[str] | None = None) -> list[dict]:
    kws = keywords or KEYWORDS
    excl = [e.lower() for e in EXCLUDE_KEYWORDS]
    query = _build_query(kws)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    jobs = []
    seen = set()

    for page in range(MAX_PAGES_PER_SOURCE):
        params = {"q": query, "start": page * 10, "sort": "date", "remotejob": "1"}
        try:
            resp = httpx.get(BASE_URL, params=params, headers=headers, timeout=20, follow_redirects=True)
            resp.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"Indeed page {page} failed: {e}")

        soup = BeautifulSoup(resp.text, "html.parser")

        # Indeed renders job cards with data-jk attribute
        cards = soup.select("div.job_seen_beacon, div[data-jk]")
        if not cards:
            # Fallback selector
            cards = soup.select("div.result")
        if not cards:
            break

        for card in cards:
            title_el = card.select_one("h2.jobTitle span, h2 a span")
            company_el = card.select_one("span.companyName, [data-testid='company-name']")
            location_el = card.select_one("div.companyLocation, [data-testid='text-location']")
            link_el = card.select_one("h2 a[href]")
            salary_el = card.select_one("div.salary-snippet-container, div.metadata.salary-snippet-container")
            desc_el = card.select_one("div.job-snippet")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else ""
            location = location_el.get_text(strip=True) if location_el else ""
            description = desc_el.get_text(strip=True) if desc_el else ""
            salary = salary_el.get_text(strip=True) if salary_el else ""

            href = link_el.get("href", "") if link_el else ""
            if href.startswith("/"):
                href = "https://www.indeed.com" + href
            if not href or href in seen:
                continue

            haystack = f"{title} {company} {description}".lower()
            if not any(k.lower() in haystack for k in kws):
                continue
            if any(ex in haystack for ex in excl):
                continue

            seen.add(href)
            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "url": href,
                "source": "indeed",
                "description": description,
                "salary": salary,
                "posted_at": "",
            })

        time.sleep(1.5)  # polite delay between pages

    return jobs
