#!/usr/bin/env python3
"""
Lead Intelligence System
Ingests a CSV of leads, scores them against a rubric, sends batches to an LLM
for judgment + personalized outreach copy, and writes an actionable report.

Usage:
    python Cli/main.py --input leads.csv --config Cli/config.yaml --output-prefix output_report
    python Cli/main.py --input leads.csv --provider anthropic   # override config.yaml

See README.md for the rubric explanation and known limitations.
"""

import argparse
import csv
import json
import logging
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

from rubric import score_lead
from llm_client import get_provider, LLMError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("lead_qualifier")

CLI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CLI_DIR.parent

REQUIRED_COLUMNS = ["name", "company", "company_size", "industry", "source", "last_interaction_date"]


def load_leads(path: str) -> list[dict]:
    """Reads the CSV and returns a list of dicts. Never raises on bad/missing
    cell values -- missing fields are recorded (rubric.py flags them) and
    scored conservatively rather than crashing the run."""
    leads = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing_cols = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing_cols:
            logger.error("Input CSV is missing required columns: %s", missing_cols)
            sys.exit(1)
        for i, row in enumerate(reader):
            row = {k: (v or "").strip() for k, v in row.items()}
            row["_row_num"] = i + 2  # +2: header row + 1-indexing, for human-readable error refs
            leads.append(row)
    if not leads:
        logger.error("No leads found in %s", path)
        sys.exit(1)
    return leads


def make_batches(leads: list[dict], batch_size: int) -> list[list[dict]]:
    return [leads[i:i + batch_size] for i in range(0, len(leads), batch_size)]


def run_batch_with_fallback(provider, batch: list[dict]) -> list[dict]:
    """
    Calls the LLM provider for one batch. If the batch fails even after the
    provider's internal retries, degrade gracefully: fall back to the
    rule-based score alone, mark every lead in the batch "review" with an
    explicit reason, and keep the pipeline moving instead of crashing the
    whole run over one bad batch.
    """
    try:
        return provider.score_and_message_batch(batch)
    except LLMError as e:
        logger.error(
            "Batch of %d leads failed after all retries (%s). "
            "Falling back to rule-based scores; flagging batch for human review.",
            len(batch), e,
        )
        return [
            {
                "id": lead["_batch_id"],
                "final_score": lead["rule_score"],
                "decision": "review",
                "reasoning": f"LLM call failed after retries ({e}); rule-based score only, needs human review.",
                "outreach_message": None,
            }
            for lead in batch
        ]


def build_report(leads: list[dict]) -> dict:
    total = len(leads)
    decisions = Counter(l["decision"] for l in leads)
    qualified_pct = round(100 * decisions.get("qualified", 0) / total, 1) if total else 0.0

    rejection_reasons = Counter()
    for l in leads:
        if l["decision"] == "rejected":
            worst_factor = min(l["factor_scores"], key=lambda k: l["factor_scores"][k])
            rejection_reasons[worst_factor] += 1

    qualified = sorted(
        [l for l in leads if l["decision"] == "qualified"],
        key=lambda l: (-l["final_score"], l.get("days_since_contact") if l.get("days_since_contact") is not None else 9999),
    )
    for rank, l in enumerate(qualified, start=1):
        l["priority_rank"] = rank

    review = [l for l in leads if l["decision"] == "review"]
    rejected = [l for l in leads if l["decision"] == "rejected"]

    def slim(l: dict) -> dict:
        return {
            "name": l.get("name"),
            "company": l.get("company"),
            "company_size": l.get("company_size"),
            "industry": l.get("industry"),
            "source": l.get("source"),
            "decision": l["decision"],
            "rule_score": l["rule_score"],
            "final_score": l["final_score"],
            "priority_rank": l.get("priority_rank"),
            "reasoning": l["reasoning"],
            "outreach_message": l.get("outreach_message"),
            "missing_fields": l.get("missing_fields") or None,
        }

    report = {
        "run_summary": {
            "total_processed": total,
            "qualified": decisions.get("qualified", 0),
            "rejected": decisions.get("rejected", 0),
            "needs_review": decisions.get("review", 0),
            "qualified_pct": qualified_pct,
            "common_rejection_factors": dict(rejection_reasons.most_common()),
        },
        "priority_queue": [slim(l) for l in qualified],
        "needs_human_review": [slim(l) for l in review],
        "rejected": [slim(l) for l in rejected],
        "sample_outreach_messages": [
            {"company": l.get("company"), "name": l.get("name"), "message": l["outreach_message"]}
            for l in qualified[:5] if l.get("outreach_message")
        ],
    }
    return report


