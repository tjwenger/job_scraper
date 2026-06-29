"""We Work Remotely — RSS feeds per category."""
import feedparser
from config import KEYWORDS, EXCLUDE_KEYWORDS

FEEDS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    "https://weworkremotely.com/categories/remote-data-science-jobs.rss",
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
    "https://weworkremotely.com/remote-jobs.rss",
]


def scrape_wwr(keywords: list[str] | None = None) -> list[dict]:
    kws = [k.lower() for k in (keywords or KEYWORDS)]
    excl = [e.lower() for e in EXCLUDE_KEYWORDS]
    jobs = []
    seen = set()

    for feed_url in FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            url = entry.get("link", "")
            if not url or url in seen:
                continue

            title = entry.get("title", "")
            summary = entry.get("summary", "")
            haystack = f"{title} {summary}".lower()

            if not any(kw in haystack for kw in kws):
                continue
            if any(ex in haystack for ex in excl):
                continue

            seen.add(url)
            # WWR title format: "Company: Job Title at Location"
            parts = title.split(":", 1)
            company = parts[0].strip() if len(parts) > 1 else ""
            clean_title = parts[1].strip() if len(parts) > 1 else title

            jobs.append({
                "title": clean_title,
                "company": company,
                "location": "Remote",
                "url": url,
                "source": "weworkremotely",
                "description": summary[:1000],
                "salary": "",
                "posted_at": entry.get("published", ""),
            })

    return jobs
