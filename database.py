import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "jobs.db"


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                company     TEXT,
                location    TEXT,
                url         TEXT NOT NULL,
                source      TEXT NOT NULL,
                description TEXT,
                salary      TEXT,
                posted_at   TEXT,
                scraped_at  TEXT NOT NULL,
                status      TEXT DEFAULT 'new',
                notes       TEXT DEFAULT '',
                score        INTEGER DEFAULT NULL,
                score_reason TEXT DEFAULT '',
                company_size INTEGER DEFAULT NULL
            )
        """)
        # Migrate existing databases
        for col, definition in [
            ("notes", "TEXT DEFAULT ''"),
            ("score", "INTEGER DEFAULT NULL"),
            ("score_reason", "TEXT DEFAULT ''"),
            ("company_size", "INTEGER DEFAULT NULL"),
        ]:
            try:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {definition}")
                conn.commit()
            except Exception:
                pass  # Column already exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scrape_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                source     TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                new_jobs   INTEGER DEFAULT 0,
                error      TEXT
            )
        """)
        conn.commit()


def job_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def upsert_job(job: dict) -> bool:
    """Insert job if new. Returns True if it was a new insertion."""
    jid = job_id(job["url"])
    with _conn() as conn:
        existing = conn.execute("SELECT id FROM jobs WHERE id = ?", (jid,)).fetchone()
        if existing:
            return False
        conn.execute(
            """
            INSERT INTO jobs (id, title, company, location, url, source,
                              description, salary, posted_at, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                jid,
                job.get("title", ""),
                job.get("company", ""),
                job.get("location", ""),
                job["url"],
                job.get("source", ""),
                job.get("description", ""),
                job.get("salary", ""),
                job.get("posted_at", ""),
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        return True


def get_job_by_id(job_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def get_jobs(
    search: str = "",
    source: str = "",
    status: str = "",
    show_declined: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    query = "SELECT * FROM jobs WHERE 1=1"
    params: list = []

    if search:
        query += " AND (title LIKE ? OR company LIKE ? OR description LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like]
    if source:
        query += " AND source = ?"
        params.append(source)
    if status:
        query += " AND status = ?"
        params.append(status)
    elif not show_declined:
        query += " AND status != 'declined'"

    query += " ORDER BY CASE WHEN score IS NULL THEN 1 ELSE 0 END, score DESC, scraped_at DESC LIMIT ? OFFSET ?"
    params += [limit, offset]

    with _conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def count_jobs(search: str = "", source: str = "", status: str = "", show_declined: bool = False) -> int:
    query = "SELECT COUNT(*) FROM jobs WHERE 1=1"
    params: list = []
    if search:
        query += " AND (title LIKE ? OR company LIKE ? OR description LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like]
    if source:
        query += " AND source = ?"
        params.append(source)
    if status:
        query += " AND status = ?"
        params.append(status)
    elif not show_declined:
        query += " AND status != 'declined'"
    with _conn() as conn:
        return conn.execute(query, params).fetchone()[0]


def update_status(job_id: str, status: str):
    with _conn() as conn:
        conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
        conn.commit()


def update_score(job_id: str, score: int, reason: str, company_size: int | None = None):
    with _conn() as conn:
        conn.execute(
            "UPDATE jobs SET score = ?, score_reason = ?, company_size = ? WHERE id = ?",
            (score, reason, company_size, job_id),
        )
        conn.commit()


def get_unscored_jobs(limit: int = 50) -> list[dict]:
    """Return active jobs that haven't been scored yet."""
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM jobs
            WHERE score IS NULL
              AND status NOT IN ('declined', 'rejected', 'ignored')
            ORDER BY scraped_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_notes(job_id: str, notes: str):
    with _conn() as conn:
        conn.execute("UPDATE jobs SET notes = ? WHERE id = ?", (notes, job_id))
        conn.commit()


def get_rejection_notes() -> list[dict]:
    """Return all declined/rejected jobs that have notes, newest first."""
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT id, title, company, source, status, notes, scraped_at
            FROM jobs
            WHERE status IN ('declined', 'rejected')
              AND notes != ''
            ORDER BY scraped_at DESC
            """,
        ).fetchall()
    return [dict(r) for r in rows]


def log_scrape_start(source: str) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO scrape_log (source, started_at) VALUES (?, ?)",
            (source, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def log_scrape_end(log_id: int, new_jobs: int, error: str = ""):
    with _conn() as conn:
        conn.execute(
            "UPDATE scrape_log SET finished_at = ?, new_jobs = ?, error = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), new_jobs, error, log_id),
        )
        conn.commit()


def is_scrape_running() -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM scrape_log WHERE finished_at IS NULL"
        ).fetchone()
    return row[0] > 0


def get_scrape_log(limit: int = 20) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scrape_log ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_sources() -> list[str]:
    with _conn() as conn:
        rows = conn.execute("SELECT DISTINCT source FROM jobs ORDER BY source").fetchall()
    return [r[0] for r in rows]
