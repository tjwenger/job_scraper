"""RemoteOK — public JSON API, no auth required."""
import httpx
from config import KEYWORDS, EXCLUDE_KEYWORDS, USER_AGENT


def scrape_remoteok(keywords: list[str] | None = None) -> list[dict]:
    kws = [k.lower() for k in (keywords or KEYWORDS)]
    excl = [e.lower() for e in EXCLUDE_KEYWORDS]

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    jobs = []

    try:
        resp = httpx.get("https://remoteok.com/api", headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"RemoteOK fetch failed: {e}")

    for item in data:
        if not isinstance(item, dict) or "position" not in item:
            continue

        title = item.get("position", "")
        company = item.get("company", "")
        description = item.get("description", "")
        tags = " ".join(item.get("tags") or [])
        haystack = f"{title} {company} {description} {tags}".lower()

        if not any(kw in haystack for kw in kws):
            continue
        if any(ex in haystack for ex in excl):
            continue

        jobs.append({
            "title": title,
            "company": company,
            "location": "Remote",
            "url": item.get("url") or f"https://remoteok.com/remote-jobs/{item.get('id', '')}",
            "source": "remoteok",
            "description": description[:1000],
            "salary": item.get("salary", ""),
            "posted_at": item.get("date", ""),
        })

    return jobs
