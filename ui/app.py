#!/usr/bin/env python3
"""
Lead Intelligence System - Streamlit UI
Interactive web interface for lead qualification, scoring, and outreach message generation.
"""

import streamlit as st
import pandas as pd
import json
import yaml
import tempfile
import os
from pathlib import Path
from datetime import date

from rubric import score_lead
from llm_client import get_provider, LLMError

REQUIRED_COLUMNS = ["name", "company", "company_size", "industry", "source", "last_interaction_date"]


def process_leads(df, config):
    """Run the working CLI scoring and batched LLM flow for a DataFrame."""
    missing_cols = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {', '.join(missing_cols)}")
    if df.empty:
        raise ValueError("The uploaded CSV contains no leads.")

    scored_leads = []
    for batch_id, (_, row) in enumerate(df.iterrows()):
        lead = {
            key: (str(value) if pd.notna(value) else "").strip()
            for key, value in row.items()
        }
        scored = score_lead(lead, config["rubric"], date.today())
        scored["_batch_id"] = batch_id
        scored_leads.append(scored)

    provider_instance = get_provider(config["api"])
    batch_size = max(1, int(config["api"].get("batch_size", 10)))
    llm_results_by_id = {}
    for start in range(0, len(scored_leads), batch_size):
        batch = scored_leads[start:start + batch_size]
        try:
            batch_results = provider_instance.score_and_message_batch(batch)
        except LLMError as exc:
            batch_results = [{
                "id": lead["_batch_id"],
                "final_score": lead["rule_score"],
                "decision": "review",
                "reasoning": f"LLM call failed after retries ({exc}); needs human review.",
                "outreach_message": None,
            } for lead in batch]
        for result in batch_results:
            llm_results_by_id[result["id"]] = result

    final_results = []
    internal_fields = {"_batch_id", "factor_scores", "rule_score", "days_since_contact",
                       "missing_fields", "forced_review"}
    for lead in scored_leads:
        llm_result = llm_results_by_id.get(lead["_batch_id"], {})
        decision = llm_result.get("decision", "review")
        reasoning = llm_result.get("reasoning", "No LLM result returned; needs human review.")
        if lead["missing_fields"] and decision == "qualified":
            decision = "review"
            reasoning += f" [Forced to review: missing fields {lead['missing_fields']}]"
        final_results.append({
            "lead": {key: value for key, value in lead.items() if key not in internal_fields},
            "rule_score": lead["rule_score"],
            "rule_breakdown": lead["factor_scores"],
            "final_score": float(llm_result.get("final_score", lead["rule_score"])),
            "decision": decision,
            "reasoning": reasoning,
            "outreach_message": llm_result.get("outreach_message"),
        })
    return final_results

