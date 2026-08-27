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
