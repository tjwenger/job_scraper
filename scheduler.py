import logging
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from apscheduler.schedulers.background import BackgroundScheduler
from database import init_db, upsert_job, log_scrape_start, log_scrape_end
from scrapers import ALL_SCRAPERS
from config import SCRAPE_INTERVAL_MINUTES

MAX_AGE_DAYS = 30

# ---------------------------------------------------------------------------
# Post-scrape filters — applied to every job from every scraper
# ---------------------------------------------------------------------------

# Onsite/hybrid filtering lives in scrapers/filters.py so every source — and
# this central gate — applies the exact same positive-remote logic.
from scrapers.filters import is_remote_ok

# Non-tech industries — matched against title + company + description
_NON_TECH_RE = re.compile(
    r"\b("
    # Healthcare / medical
    r"hospital|health\s*system|health\s*plan|clinic|medical center|physician"
    r"|nursing|dental|pharmacy|pharma(ceutical)?|biotech(?! software)|genomics"
    r"|patient care|clinical trial|ehr|epic systems"
    # Financial services (non-fintech)
    r"|bank(?:ing)?|credit union|mortgage|insurance(?! software| tech| platform)"
    r"|wealth management|asset management|brokerage|underwriting|actuarial"
    r"|financial advisor|investment bank|hedge fund|private equity"
    # Retail / CPG / Food
    r"|retail chain|grocery|supermarket|restaurant|food service|hospitality"
    r"|hotel|resort|casino|travel agency"
    # Industrial / Manufacturing / Energy
    r"|manufactur|automotive|aerospace|defense contractor|oil\s*&?\s*gas"
    r"|utilities|power plant|mining|agriculture|farming"
    # Government / Nonprofit / Education
    r"|government|federal agency|dept\. of|department of (defense|labor|energy)"
    r"|non[\-\s]?profit|school district|k[\-\s]?12|university hospital"
    r")\b",
    re.IGNORECASE,
)

# Explicit tech-company signals in the description that override _NON_TECH_RE
_TECH_OVERRIDE_RE = re.compile(
    r"\b(saas|software platform|api|cloud platform|developer platform"
    r"|series [a-e]|venture[\-\s]backed|seed[\-\s]funded|fintech|insurtech"
    r"|healthtech|techstack|microservices|kubernetes|aws|gcp|azure)\b",
    re.IGNORECASE,
)


def _is_non_tech(job: dict) -> bool:
    """True if the job appears to be at a non-technology company."""
    haystack = " ".join([
        job.get("title", ""),
        job.get("company", ""),
        job.get("description", "")[:1500],
    ])
    if not _NON_TECH_RE.search(haystack):
        return False
    # If there are strong tech signals, keep the job anyway
    return not bool(_TECH_OVERRIDE_RE.search(haystack))


def _passes_filters(job: dict) -> bool:
    """Central post-scrape gate. Returns False to drop the job."""
    if not is_remote_ok(job):
        logging.getLogger(__name__).debug(
            "Dropped (onsite/hybrid): %s @ %s", job.get("title"), job.get("company")
        )
        return False
    if _is_non_tech(job):
        logging.getLogger(__name__).debug(
            "Dropped (non-tech industry): %s @ %s", job.get("title"), job.get("company")
        )
        return False
    return True


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
            if _is_recent(job) and _passes_filters(job) and upsert_job(job):
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
