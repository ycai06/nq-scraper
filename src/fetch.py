"""Thin wrappers around yfinance with retry/backoff.

yfinance is an unofficial Yahoo scraper: it can break, return empty frames,
or get rate-limited. Every call here retries a few times and returns None
on final failure instead of raising, so one bad ticker never kills a run.
"""
from __future__ import annotations

import logging
import time
from datetime import date

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

RETRIES = 3
BACKOFF_SECONDS = 2.0


def _retry(fn, what: str):
    for attempt in range(1, RETRIES + 1):
        try:
            result = fn()
            if result is None or (isinstance(result, pd.DataFrame) and result.empty):
                raise ValueError("empty result")
            return result
        except Exception as exc:  # yfinance raises a grab-bag of exceptions
            log.warning("%s: attempt %d/%d failed: %s", what, attempt, RETRIES, exc)
            if attempt < RETRIES:
                time.sleep(BACKOFF_SECONDS * attempt)
    log.error("%s: giving up after %d attempts", what, RETRIES)
    return None


def history(ticker: str, period: str = "5d") -> pd.DataFrame | None:
    """Daily bars for `ticker`, index converted to plain dates."""
    df = _retry(lambda: yf.Ticker(ticker).history(period=period, auto_adjust=False),
                f"history({ticker})")
    if df is None:
        return None
    df = df.copy()
    df.index = pd.to_datetime(df.index).date
    return df


def close_on(ticker: str, day: date) -> float | None:
    """Close price for `ticker` on `day`, or None if Yahoo has no bar for that day."""
    df = history(ticker)
    if df is None:
        return None
    if day not in df.index:
        log.warning("%s: no bar for %s (latest is %s)", ticker, day, df.index[-1])
        return None
    return round(float(df.loc[day, "Close"]), 4)


CHAIN_COLUMNS = ["expiry", "dte", "type", "strike", "bid", "ask", "last",
                 "volume", "openInterest", "impliedVolatility", "contractSymbol"]


def option_chain(ticker: str, day: date, spot: float,
                 max_dte: int = 60, strike_band: float = 0.15) -> pd.DataFrame | None:
    """Trimmed chain: expiries within `max_dte` days, strikes within ±band of spot.

    Expiries that fail to download are logged and skipped; returns None only
    if nothing at all could be fetched.
    """
    tk = yf.Ticker(ticker)
    expiries = _retry(lambda: list(tk.options) or None, f"options({ticker})")
    if not expiries:
        return None

    lo, hi = spot * (1 - strike_band), spot * (1 + strike_band)
    frames = []
    for exp in expiries:
        dte = (date.fromisoformat(exp) - day).days
        if dte < 0 or dte > max_dte:
            continue
        chain = _retry(lambda: tk.option_chain(exp), f"option_chain({ticker} {exp})")
        if chain is None:
            continue
        for kind, df in (("call", chain.calls), ("put", chain.puts)):
            if df is None or df.empty:
                continue
            df = df[(df["strike"] >= lo) & (df["strike"] <= hi)].copy()
            df = df.rename(columns={"lastPrice": "last"})
            df["expiry"], df["dte"], df["type"] = exp, dte, kind
            frames.append(df)

    if not frames:
        log.error("%s: no option data within %d DTE", ticker, max_dte)
        return None
    out = pd.concat(frames, ignore_index=True).reindex(columns=CHAIN_COLUMNS)
    out["impliedVolatility"] = out["impliedVolatility"].round(6)
    return out.sort_values(["expiry", "type", "strike"]).reset_index(drop=True)