# Page configuration
st.set_page_config(
    page_title="Lead Intelligence System",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Title and description
st.title("🎯 Lead Intelligence System")
st.markdown("""
Auto-qualifies inbound leads, scores and prioritizes them, and drafts personalized first-touch messages.
Upload a CSV of leads to get started.
""")

# Sidebar for configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Provider selection
    provider = st.selectbox(
        "LLM Provider",
        options=["mock", "anthropic"],
        index=0,
        help="Use 'mock' for offline testing (no API key needed) or 'anthropic' for real Claude API"
    )
    
    if provider == "anthropic":
        api_key = st.text_input(
            "Anthropic API Key",
            type="password",
            help="Set your ANTHROPIC_API_KEY environment variable or enter it here"
        )
        if api_key:
            os.environ["ANTHROPIC_API_KEY"] = api_key
    
    # Configuration file upload
    config_file = st.file_uploader(
        "Upload config.yaml",
        type=['yaml', 'yml'],
        help="Configuration file for scoring rubric and API settings"
    )
    
    # Load config
    if config_file is not None:
        config = yaml.safe_load(config_file)
        st.success("Configuration loaded!")
    else:
        # Try to load default config
        default_config_path = Path(__file__).parent / "config.yaml"
        if default_config_path.exists():
            with open(default_config_path, 'r') as f:
                config = yaml.safe_load(f)
            st.info("Using default configuration")
        else:
            st.warning("No configuration file found. Using defaults.")
            config = {
                "api": {"provider": "mock"},
                "rubric": {
                    "weights": {
                        "company_size_fit": 0.25,
                        "industry_fit": 0.25,
                        "engagement_recency": 0.20,
                        "source_quality": 0.15,
                        "budget_timeline": 0.15
                    }
                }
            }

# The sidebar selection overrides the provider from either configuration source.
config.setdefault("api", {})["provider"] = provider

# Main content area
tab1, tab2, tab3 = st.tabs(["📤 Upload & Process", "📊 Results", "📋 About"])

with tab1:
    st.header("Upload Leads CSV")
    
    uploaded_file = st.file_uploader(
        "Choose a CSV file",
        type=['csv'],
        help="CSV must contain columns: name, company, company_size, industry, source, last_interaction_date, notes (optional)"
    )
    
    if uploaded_file is not None:
        # Display file info
        file_details = {
            "Filename": uploaded_file.name,
            "FileSize": f"{uploaded_file.size / 1024:.2f} KB"
        }
        st.write("### File Details")
        st.json(file_details)
        
        # Preview the data
        try:
            df_preview = pd.read_csv(uploaded_file)
            st.write("### Data Preview")
            st.dataframe(df_preview.head())
            
            # Reset file pointer for processing
            uploaded_file.seek(0)
            
            # Process button
            if st.button("🚀 Process Leads", type="primary"):
                with st.spinner("Processing leads..."):
                    # Save uploaded file temporarily
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp_file:
                        tmp_file.write(uploaded_file.getvalue())
                        tmp_path = tmp_file.name
                    
                    try:
                        # Load leads
                        leads = []
                        required_columns = ["name", "company", "company_size", "industry", "source", "last_interaction_date"]
                        
                        df = pd.read_csv(tmp_path)
                        missing_cols = [c for c in required_columns if c not in df.columns]
                        
                        if missing_cols:
                            st.error(f"Missing required columns: {missing_cols}")
                        else:
                            # Process each lead
                            results = []
                            progress_bar = st.progress(0)
                            status_text = st.empty()
                            
                            for idx, row in df.iterrows():
                                status_text.text(f"Processing lead {idx + 1} of {len(df)}...")
                                progress_bar.progress((idx + 1) / len(df))
                                
                                lead = {k: (str(v) if pd.notna(v) else "").strip() for k, v in row.items()}
                                
                                # Score with rubric
                                scored_lead = score_lead(lead, config["rubric"], date.today())
                                scored_lead["_batch_id"] = len(results)
                                rule_score = scored_lead["rule_score"]
                                rule_breakdown = scored_lead["factor_scores"]
                                
                                # Prepare for LLM
                                lead_with_score = lead.copy()
                                lead_with_score["rule_score"] = rule_score
                                lead_with_score["rule_breakdown"] = rule_breakdown
                                
                                # Get LLM judgment (in batches for efficiency)
                                # For simplicity in UI, we'll process individually here
                                # In production, you'd want to batch these
                                
                                results.append({
                                    "lead": lead,
                                    "scored_lead": scored_lead,
                                    "rule_score": rule_score,
                                    "rule_breakdown": rule_breakdown
                                })
                            
                            status_text.text("Getting LLM judgments...")
                            
                            # Process in batches using the existing LLM client
                            provider_instance = get_provider(config.get("api", {}))
                            
                            # Convert leads to format expected by LLM client
                            leads_for_llm = []
                            for result in results:
                                leads_for_llm.append(result["scored_lead"])
                            
                            # Get LLM responses in the same batch sizes used by the CLI.
                            llm_results = []
                            batch_size = max(1, int(config["api"].get("batch_size", 10)))
                            for start in range(0, len(leads_for_llm), batch_size):
                                batch = leads_for_llm[start:start + batch_size]
                                try:
                                    llm_results.extend(provider_instance.score_and_message_batch(batch))
                                except LLMError as exc:
                                    llm_results.extend({
                                        "id": lead["_batch_id"],
                                        "final_score": lead["rule_score"],
                                        "decision": "review",
                                        "reasoning": f"LLM call failed after retries ({exc}); needs human review.",
                                        "outreach_message": None,
                                    } for lead in batch)
                            
                            # Combine results
                            final_results = []
                            for i, (rule_result, llm_result) in enumerate(zip(results, llm_results)):
                                scored_lead = rule_result["scored_lead"]
                                decision = llm_result.get("decision", "review")
                                reasoning = llm_result.get("reasoning", "")
                                outreach_message = llm_result.get("outreach_message")
                                if scored_lead.get("missing_fields") or scored_lead.get("forced_review"):
                                    decision = "review"
                                    outreach_message = None
                                    review_causes = []
                                    if scored_lead.get("missing_fields"):
                                        review_causes.append(
                                            f"missing fields {scored_lead['missing_fields']}"
                                        )
                                    if scored_lead.get("forced_review"):
                                        review_causes.append("a configured review signal in the notes")
                                    reasoning = (
                                        reasoning.rstrip() +
                                        f" [Forced to review: {'; '.join(review_causes)}.]"
                                    ).strip()
                                final_results.append({
                                    "lead": rule_result["lead"],
                                    "rule_score": rule_result["rule_score"],
                                    "rule_breakdown": rule_result["rule_breakdown"],
                                    "final_score": llm_result.get("final_score", rule_result["rule_score"]),
                                    "decision": decision,
                                    "reasoning": reasoning,
                                    "outreach_message": outreach_message
                                })
                            
                            # Store results in session state
                            st.session_state['results'] = final_results
                            st.session_state['processed'] = True
                            
                            # Clean up
                            os.unlink(tmp_path)
                            
                            status_text.text("✅ Processing complete!")
                            st.balloons()
                            
                    except Exception as e:
                        st.error(f"Error processing leads: {str(e)}")
                        if 'tmp_path' in locals():
                            try:
                                os.unlink(tmp_path)
                            except:
                                pass
        except Exception as e:
            st.error(f"An error occurred during pipeline execution: {str(e)}")
        finally:
            # Clean up the temporary file safely
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.remove(tmp_path)
with tab2:
    st.header("Results")
    
    if st.session_state.get('processed', False) and 'results' in st.session_state:
        results = st.session_state['results']
        
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        
        qualified_count = sum(1 for r in results if r['decision'] == 'qualified')
        rejected_count = sum(1 for r in results if r['decision'] == 'rejected')
        review_count = sum(1 for r in results if r['decision'] == 'review')
        total_count = len(results)
        
        with col1:
            st.metric("Total Leads", total_count)
        with col2:
            st.metric("Qualified", qualified_count, delta=f"{qualified_count/total_count*100:.1f}%")
        with col3:
            st.metric("Rejected", rejected_count, delta=f"{rejected_count/total_count*100:.1f}%")
        with col4:
            st.metric("Needs Review", review_count, delta=f"{review_count/total_count*100:.1f}%")
        
        # Filter options
        st.subheader("Filter Results")
        col1, col2 = st.columns(2)
        with col1:
            decision_filter = st.multiselect(
                "Decision",
                options=["qualified", "rejected", "review"],
                default=["qualified", "rejected", "review"]
            )
        with col2:
            score_range = st.slider(
                "Score Range",
                min_value=0.0,
                max_value=10.0,
                value=(0.0, 10.0),
                step=0.1
            )
        
        # Filter results
        filtered_results = [
            r for r in results
            if r['decision'] in decision_filter
            and score_range[0] <= r['final_score'] <= score_range[1]
        ]
        
        st.write(f"Showing {len(filtered_results)} of {total_count} leads")
        
        # Display results
        for idx, result in enumerate(filtered_results):
            with st.expander(
                f"{result['lead'].get('name', 'Unknown')} @ {result['lead'].get('company', 'Unknown')} "
                f"- Score: {result['final_score']:.1f} - {result['decision'].upper()}"
            ):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.write("**Lead Information:**")
                    lead_df = pd.DataFrame([
                        {"Field": k, "Value": v} 
                        for k, v in result['lead'].items() 
                        if k not in ['rule_score', 'rule_breakdown']
                    ])
                    st.dataframe(lead_df, hide_index=True)
                    
                    st.write("**Rule-Based Scoring:**")
                    rule_df = pd.DataFrame([
                        {"Factor": k.replace('_', ' ').title(), "Score": v} 
                        for k, v in result['rule_breakdown'].items()
                    ])
                    st.dataframe(rule_df, hide_index=True)
                    st.write(f"*Rule Score: {result['rule_score']:.2f}*")
                
                with col2:
                    st.write("**LLM Judgment:**")
                    st.metric("Final Score", f"{result['final_score']:.1f}")
                    st.write(f"**Decision:** {result['decision'].title()}")
                    
                    if result['reasoning']:
                        st.write("**Reasoning:**")
                        st.info(result['reasoning'])
                    
                    if result['decision'] == 'qualified' and result['outreach_message']:
                        st.write("**Outreach Message:**")
                        st.text_area(
                            "Message",
                            value=result['outreach_message'],
                            height=100,
                            key=f"message_{idx}",
                            label_visibility="collapsed"
                        )
        
        # Export options
        st.subheader("Export Results")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📥 Download JSON Report"):
                # Prepare export data
                export_data = []
                for result in filtered_results:
                    flat_result = {
                        **{f"lead_{k}": v for k, v in result['lead'].items()},
                        "rule_score": result['rule_score'],
                        "final_score": result['final_score'],
                        "decision": result['decision'],
                        "reasoning": result['reasoning'],
                        "outreach_message": result['outreach_message']
                    }
                    # Add rule breakdown
                    for factor, score in result['rule_breakdown'].items():
                        flat_result[f"rule_{factor}"] = score
                    export_data.append(flat_result)
                
                export_df = pd.DataFrame(export_data)
                json_str = export_df.to_json(orient='records', indent=2)
                
                st.download_button(
                    label="Download JSON",
                    data=json_str,
                    file_name="lead_qualification_report.json",
                    mime="application/json"
                )
        
        with col2:
            if st.button("📥 Download CSV Report"):
                # Prepare export data
                export_data = []
                for result in filtered_results:
                    flat_result = {
                        **{f"lead_{k}": v for k, v in result['lead'].items()},
                        "rule_score": result['rule_score'],
                        "final_score": result['final_score'],
                        "decision": result['decision'],
                        "reasoning": result['reasoning'],
                        "outreach_message": result['outreach_message']
                    }
                    # Add rule breakdown
                    for factor, score in result['rule_breakdown'].items():
                        flat_result[f"rule_{factor}"] = score
                    export_data.append(flat_result)
                
                export_df = pd.DataFrame(export_data)
                csv_str = export_df.to_csv(index=False)
                
                st.download_button(
                    label="Download CSV",
                    data=csv_str,
                    file_name="lead_qualification_report.csv",
                    mime="text/csv"
                )
    
    else:
        st.info("👆 Upload and process leads in the first tab to see results here.")

with tab3:
    st.header("About This System")
    
    st.markdown("""
    ### Lead Intelligence System
    
This interactive web interface provides the same functionality as the command-line version but with an intuitive graphical interface.
    
    **Features:**
    - 📤 Upload CSV files with lead data
    - ⚙️ Configure LLM provider (mock for testing, anthropic for real API)
    - 📊 View detailed scoring and decision breakdowns
    - 💌 Generate personalized outreach messages for qualified leads
    - 💾 Export results as JSON or CSV
    - 🔍 Filter and search through results
    
    **How It Works:**
    1. **Rule-Based Scoring**: Each lead is scored against a rubric (company size, industry, engagement recency, source quality, budget/timeline signals)
    2. **LLM Judgment**: The language model reviews the rule score and lead notes to make a final qualification decision
    3. **Personalized Outreach**: For qualified leads, the system generates a customized first-touch message
    
    **Decision Logic:**
    - ✅ **Qualified**: Final score ≥ 7.0
    - ❌ **Rejected**: Final score ≤ 4.0  
    - 🔍 **Review**: Scores between 4.0 and 7.0 (or ambiguous signals)
    
    **Getting Started:**
    1. Go to the "Upload & Process" tab
    2. Upload your leads CSV file
    3. Select your LLM provider (use "mock" for testing without API keys)
    4. Click "Process Leads"
    5. View results in the "Results" tab
    6. Export your reports as needed
    
    **Data Requirements:**
    Your CSV must include these columns:
    - `name`: Contact person's name
    - `company`: Company name
    - `company_size`: Company size (e.g., "51-200", "201-1000")
    - `industry`: Industry sector
    - `source`: Lead source (e.g., "referral", "demo request", "cold list")
    - `last_interaction_date`: Date of last contact (YYYY-MM-DD format)
    - `notes`: Optional free-text notes from interactions
    
    The system is designed to be runnable offline using the mock LLM provider, making it ideal for demos, testing, and environments without internet access.
    """)
    
    # Show sample data format
    with st.expander("📋 See Sample Data Format"):
        sample_data = {
            "name": ["Yuki Tanaka", "Ben Okafor", "Ahmed Siddiqui"],
            "company": ["Skylark SaaS Ventures", "Rivet Industrial Supply", "Coastal Freight Logistics"],
            "company_size": ["51-200", "201-500", "51-200"],
            "industry": ["software", "manufacturing", "transportation"],
            "source": ["referral", "cold list", "demo request"],
            "last_interaction_date": ["2024-01-15", "2023-11-02", "2024-01-10"],
            "notes": [
                "Founder, wants to onboard within 2 weeks, has budget ready",
                "No engagement since initial contact", 
                "Ops director, interested but says decision is 6+ months out"
            ]
        }
        st.dataframe(pd.DataFrame(sample_data))

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #666;'>"
    "Lead Intelligence System • Built with Streamlit • "
    "<a href='https://github.com/your-repo' target='_blank'>View Source</a>"
    "</div>",
    unsafe_allow_html=True
)
