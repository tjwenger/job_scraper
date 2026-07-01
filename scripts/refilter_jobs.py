"""
One-off maintenance: re-apply the current remote/onsite gate to existing jobs.

Only touches status='new' jobs (leaves applied/ignored/declined alone).
For LinkedIn jobs with an empty description (stored during the ID-extraction
bug era), re-fetches the description first so the gate can judge accurately,
then deletes any 'new' job that still fails is_remote_ok.

Run:  python scripts/refilter_jobs.py           (dry run — reports only)
      python scripts/refilter_jobs.py --apply    (delete failing 'new' jobs)
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from database import _conn  # noqa: E402
from scrapers.filters import is_remote_ok  # noqa: E402
from scrapers.linkedin import _job_id_from_url, _fetch_description  # noqa: E402

APPLY = "--apply" in sys.argv


def main():
    with _conn() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM jobs WHERE status = 'new'"
        ).fetchall()]

    print(f"{len(rows)} untouched 'new' jobs to review.\n")

    # 1. Re-fetch missing descriptions for LinkedIn jobs so judgment is accurate.
    refetched = 0
    with httpx.Client(follow_redirects=True) as client:
        for job in rows:
            if job["source"] != "linkedin":
                continue
            if (job.get("description") or "").strip():
                continue
            jid = _job_id_from_url(job["url"])
            if not jid:
                continue
            desc = _fetch_description(jid, client)
            if desc:
                job["description"] = desc[:2000]
                with _conn() as conn:
                    conn.execute(
                        "UPDATE jobs SET description = ? WHERE id = ?",
                        (job["description"], job["id"]),
                    )
                    conn.commit()
                refetched += 1
            time.sleep(1.5)  # polite delay

    print(f"Re-fetched {refetched} descriptions.\n")

    # 2. Re-apply the gate.
    failing = [j for j in rows if not is_remote_ok(j)]
    passing = [j for j in rows if is_remote_ok(j)]

    print(f"PASS: {len(passing)}   FAIL: {len(failing)}\n")
    print("Failing 'new' jobs (to be deleted):")
    for j in failing:
        has_desc = "desc" if (j.get("description") or "").strip() else "no-desc"
        print(f"  [{has_desc:7}] {j['location'][:26]:26} | {j['title'][:44]}")

    # 3. Delete failing jobs (only with --apply).
    if APPLY and failing:
        with _conn() as conn:
            conn.executemany(
                "DELETE FROM jobs WHERE id = ?",
                [(j["id"],) for j in failing],
            )
            conn.commit()
        print(f"\nDELETED {len(failing)} onsite/hybrid jobs.")
    elif failing:
        print(f"\n[dry run] Re-run with --apply to delete these {len(failing)} jobs.")
    else:
        print("\nNothing to delete.")


if __name__ == "__main__":
    main()
