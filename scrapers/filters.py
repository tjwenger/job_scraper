"""
Shared remote/onsite filtering — single source of truth for every scraper.

Design: a *positive remote gate*. A job is kept only when it shows an
affirmative remote signal. Onsite jobs frequently don't declare themselves
"on-site" (they just list a city), so a negative "drop on onsite keyword"
filter misses them. We instead require proof of remote.

Decision order (see `is_remote_ok`):
  1. "hybrid" anywhere        -> DROP (hard; not overridable — hybrid still
                                  requires office time even if "remote" appears)
  2. explicit onsite signal   -> DROP unless a STRONG remote signal overrides
  3. strong remote signal     -> KEEP (from location or description)
  4. ambiguous (city, no
     remote mention)          -> DROP (assume onsite)
"""
import re

# HARD drop — these require regular office presence by definition, so a "Remote"
# location label or remote language does NOT override them:
#   - "hybrid" (any form)
#   - a weekly office cadence ("3 days per week in office")
_HARD_ONSITE_RE = re.compile(
    r"("
    r"\bhybrid\b"
    r"|\d+\s*days?\s*(per|a|each)?\s*week\s*(in|at|from)?\s*(the )?(office|hq|onsite|on[\s\-]?site)"
    r"|\d+\s*days?\s*(in|at)\s*(the )?(office|hq)"
    r")",
    re.IGNORECASE,
)

# SOFT on-site signals — droppable, but a strong remote signal can override
# (e.g. "remote-first, occasional on-site meetings").
_ONSITE_RE = re.compile(
    r"("
    r"\bon[\s\-]?site\b|\bonsite\b"
    r"|\bin[\s\-]?office\b|\bin the office\b|\bin[\s\-]?person\b"
    r"|must (be (located|based|present|available)|reside|live) in"
    r"|required to (be in|report to|work (from|at|in)) (the )?(office|headquarters|hq)"
    r"|relocation (is )?(required|expected)"
    r")",
    re.IGNORECASE,
)

# STRONG remote signals — proof a role is genuinely remote. Deliberately
# excludes weak phrases like "remote-friendly" / "distributed team" that
# routinely appear in hybrid postings.
_STRONG_REMOTE_RE = re.compile(
    r"("
    r"fully[\s\-]?remote|100%\s*remote|remote[\s\-]?first|fully[\s\-]?distributed"
    r"|work from anywhere|this (is|role is) (a )?remote|position is remote"
    r"|remote (position|role|opportunity|based)|open to remote"
    r"|anywhere in the (us|u\.s\.|united states)"
    r")",
    re.IGNORECASE,
)

# Location strings that indicate remote at the location level.
_REMOTE_LOC_RE = re.compile(
    r"\b(remote|anywhere|distributed|work from home|wfh)\b",
    re.IGNORECASE,
)

# Country-level locations (no specific city) — weak remote hint. Kept only if
# the description doesn't contradict it with an onsite signal.
_COUNTRY_LOC_RE = re.compile(
    r"^\s*(united states|usa|u\.s\.a?\.?|us|remote|anywhere)\s*$",
    re.IGNORECASE,
)


def _has_strong_remote(text: str, location: str) -> bool:
    if location and _REMOTE_LOC_RE.search(location):
        return True
    if text and _STRONG_REMOTE_RE.search(text):
        return True
    return False


# ---------------------------------------------------------------------------
# Software-role gate — reject "Engineering" leadership roles that are actually
# physical/industrial engineering (process, mechanical, civil, manufacturing…)
# rather than software. Job titles overlap heavily ("Director of Engineering"
# means very different things at a battery plant vs. a SaaS company), so we
# judge on domain signals in the text, not the title.
# ---------------------------------------------------------------------------

# Physical / non-software engineering & industry domains → disqualifying.
# NOTE: no trailing \b so stems match inflections (manufactur -> manufacturing).
_PHYSICAL_ENG_RE = re.compile(
    r"\b("
    r"process engineer|mechanical engineer|civil engineer|chemical engineer"
    r"|electrical engineer|industrial engineer|structural engineer"
    r"|manufactur|materials science|metallurg|refiner|petrochemical"
    r"|epc|epcm|commissioning|capital project|process manufactur"
    r"|plant (manager|engineer|operations)|production facilit|industrial facilit"
    r"|assembly line|supply chain manufactur|hvac|piping|welding"
    r"|automotive|aerospace|oil\s*&?\s*gas|mining|drilling|construction"
    r"|semiconductor fab|foundry|hardware manufactur|circuit board|pcb"
    r")",
    re.IGNORECASE,
)

# Positive software-engineering signals → keeps the role even if a physical
# term appears incidentally (e.g. "software for manufacturing plants").
_SOFTWARE_RE = re.compile(
    r"\b("
    r"software|saas|web (app|application|platform)|cloud|api\b|backend|back[\-\s]end"
    r"|frontend|front[\-\s]end|full[\-\s]stack|micro[\-\s]?service|kubernetes|docker"
    r"|devops|ci/cd|codebase|source code|programming|developer|engineering team"
    r"|python|java(script)?|golang|typescript|react|node\.?js|aws|gcp|azure"
    r"|data (platform|pipeline|engineering)|machine learning|\bml\b|\bai\b|llm"
    r"|distributed systems|scalab|application development|mobile app|platform engineering"
    r")\b",
    re.IGNORECASE,
)


def is_software_role(job: dict) -> bool:
    """Return True if the role appears to be software engineering.

    Drops physical/industrial engineering roles that share the same titles.
    A job is kept (True) when either:
      - it shows a software signal, OR
      - it shows no physical-engineering signal at all (benefit of the doubt).
    It is rejected (False) only when a physical-engineering signal is present
    AND there is no software signal to counter it.
    """
    haystack = " ".join([
        job.get("title", ""),
        job.get("company", ""),
        (job.get("description", "") or "")[:2500],
    ])
    physical = bool(_PHYSICAL_ENG_RE.search(haystack))
    if not physical:
        return True  # nothing disqualifying → keep
    software = bool(_SOFTWARE_RE.search(haystack))
    return software  # physical present → keep only if software also present


def is_remote_ok(job: dict) -> bool:
    """Return True if the job should be kept (genuinely remote-eligible)."""
    desc = job.get("description", "") or ""
    location = job.get("location", "") or ""
    blob = f"{location}\n{desc}"

    strong_remote = _has_strong_remote(desc, location)

    # 1. Hard onsite (hybrid, weekly office cadence) — office time required by
    #    definition; not overridable by a "Remote" label or remote language.
    if _HARD_ONSITE_RE.search(blob):
        return False

    # 2. Explicit onsite signal drops unless a strong remote signal overrides it.
    if _ONSITE_RE.search(blob):
        return strong_remote

    # 3. Strong remote signal (location or description) → keep.
    if strong_remote:
        return True

    # 4. Country-level location with no contradicting onsite signal → keep
    #    (benefit of the doubt for e.g. "United States" postings).
    if _COUNTRY_LOC_RE.match(location.strip()):
        return True

    # 5. Ambiguous: specific city, no remote mention → assume onsite → drop.
    #    If we have no description at all and no location, keep (can't judge).
    if not desc and not location:
        return True
    return False
