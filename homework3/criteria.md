# Validation Criteria — Homework 3

Customized rubric for the Coinbase Spot Reporter Agent 3 briefings. **Different
from the LAB's generic Likert** in two ways: (1) two of the four dimensions are
**deterministic** (grounded in observable artifacts, not subjective ratings),
and (2) the two AI-rated dimensions are tied to specific stakeholder
expectations rather than a generic "quality" scale.

| Dimension | Type | Scale | How it's measured | Benchmark |
|---|---|---|---|---|
| **Numeric grounding** | Deterministic | 0.00–1.00 | Fraction of numbers in Agent 1's text that match a number in the JSON snapshot within ±0.5% tolerance. Computed by `qc_validation._grounded_fraction`. | ≥ 0.60 = passing |
| **Disclaimer compliance** | Deterministic | 0 or 1 | Returns 1 if the executive briefing contains the substring `"not investment advice"` or starts a line with `"Reminder:"`. Computed by `qc_validation.validate_ai_pipeline_result`. | 1 = passing |
| **Stakeholder fit** | AI reviewer | 1 (poor) – 5 (excellent) | A separate LLM (`gpt-oss-120b` on Ollama Cloud) is shown the briefing and the audience label and asked to rate how well the language matches the audience (operational / governance / plain English). | ≥ 4 = passing |
| **Conciseness** | AI reviewer | 1 (verbose) – 5 (very concise) | Same reviewer LLM rates whether the briefing is short, free of redundant phrases, and avoids unnecessary jargon. | ≥ 4 = passing |

## Why this is "qualitative content analysis"

For dimensions 3 and 4, the AI reviewer reads the **content** of each briefing,
not just metadata. Each rating is justified with a one-sentence rationale that
gets logged in `results.csv` (column `review_rationale`). That mirrors the
qualitative-coding tradition where two human raters would read each report and
assign a categorical / ordinal score.

## How this differs from the LAB's Likert scales

| LAB approach | This rubric |
|---|---|
| Single 1–5 scale ("quality") | 4 dimensions, two deterministic + two AI-rated |
| Subjective ratings only | Half the dimensions are objective measurements |
| Generic criterion ("is this good?") | Each dimension is tied to a specific stakeholder requirement |
| One model both writes and rates | Reviewer model is **different** from writer model — reduces self-rating bias |
