"""
llm_client.py
Handles all LLM calls: batching, prompt construction, retries with exponential
backoff + jitter, and parsing structured JSON responses.

Two providers:
  - "mock":      deterministic local stand-in, no network/API key needed.
                 Used so the pipeline is fully runnable and gradeable offline.
  - "anthropic": real call to the Claude API. Set ANTHROPIC_API_KEY and flip
                 config.yaml -> api.provider to "anthropic" to use it.

Both providers implement the same interface: score_and_message_batch(leads) ->
list of result dicts, one per lead, in the same order as the input.
"""

import json
import os
import random
import time
import logging
from typing import Any

logger = logging.getLogger("lead_qualifier.llm")

COMPANY_PROFILE = (
    "We sell a workflow/analytics SaaS platform to mid-market B2B companies. "
    "Typical deal size is $5k-$60k/year. Best-fit buyers are Ops, RevOps, or "
    "Product/Eng leaders at 51-500 person companies in software, tech, "
    "e-commerce, or financial services, with a stated timeline or budget signal."
)

SYSTEM_PROMPT = f"""You are a B2B sales qualification assistant.

Company context: {COMPANY_PROFILE}

For each lead in the batch you will receive: contact info, a rule-based
pre-score (0-10) broken down by factor, and free-text notes from their most
recent interaction.

For each lead, return:
  - final_score (0-10, one decimal place): your judgment after reading the
    notes. Start from the rule_score; only move it if the notes justify the
    move, and say why in reasoning.
  - decision: one of "qualified", "rejected", "review". Use "review" for
    genuinely ambiguous cases (conflicting signals, missing key info,
    borderline score) rather than guessing.
  - reasoning: 1-2 sentences, specific to this lead, referencing an actual
    detail from their notes or profile.
  - outreach_message: ONLY for "qualified" leads. A 2-4 sentence personalized
    first-touch message. It must reference at least one specific, real detail
    from this lead's company/notes (not a generic template). For "rejected"
    or "review" leads, set this to null.

Respond with ONLY a JSON array, one object per lead, in the SAME ORDER as the
input leads, with keys: id, final_score, decision, reasoning, outreach_message.
No prose outside the JSON array.
"""


class LLMError(Exception):
    pass


def _build_user_prompt(leads: list[dict[str, Any]]) -> str:
    payload = []
    for lead in leads:
        payload.append({
            "id": lead["_batch_id"],
            "name": lead.get("name"),
            "company": lead.get("company"),
            "company_size": lead.get("company_size"),
            "industry": lead.get("industry"),
            "source": lead.get("source"),
            "days_since_last_contact": lead.get("days_since_contact"),
            "notes": lead.get("notes"),
            "rule_score": lead.get("rule_score"),
            "factor_scores": lead.get("factor_scores"),
        })
    return "Leads:\n" + json.dumps(payload, indent=2)


def _with_retry(fn, max_retries: int, base_backoff: float, what: str):
    """Runs fn() with exponential backoff + jitter on transient failures.
    Re-raises the last error if all retries are exhausted."""
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except LLMError as e:
            last_err = e
            if attempt == max_retries:
                break
            sleep_s = base_backoff * (2 ** attempt) + random.uniform(0, 0.5)
            logger.warning(
                "%s failed (attempt %d/%d): %s -- retrying in %.1fs",
                what, attempt + 1, max_retries + 1, e, sleep_s,
            )
            time.sleep(sleep_s)
    raise last_err


class AnthropicProvider:
    def __init__(self, cfg: dict):
        self.model = cfg["model"]
        self.max_tokens = cfg["max_tokens"]
        self.max_retries = cfg["max_retries"]
        self.base_backoff = cfg["base_backoff_seconds"]
        self.timeout = cfg["request_timeout_seconds"]
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set. Export it, or set api.provider "
                "to 'mock' in config.yaml to run without a live key."
            )
        import anthropic  # imported lazily so 'mock' mode has no hard dependency
        self._client = anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout)

    def _call_once(self, leads: list[dict[str, Any]]) -> list[dict]:
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _build_user_prompt(leads)}],
            )
        except Exception as e:  # covers rate limits, timeouts, connection errors
            raise LLMError(f"API request failed: {e}") from e

        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.split("\n", 1)[-1] if "\n" in text else text
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"Could not parse JSON response: {e}") from e

        if not isinstance(parsed, list) or len(parsed) != len(leads):
            raise LLMError(
                f"Response shape mismatch: expected {len(leads)} results, got "
                f"{len(parsed) if isinstance(parsed, list) else type(parsed)}"
            )
        return parsed

    def score_and_message_batch(self, leads: list[dict[str, Any]]) -> list[dict]:
        return _with_retry(
            lambda: self._call_once(leads),
            self.max_retries, self.base_backoff, "Anthropic batch call",
        )


