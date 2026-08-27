# Lead Qualification Project - Data Files

This directory contains sample training and testing data for the Lead Intelligence System mini project.

## Files

### `leads_training.csv`
**Purpose:** Primary training dataset for development and testing your qualification system.

- **30 leads** with diverse characteristics
- **Mix of scenarios:** Obvious wins, obvious rejects, and edge cases
- **Industries covered:** SaaS, Finance, Healthcare, Manufacturing, Retail, Logistics, EdTech, FinTech, and more
- **Company sizes:** Startup (1-10), SMB (11-500), Mid-market (501-5000), Enterprise (5000+)
- **Sources:** Inbound demo requests, LinkedIn outreach, referrals, webinar attendees, content downloads, sales calls
- **Interaction recency:** From ~1 month ago to over 1 year ago
- **Data completeness:** All fields populated

**Use this to:**
- Develop your qualification rubric
- Test your LLM prompts
- Validate your scoring logic
- Generate your sample output report

### `leads_testing.csv`
**Purpose:** Edge-case and robustness testing dataset.

- **20 leads** with real-world messiness
- **Edge cases included:**
  - Missing fields (company_size, last_interaction_date, source)
  - Missing names
  - Unknown/unmapped categories
  - Extreme company sizes (1 person, 50,000+ employees)
  - Stale interactions (over 1 year old)
  - Very recent interactions (same day)
  - Invalid or sparse data
- **Goal:** Test error handling, graceful degradation, and edge-case detection

**Use this to:**
- Test robustness of your data validation
- Verify error handling and logging
- Ensure your system flags unclear cases for human review
- Check that missing data doesn't crash the pipeline

## Column Definitions

| Column | Description | Example |
|--------|-------------|---------|
| `name` | Contact name | "Alice Chen" |
| `company` | Company name | "CloudScale AI" |
| `company_size` | Number of employees | 50, or "NA" if unknown |
| `industry` | Business industry | "SaaS", "Healthcare", "Retail" |
| `source` | How lead was acquired | "Inbound demo request", "LinkedIn outreach", "Referral" |
| `last_interaction_date` | Last time we touched base | "2024-01-15" (YYYY-MM-DD) or blank |

## How to Use

1. **Start with training data:** Use `leads_training.csv` to build and refine your system.
2. **Test with full dataset:** Combine both files or run them separately to validate at scale.
3. **Expect messiness in testing data:** The testing file is deliberately imperfect. Your system should handle it gracefully.
4. **Don't hardcode expectations:** Build logic that adapts to real-world data quality issues.

## Notes

- Dates are in `YYYY-MM-DD` format
- Blank/empty cells represent missing data (not the string "NA")
- Company sizes are approximate; use ranges in your rubric
- Sources may vary beyond these examples in production
- Consider your rubric's tolerance for missing data per field

## Quick Stats

**Training Data:**
- Total leads: 30
- Complete records: 30 (100%)
- Date range: 2023-08-30 to 2024-01-20
- Industries: 20 different sectors

**Testing Data:**
- Total leads: 20
- Complete records: ~12 (40%)
- Incomplete/edge cases: ~8 (40%)
- Date range: 2022-06-15 to 2024-01-20
- Intentional problems: Missing names, sizes, dates, sources; extreme values
