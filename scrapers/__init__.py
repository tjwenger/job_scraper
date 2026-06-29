from .remoteok import scrape_remoteok
from .wwr import scrape_wwr
from .hackernews import scrape_hackernews
from .indeed import scrape_indeed
from .glassdoor import scrape_glassdoor
from .linkedin import scrape_linkedin
from .lever import scrape_lever

ALL_SCRAPERS = {
    "linkedin": scrape_linkedin,
    "greenhouse": scrape_lever,
    "indeed": scrape_indeed,
    "glassdoor": scrape_glassdoor,
    "remoteok": scrape_remoteok,
    "weworkremotely": scrape_wwr,
    "hackernews": scrape_hackernews,
}
