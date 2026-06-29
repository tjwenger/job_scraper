"""
Edit KEYWORDS and EXCLUDE_KEYWORDS to control which jobs are matched.
Jobs matching any keyword in KEYWORDS (case-insensitive) are stored.
Jobs matching any term in EXCLUDE_KEYWORDS are filtered out.

Keywords can also be edited live via the dashboard at /keywords — changes
are saved to keywords.json and take effect on the next scrape run.
"""
import json
from pathlib import Path

_KW_FILE = Path(__file__).parent / "keywords.json"

_DEFAULT_KEYWORDS = [
    # VP-level titles
    "VP of Engineering",
    "Vice President of Engineering",
    "VP Engineering",
    "VP Software Engineering",
    "Vice President Software",
    "VP of Software",
    "VP Technology",
    "VP of Technology",
    "Vice President Technology",
    # Director-level titles
    "Director of Engineering",
    "Director of Software Engineering",
    "Director Software Engineering",
    "Engineering Director",
    "Director of Technology",
    "Director Technology",
    "Senior Director Engineering",
    "Senior Director of Engineering",
    "Director of Platform",
    "Director of Infrastructure",
]

_DEFAULT_EXCLUDE_KEYWORDS = [
    # On-site / hybrid only
    "on-site only",
    "onsite only",
    "in-office",
    "relocation required",
    # Non-tech industries
    "healthcare",
    "insurance",
    "financial advisor",
    "mortgage",
    "real estate",
    "manufacturing",
    # Non-engineering leadership
    "Director of Sales",
    "Director of Marketing",
    "Director of Operations",
    "VP of Sales",
    "VP of Marketing",
    "VP of Finance",
    # Too junior (whole-word to avoid matching "internal", "internship" in descriptions)
    " intern ",
    "internship",
    " junior ",
    "entry level",
    "associate engineer",
]


def _load() -> tuple[list[str], list[str]]:
    if _KW_FILE.exists():
        try:
            data = json.loads(_KW_FILE.read_text(encoding="utf-8"))
            return data.get("keywords", _DEFAULT_KEYWORDS), data.get("exclude_keywords", _DEFAULT_EXCLUDE_KEYWORDS)
        except Exception:
            pass
    return _DEFAULT_KEYWORDS, _DEFAULT_EXCLUDE_KEYWORDS


def save_keywords(keywords: list[str], exclude_keywords: list[str]) -> None:
    """Persist keyword lists to keywords.json."""
    _KW_FILE.write_text(
        json.dumps({"keywords": keywords, "exclude_keywords": exclude_keywords}, indent=2),
        encoding="utf-8",
    )


def reload() -> tuple[list[str], list[str]]:
    """Reload from disk and update module-level globals. Call after save_keywords()."""
    global KEYWORDS, EXCLUDE_KEYWORDS
    KEYWORDS, EXCLUDE_KEYWORDS = _load()
    return KEYWORDS, EXCLUDE_KEYWORDS


KEYWORDS, EXCLUDE_KEYWORDS = _load()

# How often to run scrapers automatically (in minutes). Set to 0 to disable.
SCRAPE_INTERVAL_MINUTES = 120

# Max pages to scrape per source per run (keeps runtime short)
MAX_PAGES_PER_SOURCE = 3

# User-agent header used for HTTP requests
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
