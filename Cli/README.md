# Lead Intelligence System

Auto-qualifies inbound leads, scores and prioritizes them, and drafts a
personalized first-touch message for each qualified lead — so the sales team
opens a report instead of 1,200 raw rows.

## How to run

```bash
pip install -r Cli/requirements.txt

# Default: runs in mock mode, no API key needed, fully reproducible
python Cli/main.py --input leads.csv --output-prefix output_report

# To hit the real Claude API instead of the mock:
export ANTHROPIC_API_KEY=sk-...
python Cli/main.py --input leads.csv --provider anthropic

# Sanity-check scoring + prompts on 3 hand-picked leads before a full run:
python Cli/test_prompts.py
```

Outputs `output_report.json` (full detail) and `output_report.csv` (flat,
spreadsheet-friendly) in the working directory.

**Why mock mode exists and is the default:** this environment has no network
access, so I couldn't validate a live key end-to-end. `MockProvider` in
`llm_client.py` implements the *identical* interface as `AnthropicProvider` —
same batching, same retry path, same output shape — using rule-based judgment
instead of a model call, so the full pipeline (including the retry/backoff
logic, which it deliberately fails ~5% of the time to exercise) is runnable
and verifiable end to end. Switching to a real model is a one-line config
change (`api.provider: anthropic`) plus an API key; no code changes needed.

## The qualification rubric

Five weighted factors (weights in `config.yaml`, easy to retune): **company
size fit** (25%) and **industry fit** (25%) against the target ICP,
**engagement recency** (20%, days since last touch), **source quality** (15%,
referral > demo request > ... > cold list), and a **budget/timeline signal**
(15%) pulled from the free-text notes field. These combine into a rule-based
`rule_score` (0–10) first — fast, deterministic, and auditable. The LLM step
then reads the full notes text and can nudge that score up or down, but has
to justify the move in `reasoning`. Final decision: **≥7 qualified, ≤4
rejected, in between → review**. Leads with strong negative notes signals
("no budget", "just researching") are force-flagged for review regardless of
score, and any lead missing a required field is never auto-qualified — it's
kicked to review instead.

## Known limitations / edge cases

- **`notes` is an assumed column.** The brief lists name/company/size/
  industry/source/last-interaction-date; I added a free-text `notes` field
  (source-call or intake-form summary) because budget/timeline signal is one
  of the five rubric factors and needs *some* text to read. Without it, that
  factor and message personalization would have nothing to work from.
- **Mock mode's judgment is a keyword heuristic**, not real language
  understanding — it will miss nuance a real model would catch (sarcasm,
  implied urgency, compound signals). It's a stand-in for demonstrating the
  pipeline, not a claim about output quality.
- **Batch-level failure fallback is coarse.** If a batch fails after all
  retries, every lead in that batch drops to rule-score-only and gets
  flagged "review" — safer than guessing, but means one bad batch inflates
  the review queue rather than isolating just the leads that actually needed
  it.
- **Company-size and industry are treated as fixed enumerated bands** (see
  `config.yaml`). A value outside every known band gets a default mid-score
  rather than crashing, but it's not intelligently handled.
- **No dedup.** Duplicate leads across sources aren't merged — the stress
  test run treated 4 copies of the same lead as 4 separate leads.
- **Priority ranking is score-then-recency only** — it doesn't account for
  deal-size potential (e.g., company size beyond the "fit" band) or rep
  capacity/territory.
