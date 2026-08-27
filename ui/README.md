# Lead Intelligence System - Streamlit UI

This is an interactive web interface for the Lead Intelligence System built with Streamlit.

## Features

- Upload CSV files with lead data
- Configure LLM provider (mock for testing, anthropic for real API)
- View detailed scoring and decision breakdowns
- Generate personalized outreach messages for qualified leads
- Export results as JSON or CSV
- Filter and search through results

## How to Run

### Option 1: Using the launch script (recommended)

```bash
# Activate the virtual environment if you have one
# .venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux

# Run the UI
python launch.py
```

### Option 2: Direct Streamlit command

```bash
streamlit run app.py
```

### Option 3: Using the virtual environment's Python

```bash
# From the ui directory
..\.venv\Scripts\python.exe -m streamlit run app.py
```

## Dependencies

The UI requires additional dependencies beyond the base system:
- streamlit>=1.28.0

These are listed in `ui/requirements.txt`. Install them with:

```bash
pip install -r ui/requirements.txt
```

## Configuration

The UI uses the same configuration system as the command-line version:
- Upload a custom `config.yaml` file via the sidebar
- Or it will use the default `config.yaml` from the parent directory if available
- Configuration controls scoring rubric weights and API settings

## LLM Providers

- **Mock**: Default provider, runs completely offline with deterministic responses (no API key needed)
- **Anthropic**: Requires setting `ANTHROPIC_API_KEY` environment variable or entering it in the sidebar

## Data Requirements

Your CSV must include these columns:
- `name`: Contact person's name
- `company`: Company name
- `company_size`: Company size (e.g., "51-200", "201-1000")
- `industry`: Industry sector
- `source`: Lead source (e.g., "referral", "demo request", "cold list")
- `last_interaction_date`: Date of last contact (YYYY-MM-DD format)
- `notes`: Optional free-text notes from interactions

## Decision Logic

- ✅ **Qualified**: Final score ≥ 7.0
- ❌ **Rejected**: Final score ≤ 4.0  
- 🔍 **Review**: Scores between 4.0 and 7.0 (or ambiguous signals)

## Output

Results can be viewed interactively in the browser and exported as:
- JSON report (`lead_qualification_report.json`)
- CSV report (`lead_qualification_report.csv`)

## Notes

This UI provides the same core functionality as the command-line version (`main.py`) but with an intuitive graphical interface. All lead processing logic is reused from the existing codebase to ensure consistency.