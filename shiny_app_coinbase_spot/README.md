# Coinbase Spot Reporter (App)

This folder contains a small “reporter-style” app that queries **Coinbase Exchange** spot candle data (`GET /products/{product_id}/candles`) and computes rolling metrics like returns, volatility, and relative volume.

## What the app does

- Lets you choose a **market** (example: `BTC-USD`) and **candle granularity**
- Fetches recent candles from the Coinbase Exchange REST API
- Computes:
  - 1-candle return (%)
  - Lookback return (%)
  - Lookback volatility (sample standard deviation of returns)
  - Average and relative USD volume over the lookback window
  - Distance from lookback high/low
- Displays results as:
  - A price line chart
  - A volume bar chart
  - A formatted table of computed metrics

## API requirements

- This specific endpoint is **public** and does **not** require an API key.
- If you later switch to a private endpoint, you can add `.env` handling.

## Data summary

The API data is stored as a table of Coinbase candle records plus calculated market metrics.

| Column name | Data type | Brief description |
| --- | --- | --- |
| `start_time_utc` | datetime | Start time of the candle in UTC |
| `low_price_raw` | float | Lowest price during the candle period |
| `high_price_raw` | float | Highest price during the candle period |
| `open_price_raw` | float | Opening price of the candle |
| `latest_close` | float | Closing price of the candle |
| `usd_volume_1h` | float | Trading volume converted to approximate USD value |
| `return_1h_pct` | float | Percent return from the previous candle to the current candle |
| `return_lookback_pct` | float | Percent return over the selected lookback window |
| `volatility_lookback_pct` | float | Sample standard deviation of returns over the lookback window |
| `avg_usd_volume_lookback` | float | Average USD trading volume over the lookback period |
| `relative_volume_lookback` | float | Current volume compared with average lookback volume |
| `high_lookback` | float | Highest price in the lookback window |
| `low_lookback` | float | Lowest price in the lookback window |
| `range_lookback_pct` | float | Percent range between lookback high and low |
| `distance_from_lookback_high_pct` | float | Percent distance from current close to lookback high |
| `distance_from_lookback_low_pct` | float | Percent distance from current close to lookback low |

## Technical details

This project uses the public Coinbase Exchange candles endpoint to fetch spot market data, process it with Python, and display the results in either a Streamlit dashboard or an AI-generated report. The main packages are `requests`, `pandas`, `streamlit`, `python-dotenv`, `markdown`, and `python-docx`.

Important files:
- `coinbase_query.py`: fetches Coinbase candles and computes rolling metrics
- `app.py`: Streamlit dashboard (market UI + optional 3-agent Ollama briefing)
- `agent_pipeline.py`: **App V2** — sequential agents (data + tools, risk, executive) via Ollama Cloud `/api/chat`
- `market_agent_tools.py`: **tool calling** definitions + executor (`fetch_market_metrics`, `search_playbook`)
- `rag_retrieval.py`: lightweight **RAG** over `data/knowledge_base.md`
- `qc_validation.py`: **App V3** — dataframe checks + AI output heuristics for QC evidence
- `data/knowledge_base.md`: playbook text for retrieval
- `06_ai_reporter.py`: standalone AI reporting script (older path)
- `03_ollama_cloud.py` / `04_openai.py` / `05_reporting.py`: examples and report export

### App V2 / V3 (course alignment)

- **Multi-agent orchestration:** Agent 1 (tool-using data analyst) → Agent 2 (risk/regime) → Agent 3 (executive brief + disclaimer).
- **Tool calling:** JSON snapshot of the active dataframe + config through `fetch_market_metrics`.
- **RAG:** `search_playbook` retrieves ranked sections from `data/knowledge_base.md` (token overlap; swap for embeddings later if you want).
- **Production / QC signals:** pre-AI dataframe validation table; post-AI checklist (tool usage, length, numeric grounding hints). Optional env `COINBASE_APP_PASSWORD` adds a simple gate before the UI.
- **Deploy:** course docs often say “Shiny”; this implementation is **Streamlit** — confirm with your instructor or wrap via `shinywidgets`/hosting policy. For deployment, set `OLLAMA_*` in the host **Secrets** / environment (see `env_pref` in `app.py`).

## Installation

From the repo root, create and activate a virtual environment, then install dependencies:

```bash
cd shiny_app_coinbase_spot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

(`requirements.txt` includes `python-dotenv`. Add `markdown` / `python-docx` only if you use `05_reporting.py` / `06_ai_reporter.py`.)
## Usage instructions

1. Create a `.env` file inside `shiny_app_coinbase_spot` if you need model API keys.
2. Add your keys in this format:

```bash
OLLAMA_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
```

3. Make sure `.env` is listed in `.gitignore` so you do not commit your keys.
4. Run the Streamlit dashboard:

```bash
cd shiny_app_coinbase_spot
streamlit run app.py
```

5. Run the AI reporter:

```bash
cd shiny_app_coinbase_spot
python 06_ai_reporter.py
```

6. Optional test scripts:

```bash
python 03_ollama_cloud.py
python 04_openai.py
python 05_reporting.py
```

The dashboard lets you set the market and candle settings in the sidebar. The AI reporter fetches Coinbase data, summarizes the key metrics, sends them to the model, and saves the final report as Markdown.

## Troubleshooting

- If you get **HTTP 4xx** errors:
  - Double-check `product_id` (example: `BTC-USD`)
  - Try a different granularity
- If you get **no rows** back:
  - Try a larger number of candles
  - Try a more liquid market (like `BTC-USD` or `ETH-USD`)

## Screenshots

Add your screenshots here for submission:

- App UI running
- Successful query execution (table + charts visible)
- Any error handling case (optional but helpful)
