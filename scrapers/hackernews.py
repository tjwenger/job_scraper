"""
Hacker News 'Who is Hiring' — uses Algolia HN Search API.
Fetches the latest monthly thread and searches comments for keywords.
"""
import httpx
from datetime import datetime
from config import KEYWORDS, EXCLUDE_KEYWORDS, USER_AGENT


def _latest_hiring_thread_id() -> str | None:
    """Find the most recent 'Ask HN: Who is hiring' thread."""
    url = "https://hn.algolia.com/api/v1/search"
    params = {
        "query": "Ask HN: Who is hiring",
        "tags": "story,ask_hn",
        "hitsPerPage": 5,
    }
    resp = httpx.get(url, params=params, timeout=15)
    resp.raise_for_status()
    hits = resp.json().get("hits", [])
    # Pick thread from the current or most recent month
    now = datetime.utcnow()
    for hit in hits:
        title = hit.get("title", "")
        if "who is hiring" in title.lower():
            return hit.get("objectID")
    return hits[0].get("objectID") if hits else None


def scrape_hackernews(keywords: list[str] | None = None) -> list[dict]:
    kws = [k.lower() for k in (keywords or KEYWORDS)]
    excl = [e.lower() for e in EXCLUDE_KEYWORDS]

    thread_id = _latest_hiring_thread_id()
    if not thread_id:
        return []

    jobs = []
    page = 0
    while True:
        url = "https://hn.algolia.com/api/v1/search"
        params = {
            "tags": f"comment,story_{thread_id}",
            "hitsPerPage": 100,
            "page": page,
        }
        resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", [])
        if not hits:
            break

        for hit in hits:
            text = hit.get("comment_text", "") or ""
            haystack = text.lower()

            if not any(kw in haystack for kw in kws):
                continue
            if any(ex in haystack for ex in excl):
                continue
            if "remote" not in haystack:
                continue

            # Try to extract company | title from first line
            first_line = text.split("\n")[0].replace("<p>", "").strip()
            parts = first_line.split("|")
            company = parts[0].strip() if parts else "Unknown"
            title = parts[1].strip() if len(parts) > 1 else first_line[:80]

            obj_id = hit.get("objectID", "")
            jobs.append({
                "title": title,
                "company": company,
                "location": parts[2].strip() if len(parts) > 2 else "Unknown",
                "url": f"https://news.ycombinator.com/item?id={obj_id}",
                "source": "hackernews",
                "description": text[:1000],
                "salary": "",
                "posted_at": hit.get("created_at", ""),
            })

        if page >= data.get("nbPages", 1) - 1:
            break
        page += 1

    return jobs