class MockProvider:
    """
    Deterministic stand-in for the LLM. Applies the same qualitative judgment
    an LLM prompt would (read the notes, nudge the score, write a grounded
    reasoning line and a personalized message) using simple rules, so the full
    pipeline is runnable and reviewable with zero network access or API key.

    Also simulates an occasional transient failure (5% of batches) so the
    retry/backoff path is exercised in a demo run, not just in theory.
    """

    def __init__(self, cfg: dict):
        self.max_retries = cfg["max_retries"]
        self.base_backoff = cfg["base_backoff_seconds"]
        self._fail_once_ids: set[int] = set()

    def _judge_one(self, lead: dict[str, Any]) -> dict:
        score = lead["rule_score"]
        notes = (lead.get("notes") or "")
        notes_lower = notes.lower()

        nudge = 0.0
        reason_bits = []

        strong_positive = ["budget approved", "budget confirmed", "budget ready",
                            "ready to onboard", "wants to switch", "sign-off", "proposal"]
        strong_negative = ["no budget", "not interested", "unsubscribed", "wrong contact",
                            "just researching"]

        for kw in strong_positive:
            if kw in notes_lower:
                nudge += 1.0
                reason_bits.append(kw)
                break
        for kw in strong_negative:
            if kw in notes_lower:
                nudge -= 1.0
                reason_bits.append(kw)
                break

        final_score = round(max(0.0, min(10.0, score + nudge)), 1)

        if lead.get("forced_review"):
            decision = "review"
        elif final_score >= 7.0:
            decision = "qualified"
        elif final_score <= 4.0:
            decision = "rejected"
        else:
            decision = "review"

        # Build a grounded reasoning sentence referencing real notes content.
        clipped_notes = notes.strip().rstrip(".")
        if reason_bits:
            reasoning = (
                f"{lead.get('company')} scored {final_score}/10: notes mention "
                f"\"{reason_bits[0]}\", which {'supports' if nudge > 0 else 'weakens'} fit "
                f"alongside a rule-based pre-score of {score}/10."
            )
        elif clipped_notes:
            reasoning = (
                f"{lead.get('company')} scored {final_score}/10 based on company size, "
                f"industry, and source fit; notes (\"{clipped_notes[:80]}\") were "
                f"read but didn't strongly shift the score either way."
            )
        else:
            reasoning = (
                f"{lead.get('company')} scored {final_score}/10 from rubric factors alone; "
                f"no notes were available to refine the score."
            )

        outreach_message = None
        if decision == "qualified":
            detail = clipped_notes if clipped_notes else f"your work at {lead.get('company')}"
            first_name = (lead.get("name") or "there").split(" ")[0]
            outreach_message = (
                f"Hi {first_name}, saw that {detail[:100].rstrip()} -- given the size and "
                f"shape of {lead.get('company')}'s team, I think there's a strong fit with "
                f"what we've built for similar {lead.get('industry', 'B2B')} companies. "
                f"Would you have 15 minutes this week to walk through what that could look "
                f"like for you?"
            )

        return {
            "id": lead["_batch_id"],
            "final_score": final_score,
            "decision": decision,
            "reasoning": reasoning,
            "outreach_message": outreach_message,
        }

    def _call_once(self, leads: list[dict[str, Any]]) -> list[dict]:
        batch_key = tuple(sorted(l["_batch_id"] for l in leads))
        if batch_key not in self._fail_once_ids and random.random() < 0.05:
            self._fail_once_ids.add(batch_key)
            raise LLMError("simulated transient error (rate limited)")
        return [self._judge_one(lead) for lead in leads]

    def score_and_message_batch(self, leads: list[dict[str, Any]]) -> list[dict]:
        return _with_retry(
            lambda: self._call_once(leads),
            self.max_retries, self.base_backoff, "Mock batch call",
        )


def get_provider(cfg: dict):
    provider = cfg.get("provider", "mock")
    if provider == "anthropic":
        return AnthropicProvider(cfg)
    if provider == "mock":
        return MockProvider(cfg)
    raise ValueError(f"Unknown api.provider: {provider}")
