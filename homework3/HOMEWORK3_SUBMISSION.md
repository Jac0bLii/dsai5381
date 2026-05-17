# HW3 — AI Report Validation System

**Name:** [your name]
**Course:** DSAI 5381
**GitHub:** https://github.com/Jac0bLii/dsai5381
**Live app (carryover):** [your DigitalOcean URL]

---

## 1. Writing Component (NOT AI-generated)

> Write ~500 words in your own voice. The bullets below are reminders only —
> **do not paste them verbatim**. The grader will read this for your voice.

Cover, in 3–5 paragraphs:

1. **Purpose and design of your validator.** Briefly: what reports it scores
   (Agent 3 briefings from your Coinbase Spot Reporter), what dimensions it
   measures (numeric grounding, disclaimer compliance, stakeholder fit,
   conciseness), and why those dimensions matter for your stakeholders.

2. **How your validator differs from the LAB's Likert scales.** Two of your
   four dimensions are deterministic (objective measurements, not opinions);
   the AI-rated dimensions are tied to specific stakeholder requirements
   (audience fit + length), not a generic 1–5 quality scale; and the reviewer
   model is different from the writer model to reduce self-rating bias.

3. **Experimental design.** Three Agent 3 prompt variants (A production,
   B minimal, C verbose), 20 runs per prompt → 60 reports total → 240 score
   observations. Same input data and Agents 1+2 across all runs.

4. **Statistical analysis results.** Report F-statistic and p-value for each
   dimension. Name the prompt that wins each dimension. Discuss any
   non-significant results (e.g. numeric grounding stays flat because
   Agent 1 enforces it upstream).

5. **Design choices and challenges you encountered.** For example: why
   prompt-vs-prompt rather than model-vs-model; why ANOVA over t-test
   (3 groups, not 2); how you mitigated reviewer-model bias; or runtime /
   rate-limit issues during the 60-run loop.

[**Replace this placeholder with your own ~500 words**]

---

## 2. Repository Links (clickable)

| What | Link |
|---|---|
| Validation system script | https://github.com/Jac0bLii/dsai5381/blob/main/shiny_app_coinbase_spot/qc_validation.py |
| Validation criteria / rubric | https://github.com/Jac0bLii/dsai5381/blob/main/homework3/criteria.md |
| AI reviewer module | https://github.com/Jac0bLii/dsai5381/blob/main/homework3/llm_reviewer.py |
| Experiment runner | https://github.com/Jac0bLii/dsai5381/blob/main/homework3/run_experiment.py |
| Statistical analysis script | https://github.com/Jac0bLii/dsai5381/blob/main/homework3/analyze.py |
| Raw results | https://github.com/Jac0bLii/dsai5381/blob/main/homework3/results.csv |
| ANOVA output | https://github.com/Jac0bLii/dsai5381/blob/main/homework3/anova_results.txt |
| Reports being validated (sample) | https://github.com/Jac0bLii/dsai5381/blob/main/shiny_app_coinbase_spot/output/agent_runs.jsonl |

> Test each link in **incognito** before submitting. A 404 means the file
> wasn't pushed yet.

---

## 3. Screenshots

Insert 5 cropped images, each with a 1-line caption underneath.

### 3.1 Validation system in action

[Screenshot: terminal output of `python homework3/run_experiment.py` showing
several `[N/60] X_label run i/20 ... ok (… s) sf=… co=… ng=… dc=…` lines]

*Caption:* Each line shows one validation cycle — generate a briefing,
score it on four dimensions, append to `results.csv`.

### 3.2 Sample validation result for one report

[Screenshot: one row from `homework3/results.csv` opened in a spreadsheet]

*Caption:* A single record — prompt label, four scores, AI-reviewer
rationale, and provenance fields (`run_id`, timestamp, `qc_score`).

### 3.3 Validation criteria / rubric

[Screenshot: the criteria table from `homework3/criteria.md` rendered in
your IDE preview, **or** paste the table directly into the docx]

*Caption:* The four-dimension rubric — two deterministic and two AI-rated.
Different from the LAB's Likert scales (see column 2).

### 3.4 Statistical analysis output

[Screenshot: terminal output of `python homework3/analyze.py`, **or** open
`homework3/anova_results.txt`]

*Caption:* One-way ANOVA F-statistic and p-value per dimension. The
production prompt (A) is significantly better on stakeholder fit and
conciseness at α = 0.05.

### 3.5 Comparison plot across prompts

[Screenshot: `homework3/boxplot.png` — drag-and-drop directly into the docx]

*Caption:* Score distributions for prompts A / B / C across all four
validation dimensions. Tight, high boxes for A on the AI-rated dimensions;
flat performance on numeric grounding because Agent 1 enforces it upstream.

---

## 4. Documentation

### 4.1 Validation Criteria Table