def write_outputs(report: dict, output_prefix: str):
    json_path = f"{output_prefix}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    csv_path = f"{output_prefix}.csv"
    rows = report["priority_queue"] + report["needs_human_review"] + report["rejected"]
    fieldnames = ["company", "name", "company_size", "industry", "source",
                  "decision", "rule_score", "final_score", "priority_rank", "reasoning"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    return json_path, csv_path


def print_summary(report: dict):
    s = report["run_summary"]
    print("\n" + "=" * 60)
    print("LEAD QUALIFICATION RUN COMPLETE")
    print("=" * 60)
    print(f"Total processed:   {s['total_processed']}")
    print(f"Qualified:         {s['qualified']}  ({s['qualified_pct']}%)")
    print(f"Rejected:          {s['rejected']}")
    print(f"Needs review:      {s['needs_review']}")
    if s["common_rejection_factors"]:
        print("Top rejection factors:")
        for factor, count in s["common_rejection_factors"].items():
            print(f"  - {factor}: {count}")
    print("\nTop 5 priority leads:")
    for l in report["priority_queue"][:5]:
        print(f"  #{l['priority_rank']} {l['company']} ({l['name']}) -- score {l['final_score']}")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Lead Intelligence System")
    parser.add_argument("--input", default=str(PROJECT_ROOT / "leads.csv"), help="Path to input leads CSV")
    parser.add_argument("--config", default=str(CLI_DIR / "config.yaml"), help="Path to config YAML")
    parser.add_argument("--output-prefix", default=str(PROJECT_ROOT / "output_report"), help="Output file prefix (.json/.csv written)")
    parser.add_argument("--provider", choices=["mock", "anthropic"], help="Override api.provider from config")
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    if args.provider:
        cfg["api"]["provider"] = args.provider

    logger.info("Loading leads from %s", args.input)
    raw_leads = load_leads(args.input)
    logger.info("Loaded %d leads", len(raw_leads))

    today = date.today()
    scored = [score_lead(lead, cfg["rubric"], today) for lead in raw_leads]
    for i, lead in enumerate(scored):
        lead["_batch_id"] = i

    provider = get_provider(cfg["api"])
    batches = make_batches(scored, cfg["api"]["batch_size"])
    logger.info("Sending %d leads to LLM (%s) in %d batches of up to %d",
                len(scored), cfg["api"]["provider"], len(batches), cfg["api"]["batch_size"])

    results_by_id = {}
    for batch_num, batch in enumerate(batches, start=1):
        logger.info("Batch %d/%d (%d leads)", batch_num, len(batches), len(batch))
        results = run_batch_with_fallback(provider, batch)
        for r in results:
            results_by_id[r["id"]] = r

    for lead in scored:
        result = results_by_id.get(lead["_batch_id"])
        if result is None:
            # Defensive fallback: should be unreachable given run_batch_with_fallback,
            # but a run that produces a decision for every single lead matters more
            # than a clever recovery here.
            lead["final_score"] = lead["rule_score"]
            lead["decision"] = "review"
            lead["reasoning"] = "No LLM result returned for this lead; needs manual review."
            lead["outreach_message"] = None
        else:
            lead["final_score"] = result["final_score"]
            lead["decision"] = result["decision"]
            lead["reasoning"] = result["reasoning"]
            lead["outreach_message"] = result.get("outreach_message")

        if lead.get("missing_fields") and lead["decision"] == "qualified":
            # Never auto-qualify a lead we don't have full data on -- kick to review instead.
            lead["decision"] = "review"
            lead["reasoning"] += f" [Forced to review: missing fields {lead['missing_fields']}]"

    report = build_report(scored)
    json_path, csv_path = write_outputs(report, args.output_prefix)
    logger.info("Wrote %s and %s", json_path, csv_path)
    print_summary(report)


if __name__ == "__main__":
    main()
