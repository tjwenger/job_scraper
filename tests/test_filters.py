"""
Tests for the positive-remote gate in scrapers/filters.py.

Run: python -m pytest tests/test_filters.py -v
  or: python tests/test_filters.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.filters import is_remote_ok  # noqa: E402


# (label, job, expected_keep)
CASES = [
    # --- Onsite jobs that previously leaked through (regression guards) ---
    ("Ideal Aerosmith (Grand Forks manufacturer, no remote language)",
     {"title": "Director of Engineering", "company": "Ideal Aerosmith Inc.",
      "location": "Grand Forks, ND", "description": "Lead our engineering team building precision motion systems."},
     False),
    ("Teledyne (specific city, no remote mention)",
     {"title": "Chief Engineer", "company": "Teledyne",
      "location": "Huntsville, AL", "description": "Oversee hardware engineering programs at our Huntsville facility."},
     False),

    # --- Hybrid is a hard drop, even with remote language present ---
    ("Hybrid role that also says remote",
     {"title": "VP Engineering", "company": "Acme",
      "location": "New York, NY", "description": "This is a hybrid role. Remote-friendly with 2 days per week in office."},
     False),
    ("'Remote or hybrid' still requires office time",
     {"title": "Director of Engineering", "company": "Acme",
      "location": "United States", "description": "Work style: remote or hybrid depending on team."},
     False),

    # --- Explicit onsite signal, no override ---
    ("Onsite required in office",
     {"title": "VP Engineering", "company": "Acme",
      "location": "Austin, TX", "description": "Must be located in Austin. This is an in-office position."},
     False),
    ("N days per week in office",
     {"title": "Director of Engineering", "company": "Acme",
      "location": "Remote", "description": "Requires 3 days per week in the office at our HQ."},
     False),

    # --- Genuinely remote — must be kept ---
    ("1Password fully remote",
     {"title": "Senior Director of Engineering, Consumer AI", "company": "1Password",
      "location": "Remote (United States | Canada)", "description": "This is a remote opportunity within Canada and the US."},
     True),
    ("Remote in location",
     {"title": "VP Engineering", "company": "Acme",
      "location": "Remote", "description": "Lead a global team."},
     True),
    ("Fully remote in description, city location",
     {"title": "VP Engineering", "company": "Acme",
      "location": "San Francisco, CA", "description": "We are a fully remote company; work from anywhere in the US."},
     True),
    ("Country-level location, no onsite mention",
     {"title": "Director of Engineering", "company": "Acme",
      "location": "United States", "description": "Lead our platform engineering org."},
     True),

    # --- Override: strong remote beats an incidental onsite mention ---
    ("Remote-first with occasional onsite meetings",
     {"title": "VP Engineering", "company": "Acme",
      "location": "Remote", "description": "Remote-first team. Occasional on-site meetings a few times a year."},
     True),

    # --- Edge: no data at all → can't judge → keep ---
    ("No location, no description",
     {"title": "VP Engineering", "company": "Acme", "location": "", "description": ""},
     True),
]


def run():
    failures = 0
    for label, job, expected in CASES:
        got = is_remote_ok(job)
        ok = got == expected
        if not ok:
            failures += 1
        print(f"[{'OK' if ok else 'FAIL'}] keep={got} (expected {expected}) — {label}")
    print()
    if failures:
        print(f"{failures} FAILURE(S)")
        return 1
    print(f"All {len(CASES)} cases passed.")
    return 0


# pytest entry point (optional — the file also runs standalone without pytest)
try:
    import pytest

    @pytest.mark.parametrize("label,job,expected", CASES, ids=[c[0] for c in CASES])
    def test_is_remote_ok(label, job, expected):
        assert is_remote_ok(job) is expected
except ImportError:
    pass


if __name__ == "__main__":
    sys.exit(run())