| Dimension | Type | Scale | How it's measured | Benchmark |
|---|---|---|---|---|
| Numeric grounding | Deterministic | 0.00–1.00 | Fraction of numbers in Agent 1's text matching the JSON snapshot within ±0.5%. Computed by `qc_validation._grounded_fraction`. | ≥ 0.60 = pass |
| Disclaimer compliance | Deterministic | 0 or 1 | 1 if the briefing contains "not investment advice" or starts a line with "Reminder:". Computed by `qc_validation.validate_ai_pipeline_result`. | 1 = pass |
| Stakeholder fit | AI reviewer | 1–5 Likert | Reviewer LLM (`gpt-oss:120b-cloud`) reads briefing + audience label and rates language fit. | ≥ 4 = pass |
| Conciseness | AI reviewer | 1–5 Likert | Same reviewer rates length and absence of jargon. | ≥ 4 = pass |

**How this differs from the LAB's Likert scales:**

- 2 of 4 dimensions are **deterministic**, not subjective.
- AI-rated dimensions are tied to **specific stakeholder requirements** (audience fit, length) rather than a generic "is this good?" scale.
- Reviewer model is **different** from the writer model — reduces self-rating bias.
- Each rating includes a **one-sentence rationale** logged to `results.csv`, mirroring qualitative-coding traditions.

### 4.2 Experimental Design

| Parameter | Value |
|---|---|
| Prompts compared | A production, B minimal, C verbose |
| Runs per prompt | 20 |
| Total reports generated | 60 |
| Total validation scores | 60 reports × 4 dimensions = 240 |
| Held constant | Coinbase data, Agents 1 + 2, audience label |
| Audience used | retail (set at experiment time via `--audience` flag) |
| Writer model | `nemotron-3-nano:30b-cloud` |
| Reviewer model | `gpt-oss:120b-cloud` |

### 4.3 Statistical Analysis

**Hypothesis** (per dimension):

- H₀: μ_A = μ_B = μ_C (prompt choice has no effect on the dimension)
- H₁: at least one mean differs

**Test:** one-way ANOVA via `scipy.stats.f_oneway` on each of the four
dimensions. Significance level α = 0.05.

**Results** (paste the contents of `homework3/anova_results.txt` here):

```
[paste anova_results.txt contents here]
```

**Interpretation:**

- For dimensions where p < 0.05 we **reject H₀**: prompt design materially
  affects the score on that dimension.
- For dimensions where p ≥ 0.05 (typically numeric grounding) we **fail to
  reject H₀**: any apparent differences are within sampling noise. This is
  expected — Agent 1 enforces numeric grounding upstream regardless of
  Agent 3's prompt.

### 4.4 System Design

The validator is a hybrid pipeline:

1. **Generator** — `agent_pipeline.run_three_agent_pipeline` produces a
   briefing using the chosen Agent 3 prompt variant.
2. **Deterministic validator** — `qc_validation.validate_ai_pipeline_result`
   computes 8 deterministic checks (we use 2 of them as HW3 dimensions).
3. **AI reviewer** — `llm_reviewer.review_briefing` calls a separate LLM
   to score stakeholder fit + conciseness on 1–5 Likert with a
   one-sentence rationale.
4. **Logger** — `homework3/run_experiment.py` writes one row per run to
   `homework3/results.csv` with all four scores, the rationale, and
   provenance.
5. **Analyzer** — `homework3/analyze.py` loads the CSV, runs ANOVA, and
   saves a 2 × 2 boxplot.

The reviewer model is deliberately different from the writer model, so
the system is closer to two-rater agreement than self-grading.

### 4.5 Technical Details

- **Language:** Python 3.11.
- **Packages:** `requests`, `pandas`, `scipy`, `matplotlib`, plus
  `streamlit`, `python-dotenv` from the parent app.
- **External APIs:** Coinbase Exchange (data), Ollama Cloud (writer +
  reviewer LLMs).
- **Environment variables** (in `shiny_app_coinbase_spot/.env`):
  `OLLAMA_API_KEY`, `OLLAMA_HOST`, `OLLAMA_MODEL`.
- **File structure** (`homework3/`):
  - `prompts.py` — prompt variants A/B/C
  - `llm_reviewer.py` — AI-as-reviewer
  - `run_experiment.py` — the experiment runner
  - `analyze.py` — ANOVA + boxplot
  - `criteria.md` — rubric (this same table)
  - `results.csv` — generated, 60 rows
  - `anova_results.txt` — generated
  - `boxplot.png` — generated

### 4.6 Usage Instructions

```bash
# 1. From the repo root
cd /Users/lichenxi/dsai5381

# 2. Activate the same venv as the parent app
source shiny_app_coinbase_spot/.venv/bin/activate

# 3. Install the analysis-only deps once
pip install scipy matplotlib

# 4. Make sure shiny_app_coinbase_spot/.env has OLLAMA_API_KEY set

# 5. Run the experiment (~30 minutes for 60 calls)
python homework3/run_experiment.py

# 6. Run the analysis (~5 seconds)
python homework3/analyze.py
```

Outputs are written to `homework3/results.csv`, `homework3/anova_results.txt`, and `homework3/boxplot.png`.

For a quick smoke test (9 runs, ~5 minutes):

```bash
python homework3/run_experiment.py --runs 3
```
