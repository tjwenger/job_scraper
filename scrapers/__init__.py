from .remoteok import scrape_remoteok
from .wwr import scrape_wwr
from .hackernews import scrape_hackernews
from .glassdoor import scrape_glassdoor
from .linkedin import scrape_linkedin
from .lever import scrape_lever
from .lever_co import scrape_lever_co
from .ashby import scrape_ashby

ALL_SCRAPERS = {
    "linkedin": scrape_linkedin,
    "greenhouse": scrape_lever,
    "ashby": scrape_ashby,
    "lever": scrape_lever_co,
    "glassdoor": scrape_glassdoor,
    "remoteok": scrape_remoteok,
    "weworkremotely": scrape_wwr,
    "hackernews": scrape_hackernews,
    # indeed: disabled — blocks all automated access (403 + Cloudflare)
}
