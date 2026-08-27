"""
rubric.py
Deterministic, auditable pre-scoring of a lead against the rubric in config.yaml.

Why a rule-based pass at all, instead of just asking the LLM to score everything?
  - It's free, instant, and 100% reproducible -- good for the 1,140 leads/month
    that never even need a model call once this is proven out.
  - It gives the LLM a grounded, explainable starting point instead of asking it
    to invent scoring criteria from scratch on every call (cheaper prompts,
    more consistent output).
  - It's easy for a sales team to audit ("why did this lead score a 6?") without
    reverse-engineering model behavior.
"""

from datetime import datetime, date
from typing import Any


def _company_size_score(size: str, rubric: dict) -> float:
    if size in rubric["target_company_size_band"]:
        return 10.0
    if size in rubric["acceptable_company_size_bands"]:
        return 6.0
    if size in rubric["poor_fit_company_size_bands"]:
        return 2.0
    return 4.0  # unrecognized band -> mild penalty, not a hard fail


def _industry_score(industry: str, rubric: dict) -> float:
    if industry in rubric["target_industries"]:
        return 10.0
    if industry in rubric["acceptable_industries"]:
        return 6.0
    if industry in rubric["poor_fit_industries"]:
        return 2.0
    return 4.0


def _source_score(source: str, rubric: dict) -> float:
    return float(rubric["source_quality_scores"].get(source, 4))


def _recency_score(last_interaction_date: str, rubric: dict, today: date) -> tuple[float, int | None]:
    try:
        d = datetime.strptime(last_interaction_date.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return 3.0, None  # missing/unparseable date -> neutral-low score, don't crash

    days = (today - d).days
    for band in rubric["recency_bands"]:
        if days <= band["max_days"]:
            return float(band["score"]), days
    return 1.0, days


def _budget_timeline_score(notes: str) -> float:
    """
    Lightweight keyword heuristic over the free-text notes field. This is
    intentionally coarse -- it's a *pre*-score. The LLM step re-reads the full
    notes text and can override this in either direction with reasoning.
    """
    if not notes:
        return 5.0
    text = notes.lower()

    positive = ["budget approved", "budget confirmed", "budget ready", "this week",
                "this quarter", "ready to", "wants to switch", "decide by", "sign-off",
                "proposal"]
    negative = ["no budget", "not interested", "just researching", "no timeline",
                "unclear", "6+ months", "next year", "tbd", "unsubscribed"]

    score = 5.0
    for kw in positive:
        if kw in text:
            score += 1.5
    for kw in negative:
        if kw in text:
            score -= 1.5
    return max(0.0, min(10.0, score))


def score_lead(lead: dict[str, Any], rubric: dict, today: date | None = None) -> dict[str, Any]:
    """Returns the lead dict enriched with per-factor scores, rule_score, and
    a list of missing/malformed fields so downstream steps can flag them."""
    today = today or date.today()
    weights = rubric["weights"]
    missing_fields = []

    for field in ("name", "company", "company_size", "industry", "source", "last_interaction_date"):
        if not lead.get(field, "").strip():
            missing_fields.append(field)

    company_size = _company_size_score(lead.get("company_size", ""), rubric)
    industry = _industry_score(lead.get("industry", ""), rubric)
    source = _source_score(lead.get("source", ""), rubric)
    recency, days_since = _recency_score(lead.get("last_interaction_date", ""), rubric, today)
    budget_timeline = _budget_timeline_score(lead.get("notes", ""))

    factor_scores = {
        "company_size_fit": company_size,
        "industry_fit": industry,
        "engagement_recency": recency,
        "source_quality": source,
        "budget_timeline_signal": budget_timeline,
    }

    rule_score = sum(factor_scores[k] * weights[k] for k in weights)
    rule_score = round(rule_score, 2)

    notes_lower = (lead.get("notes") or "").lower()
    forced_review = any(kw in notes_lower for kw in rubric["force_review_keywords"])

    return {
        **lead,
        "factor_scores": factor_scores,
        "rule_score": rule_score,
        "days_since_contact": days_since,
        "missing_fields": missing_fields,
        "forced_review": forced_review,
    }
