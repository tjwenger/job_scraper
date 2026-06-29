"""
Indeed scraper — DISABLED.

Indeed blocks all programmatic access (403 + Cloudflare captcha on the jobs
endpoint; RSS and API endpoints return 404/429). Browser automation or a paid
proxy service (e.g. SerpAPI) would be required to scrape it reliably.
"""
from config import KEYWORDS, EXCLUDE_KEYWORDS, USER_AGENT, MAX_PAGES_PER_SOURCE


def scrape_indeed(keywords: list[str] | None = None) -> list[dict]:
    raise RuntimeError(
        "Indeed blocks automated scraping (403 + Cloudflare). "
        "Remove 'indeed' from ALL_SCRAPERS or integrate a paid proxy service to re-enable."
    )
