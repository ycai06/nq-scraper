# nq-scraper

A daily market snapshot script built with Python, pandas, and yfinance. It records VIX family indexes, Nasdaq-100 index and futures closes, SPY/QQQ closes, and near-30-day at-the-money option implied-volatility estimates.

## Setup

Requires Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run

From the repository root:

```bash
python src/main.py
```

The script updates `data/daily.csv` and saves SPY and QQQ option-chain extracts under `data/chains/`. It only records a new snapshot when today's VIX closing data is available. Data is retrieved via the unofficial Yahoo Finance interface and may be delayed or missing.

The included `data/daily.csv` is a sample historical snapshot from the uploaded project.
