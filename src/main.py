"""Daily market snapshot: appends/updates one row in data/daily.csv.

Also saves trimmed SPY/QQQ option chains to data/chains/<TICKER>/<date>.csv
and derives ~30-day ATM IV from them.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import fetch
import iv

ROOT = Path(__file__).resolve().parent.parent
DAILY_CSV = ROOT / "data" / "daily.csv"
NY = ZoneInfo("America/New_York")

# column -> Yahoo ticker
CLOSE_TICKERS = {
    "vix": "^VIX",
    "vix9d": "^VIX9D",
    "vix3m": "^VIX3M",
    "vvix": "^VVIX",
    "nq_close": "NQ=F",
    "ndx_close": "^NDX",
    "spy_close": "SPY",
    "qqq_close": "QQQ",
}
CHAINS_DIR = ROOT / "data" / "chains"
# (ticker, spot column, IV column)
CHAIN_TICKERS = [("SPY", "spy_close", "spy_atm_iv_30d"),
                 ("QQQ", "qqq_close", "qqq_atm_iv_30d")]
COLUMNS = ["date", *CLOSE_TICKERS, "spy_atm_iv_30d", "qqq_atm_iv_30d", "vix_term_ratio"]

log = logging.getLogger("snapshot")


def upsert(row: dict, path: Path = DAILY_CSV) -> None:
    """Insert row, replacing any existing row with the same date."""
    new = pd.DataFrame([row], columns=COLUMNS)
    if path.exists():
        old = pd.read_csv(path, dtype={"date": str})
        old = old[old["date"] != row["date"]]
        df = pd.concat([old, new], ignore_index=True)
    else:
        df = new
    df = df.reindex(columns=COLUMNS).sort_values("date")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, lineterminator="\n")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    today = datetime.now(NY).date()

    if today.weekday() >= 5:
        log.info("%s is a weekend; nothing to do", today)
        return 0

    # Holiday check: no ^VIX bar for today => market was closed.
    vix = fetch.close_on("^VIX", today)
    if vix is None:
        log.info("No ^VIX bar for %s (holiday or data not ready); exiting", today)
        return 0

    row: dict = {"date": today.isoformat(), "vix": vix}
    for col, ticker in CLOSE_TICKERS.items():
        if col == "vix":
            continue
        row[col] = fetch.close_on(ticker, today)

    if row.get("vix") and row.get("vix3m"):
        row["vix_term_ratio"] = round(row["vix"] / row["vix3m"], 4)

    for ticker, spot_col, iv_col in CHAIN_TICKERS:
        spot = row.get(spot_col)
        if spot is None:
            log.warning("%s: no spot price, skipping chain", ticker)
            continue
        try:
            chain = fetch.option_chain(ticker, today, spot)
            if chain is None:
                continue
            out = CHAINS_DIR / ticker / f"{today.isoformat()}.csv"
            out.parent.mkdir(parents=True, exist_ok=True)
            # dte and contractSymbol are derivable (expiry - file date; OCC symbol
            # from ticker/expiry/type/strike), so don't spend repo space on them.
            chain.drop(columns=["dte", "contractSymbol"]).to_csv(out, index=False, lineterminator="\n")
            iv_value, expiry = iv.atm_iv(chain, spot)
            row[iv_col] = iv_value
            log.info("%s: %d contracts -> %s; ATM IV %s (expiry %s)", ticker,
                     len(chain), out.relative_to(ROOT), iv_value, expiry)
        except Exception:
            log.exception("%s: chain/IV step failed", ticker)

    upsert(row)
    missing = [c for c in CLOSE_TICKERS if row.get(c) is None]
    log.info("Wrote %s to %s%s", today, DAILY_CSV.relative_to(ROOT),
             f" (missing: {', '.join(missing)})" if missing else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
