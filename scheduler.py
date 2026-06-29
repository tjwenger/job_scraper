import logging
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from apscheduler.schedulers.background import BackgroundScheduler
from database import init_db, upsert_job, log_scrape_start, log_scrape_end
from scrapers import ALL_SCRAPERS
from config import SCRAPE_INTERVAL_MINUTES

MAX_AGE_DAYS = 30


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:
        return None


def _is_recent(job: dict) -> bool:
    """Returns True if the job was posted within MAX_AGE_DAYS, or if date is unknown."""
    dt = _parse_date(job.get("posted_at", ""))
    if dt is None:
        return True  # keep jobs with no parseable date
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    return dt >= cutoff

logger = logging.getLogger(__name__)
_scheduler = BackgroundScheduler()


def run_scraper(name: str, keywords: list[str] | None = None) -> dict:
    """Run a single named scraper and persist results. Returns a summary dict."""
    fn = ALL_SCRAPERS.get(name)
    if not fn:
        return {"error": f"Unknown scraper: {name}"}

    log_id = log_scrape_start(name)
    new_count = 0
    error_msg = ""

    try:
        jobs = fn(keywords)
        for job in jobs:
            if _is_recent(job) and upsert_job(job):
                new_count += 1
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Scraper '{name}' failed: {e}")

    log_scrape_end(log_id, new_count, error_msg)
    return {"source": name, "new_jobs": new_count, "error": error_msg}


def run_all_scrapers(keywords: list[str] | None = None) -> list[dict]:
    results = []
    for name in ALL_SCRAPERS:
        results.append(run_scraper(name, keywords))

    # Score any newly added jobs after scraping
    try:
        from scorer import score_unscored_jobs
        scored = score_unscored_jobs()
        if scored:
            logger.info(f"Scored {scored} new jobs after scraping.")
    except Exception as e:
        logger.warning(f"Scoring step failed (non-fatal): {e}")

    return results


def start_scheduler():
    if SCRAPE_INTERVAL_MINUTES <= 0:
        return
    _scheduler.add_job(
        run_all_scrapers,
        "interval",
        minutes=SCRAPE_INTERVAL_MINUTES,
        id="auto_scrape",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(f"Scheduler started — scraping every {SCRAPE_INTERVAL_MINUTES} minutes.")


def stop_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
