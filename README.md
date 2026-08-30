# Lead Intelligence System

This project qualifies and prioritizes sales leads using a deterministic rubric followed by an optional LLM judgment. It includes two independent interfaces:

- `Cli/` - command-line batch processor.
- `ui/` - Streamlit web interface.

The two implementations keep their own application code and configuration, so changes to the UI do not modify the CLI.

## Project structure

```text
FDE_Project/
|-- Cli/                    # Command-line application
|   |-- main.py
|   |-- rubric.py
|   |-- llm_client.py
|   |-- config.yaml
|   |-- test_prompts.py
|   |-- requirements.txt
|   `-- README.md
|-- ui/                     # Streamlit application
|   |-- app.py
|   |-- launch.py
|   |-- rubric.py
|   |-- llm_client.py
|   |-- config.yaml
|   |-- requirements.txt
|   `-- README.md
|-- leads.csv               # Default input dataset
|-- leads_training.csv      # Development dataset
|-- leads_testing.csv       # Edge-case dataset
|-- DATA_README.md          # Dataset documentation
|-- output_report.json      # Generated detailed report
`-- output_report.csv       # Generated flat report
```

## Run the CLI

From the project root:

```powershell
pip install -r Cli\requirements.txt
python Cli\main.py
```

The default command reads `leads.csv`, uses `Cli/config.yaml`, and writes `output_report.json` and `output_report.csv` in the project root.

Custom example:

```powershell
python Cli\main.py --input leads_testing.csv --output-prefix testing_report
```

For the real Anthropic provider, set `ANTHROPIC_API_KEY` and run:

```powershell
python Cli\main.py --provider anthropic
```

See [Cli/README.md](Cli/README.md) for scoring, prompt-testing, and limitation details.

## Run the Streamlit UI

From the project root:

```powershell
pip install -r ui\requirements.txt
python ui\launch.py
```

Alternatively:

```powershell
streamlit run ui\app.py
```

Open `http://localhost:8501`, upload a CSV, choose the mock or Anthropic provider, and process the leads. See [ui/README.md](ui/README.md) for UI-specific instructions.

## Input columns

CSV input must include:

- `name`
- `company`
- `company_size`
- `industry`
- `source`
- `last_interaction_date`

The optional `notes` field improves budget/timeline scoring and outreach personalization. Dates should use `YYYY-MM-DD`.

## Providers

- `mock` is the default and runs locally without an API key.
- `anthropic` uses the configured Claude model and requires `ANTHROPIC_API_KEY`.

Both interfaces default to their own `config.yaml` file.

## Qualification rubric

Each lead receives a deterministic score from 0 to 10 using five weighted factors: company-size fit, industry fit, engagement recency, source quality, and budget/timeline signals found in the notes. The LLM then reviews the lead context and may adjust that score within the configured limits while providing a reason; scores of 7 or higher are qualified, scores of 4 or lower are rejected, and scores between those thresholds require human review. Leads with missing required data or configured negative signals are routed to review instead of being automatically qualified.

## Known limitations and edge cases

- Mock mode uses keyword heuristics rather than real language understanding, so it may miss nuance, implied intent, sarcasm, or conflicting signals.
- Scoring depends on the exact company-size bands, industry names, and source labels configured in each interface. Unknown values receive conservative fallback scores rather than being inferred automatically.
- Budget and timeline scoring depends on the optional `notes` column. Missing or sparse notes reduce personalization quality and may leave otherwise promising leads ambiguous.
- Invalid or missing required fields are handled conservatively and routed to human review, but the system does not attempt to repair or enrich the data.
- Duplicate contacts are processed as separate leads because the pipeline does not currently perform deduplication or identity matching.
- If an LLM batch fails after all retries, every lead in that batch falls back to its rule score and is marked for human review.
- Outreach messages are generated from supplied lead data and should be reviewed before sending, particularly when notes contain sensitive, unclear, or outdated information.
- Priority ranking is primarily based on score and recency; it does not account for sales territory, representative capacity, expected contract value, or existing account ownership.
