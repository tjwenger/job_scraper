# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
# Install dependencies
pip install -r requirements.txt

# Start the web dashboard (http://127.0.0.1:8000)
python main.py

# Run all scrapers once from the command line (no server required)
python -c "
import sys; sys.path.insert(0, '.')
from database import init_db
from scheduler import run_all_scrapers
init_db()
results = run_all_scrapers()
for r in results: print(r['source'], '+' + str(r['new_jobs']), r.get('error',''))
"

# Run a single scraper by name (linkedin, indeed, glassdoor, remoteok, weworkremotely, hackernews)
python -c "
import sys; sys.path.insert(0, '.')
from database import init_db
from scheduler import run_scraper
init_db()
print(run_scraper('linkedin'))
"
```

## Architecture

The app has four distinct layers that are kept strictly separate:

1. **`config.py`** — single source of truth for all user-tunable behaviour: `KEYWORDS`, `EXCLUDE_KEYWORDS`, `SCRAPE_INTERVAL_MINUTES`, `MAX_PAGES_PER_SOURCE`, `USER_AGENT`. Every scraper imports from here; changes take effect on the next run without touching scraper code.

2. **`scrapers/`** — one file per source, each exporting a `scrape_<name>(keywords=None) -> list[dict]` function. All scrapers return the same job dict shape: `{title, company, location, url, source, description, salary, posted_at}`. Remote-only filtering is enforced at the HTTP param level where the source supports it (LinkedIn `f_WT=2`, Indeed `remotejob=1`, Glassdoor `remoteWorkType` filter param); HN falls back to requiring "remote" in the text. `ALL_SCRAPERS` in `scrapers/__init__.py` is the registry — add new sources there.

3. **`scheduler.py`** — orchestration layer. `run_scraper(name)` calls the scraper, applies the 7-day recency filter (`_is_recent`), deduplicates via `upsert_job`, and writes a scrape log entry. The in-process APScheduler fires `run_all_scrapers` on the interval set in `config.py`. The FastAPI lifespan hook starts/stops the scheduler.

4. **`database.py` + `jobs.db`** — SQLite via the stdlib `sqlite3` module (no ORM). Two tables: `jobs` (primary store, keyed by `md5(url)`) and `scrape_log`. `get_jobs`/`count_jobs` both accept `show_declined=False` which silently excludes `status='declined'` from all queries unless overridden.

**`app.py`** is a thin FastAPI layer: `GET /` renders the Jinja2 dashboard, `POST /scrape` fires scrapers as a background task, `POST /status/{id}` updates job status (new / interested / applied / rejected / ignored / declined). There are also JSON endpoints at `/api/jobs` and `/api/log`.

## Key behaviours to preserve

- **Deduplication** is URL-based (`md5(url)`). Changing a job's URL (e.g. stripping vs. keeping query params) will create duplicates. Strip tracking params before storing — see `linkedin.py` for the pattern.
- **`declined` status is hidden by default** — `get_jobs` and `count_jobs` exclude it unless `show_declined=True` is passed. The dashboard decline button fades the row out client-side and POSTs to `/status/{id}`.
- **Date filtering happens in `scheduler.py`, not in scrapers.** Jobs with no parseable `posted_at` are kept (benefit of the doubt). Do not add date filtering inside individual scrapers.
- **LinkedIn uses `PRIORITY_TERMS`** (6 hardcoded terms) instead of the full `KEYWORDS` list to avoid rate limits. If keywords are passed explicitly at call time, it uses those instead.

## Scheduled automation

A Claude Code scheduled task (`daily-job-scrape`) runs all scrapers every day at 9am via the Claude Code scheduler. The task definition lives at `C:\Users\tjwen\.claude\scheduled-tasks\daily-job-scrape\SKILL.md`. The app must be open for scheduled runs to fire.

The in-process APScheduler (controlled by `SCRAPE_INTERVAL_MINUTES` in `config.py`) is a separate, secondary mechanism that runs while the web server is up. Set it to `0` to disable it.
