# Homework 3 — AI Report Validation System

> Customized validator + statistical experiment comparing three Agent 3 prompt
> variants on the Coinbase Spot Reporter (`shiny_app_coinbase_spot/`).

## Experimental design

- Hold the data and Agents 1 + 2 constant. Only swap **Agent 3's system prompt**.
- Three prompt variants (see `prompts.py`):
  - **Prompt A — production**: current audience-aware 3-line briefing with disclaimer.
  - **Prompt B — minimal**: "Summarize the risk analysis in 3 sentences."
  - **Prompt C — verbose**: "Write a thorough multi-paragraph executive summary."
- For each variant, run **20 reports**. Total = 60 generated briefings.
- Each report scored on **4 dimensions** (see `criteria.md`):
  1. Numeric grounding (deterministic, 0.00–1.00).
  2. Disclaimer compliance (deterministic, 0 or 1).
  3. Stakeholder fit (AI reviewer, 1–5 Likert).
  4. Conciseness (AI reviewer, 1–5 Likert).
- Statistical test: **one-way ANOVA per dimension**.
  - H₀: μ_A = μ_B = μ_C
  - H₁: at least one mean differs
  - Reject H₀ at α = 0.05 if p < 0.05.

## Files

| File | Purpose |
|---|---|
| `prompts.py` | Definitions of Agent 3 prompts A, B, C. |
| `llm_reviewer.py` | LLM-as-reviewer that scores stakeholder fit + conciseness on 1–5. |
| `run_experiment.py` | Generates 60 briefings, writes `results.csv`. |
| `analyze.py` | Loads `results.csv`, runs ANOVA, saves `boxplot.png`. |
| `criteria.md` | Validation criteria table for the docx. |

## How to run

```bash
cd shiny_app_coinbase_spot
source .venv/bin/activate              # the same venv as the app
pip install -r requirements.txt        # streamlit, pandas, requests, dotenv
pip install scipy matplotlib           # only needed for HW3 analysis

# OLLAMA_API_KEY must be set (in shiny_app_coinbase_spot/.env or your shell)
cd ..
python homework3/run_experiment.py     # ~30 minutes (60 model calls)
python homework3/analyze.py            # ~5 seconds; prints ANOVA + saves boxplot.png
```

Outputs land in `homework3/`:

- `results.csv` (60 rows × 4 score columns + prompt + run_id)
- `anova_results.txt` (test statistic + p-value per dimension)
- `boxplot.png` (per-dimension comparison across prompts)

## Reusing the shiny app

`run_experiment.py` imports directly from `shiny_app_coinbase_spot/`:

- `agent_pipeline.run_three_agent_pipeline` — produces the 3-agent briefing
- `qc_validation.validate_ai_pipeline_result` — gives the deterministic scores
- `coinbase_query.fetch_coinbase_product_candles` — produces the input data

Nothing in the shiny app is modified.
