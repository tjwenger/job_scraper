"""
Edit KEYWORDS and EXCLUDE_KEYWORDS to control which jobs are matched.
Jobs matching any keyword in KEYWORDS (case-insensitive) are stored.
Jobs matching any term in EXCLUDE_KEYWORDS are filtered out.
"""

KEYWORDS = [
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

EXCLUDE_KEYWORDS = [
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
