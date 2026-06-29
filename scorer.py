"""
Scores job listings against TJ's resume using the Claude API.
Each job gets a 0-100 fit score and a one-sentence reason.

Requires ANTHROPIC_API_KEY in the environment (or a .env file).
"""
import os
import json
import logging
from pathlib import Path

import anthropic

import database as db

logger = logging.getLogger(__name__)

RESUME_PATH = Path(__file__).parent / "resume.txt"
_resume_text: str | None = None

SCORE_PROMPT = """\
You are a recruiting assistant evaluating job fit for a specific candidate.

## Candidate resume
{resume}

## Job listing
Title: {title}
Company: {company}
Location: {location}
Source: {source}
Description: {description}

## Task
Do two things:

1. SCORE: Rate how well this job matches the candidate on a scale of 0–100:
   - 90–100: Exceptional fit — title, seniority, domain, and tech stack all align
   - 70–89:  Strong fit — most dimensions align with minor gaps
   - 50–69:  Moderate fit — role is relevant but meaningful gaps exist
   - 30–49:  Weak fit — tangentially related but likely a stretch or mismatch
   - 0–29:   Poor fit — wrong seniority, industry, or domain
   Consider: title seniority (VP/Director target), remote-friendliness, tech company preferred,
   domain relevance (cloud/DevOps/SRE/platform/AI), team leadership scope, tech stack overlap.
   If the description is empty, score based on title and company name alone — do not return null.

2. COMPANY SIZE: Estimate the company's current headcount as an integer.
   Use your knowledge of the company. If the description mentions headcount, use that.
   If truly unknown, return null. Do NOT guess wildly — return null if uncertain.

You MUST always return a numeric score. Never return null for the score field.

Respond with ONLY valid JSON (no markdown fences), exactly this shape:
{{"score": <integer 0-100>, "reason": "<one concise sentence explaining the score>", "company_size": <integer or null>}}
"""


def _get_resume() -> str:
    global _resume_text
    if _resume_text is None:
        _resume_text = RESUME_PATH.read_text(encoding="utf-8")
    return _resume_text


def score_job(job: dict) -> tuple[int, str]:
    """Score a single job dict. Returns (score, reason)."""
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    prompt = SCORE_PROMPT.format(
        resume=_get_resume(),
        title=job.get("title", ""),
        company=job.get("company", ""),
        location=job.get("location", ""),
        source=job.get("source", ""),
        description=(job.get("description") or "")[:800],
    )

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    parsed = json.loads(raw)
    raw_score = parsed.get("score")
    if raw_score is None:
        raise ValueError("Model returned null score")
    score = max(0, min(100, int(raw_score)))
    reason = str(parsed.get("reason", ""))
    company_size = parsed.get("company_size")
    if company_size is not None:
        try:
            company_size = int(company_size)
        except (ValueError, TypeError):
            company_size = None
    return score, reason, company_size


def score_unscored_jobs(limit: int = 50) -> int:
    """Score all unscored active jobs. Returns count of jobs scored."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping scoring")
        return 0

    jobs = db.get_unscored_jobs(limit=limit)
    scored = 0
    for job in jobs:
        try:
            score, reason, company_size = score_job(job)
            db.update_score(job["id"], score, reason, company_size)
            scored += 1
            logger.info(f"Scored '{job['title']}' at {job['company']}: {score} | size: {company_size}")
        except Exception as e:
            logger.error(f"Failed to score job {job['id']}: {e}")
    return scored
