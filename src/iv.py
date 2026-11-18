"""Implied-vol summaries computed from trimmed option chains."""
from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

MIN_IV = 0.01   # Yahoo reports ~0 IV after hours when bid/ask is 0
MAX_IV = 5.0    # and occasionally absurd values; treat >500% as junk


def atm_iv(chain: pd.DataFrame, spot: float, target_dte: int = 30,
           n_strikes: int = 3) -> tuple[float | None, str | None]:
    """ATM IV for the expiry closest to `target_dte`.

    Averages the call and put IVs at the `n_strikes` strikes nearest spot.
    Returns (iv, expiry_used); (None, None) if no usable quotes.
    """
    if chain is None or chain.empty:
        return None, None
    usable = chain[(chain["dte"] > 0)
                   & chain["impliedVolatility"].between(MIN_IV, MAX_IV)]
    if usable.empty:
        return None, None

    # Pick the expiry closest to target DTE (ties -> the later expiry).
    dtes = usable[["expiry", "dte"]].drop_duplicates()
    dtes = dtes.assign(dist=(dtes["dte"] - target_dte).abs())
    expiry = dtes.sort_values(["dist", "dte"], ascending=[True, False]).iloc[0]["expiry"]

    exp_rows = usable[usable["expiry"] == expiry]
    strikes = pd.Series(exp_rows["strike"].unique())
    nearest = strikes.iloc[(strikes - spot).abs().argsort()[:n_strikes]]
    atm = exp_rows[exp_rows["strike"].isin(nearest)]
    if atm.empty:
        return None, None
    return round(float(atm["impliedVolatility"].mean()), 6), expiry
