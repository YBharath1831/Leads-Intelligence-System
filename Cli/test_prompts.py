#!/usr/bin/env python3
"""
test_prompts.py
Sanity-checks scoring + LLM judgment on a small, hand-picked sample (one
obvious win, one obvious reject, one ambiguous case) before committing to a
full batch run. This is what "test your prompts on 5-10 leads first" looks
like in practice for this project.

Usage: python test_prompts.py [--provider mock|anthropic]
"""

import argparse
import yaml
from datetime import date
from pathlib import Path

from rubric import score_lead
from llm_client import get_provider

SAMPLE_LEADS = [
    {  # obvious win
        "name": "Yuki Tanaka", "company": "Skylark SaaS Ventures",
        "company_size": "51-200", "industry": "SaaS/Software", "source": "Demo Request",
        "last_interaction_date": "2026-08-24",
        "notes": "Founder, wants to onboard within 2 weeks, has budget ready",
    },
    {  # obvious reject
        "name": "Ben Okafor", "company": "Rivet Industrial Supply",
        "company_size": "1000+", "industry": "Manufacturing", "source": "Cold Outreach List",
        "last_interaction_date": "2026-05-20",
        "notes": "No engagement since initial contact",
    },
    {  # genuinely ambiguous
        "name": "Ahmed Siddiqui", "company": "Coastal Freight Logistics",
        "company_size": "501-1000", "industry": "Logistics", "source": "Trade Show",
        "last_interaction_date": "2026-08-12",
        "notes": "Ops director, interested but says decision is 6+ months out",
    },
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["mock", "anthropic"], default=None)
    parser.add_argument("--config", default=str(Path(__file__).resolve().parent / "config.yaml"))
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    if args.provider:
        cfg["api"]["provider"] = args.provider

    scored = [score_lead(l, cfg["rubric"], date.today()) for l in SAMPLE_LEADS]
    for i, lead in enumerate(scored):
        lead["_batch_id"] = i

    provider = get_provider(cfg["api"])
    results = provider.score_and_message_batch(scored)

    for lead, result in zip(scored, results):
        print("-" * 60)
        print(f"{lead['name']} @ {lead['company']}")
        print(f"  rule_score:  {lead['rule_score']}")
        print(f"  final_score: {result['final_score']}  decision: {result['decision']}")
        print(f"  reasoning:   {result['reasoning']}")
        if result.get("outreach_message"):
            print(f"  message:     {result['outreach_message']}")


if __name__ == "__main__":
    main()
