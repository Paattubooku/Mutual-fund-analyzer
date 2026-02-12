"""
data/fixtures.py
────────────────
Offline synthetic NAV data generator.

When the MFAPI is unreachable or OFFLINE_MODE is True,
the system falls back to deterministic synthetic NAV data.
This enables:
    1. Development and testing without network access
    2. Repeatable smoke tests with known outputs
    3. CI/CD pipelines in air-gapped environments

The synthetic data uses geometric Brownian motion with
configurable drift and volatility, producing realistic
NAV time-series with weekday-only dates.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np
import pandas as pd

import config
from data.models import SchemeInfo, NAVData


_FIXTURE_SCHEMES = {
    100001: SchemeInfo(
        scheme_code=100001,
        scheme_name="Fixture Flexi Cap Fund - Direct Growth",
        fund_house="Fixture AMC",
        scheme_type="Open Ended Schemes",
        scheme_category="Equity Scheme - Flexi Cap Fund",
    ),
    100002: SchemeInfo(
        scheme_code=100002,
        scheme_name="Fixture Large Cap Fund - Direct Growth",
        fund_house="Fixture AMC",
        scheme_type="Open Ended Schemes",
        scheme_category="Equity Scheme - Large Cap Fund",
    ),
    100003: SchemeInfo(
        scheme_code=100003,
        scheme_name="Fixture Small Cap Fund - Direct Growth",
        fund_house="Fixture AMC",
        scheme_type="Open Ended Schemes",
        scheme_category="Equity Scheme - Small Cap Fund",
    ),
    100099: SchemeInfo(
        scheme_code=100099,
        scheme_name="Fixture Nifty 50 Index Fund - Direct Growth",
        fund_house="Fixture AMC",
        scheme_type="Open Ended Schemes",
        scheme_category="Equity Scheme - Large Cap Fund",
    ),
}


def generate_synthetic_nav(
    scheme_code: int = 100001,
    years: float = None,
    base_nav: float = None,
    annual_drift: float = None,
    annual_vol: float = None,
    seed: Optional[int] = None,
) -> NAVData:
    """Generate a synthetic NAV time-series using geometric Brownian motion."""
    if years is None:
        years = config.FIXTURE_HISTORY_YEARS
    if base_nav is None:
        base_nav = config.FIXTURE_BASE_NAV
    if annual_drift is None:
        annual_drift = config.FIXTURE_ANNUAL_DRIFT
    if annual_vol is None:
        annual_vol = config.FIXTURE_ANNUAL_VOL
    if seed is None:
        seed = scheme_code

    info = _FIXTURE_SCHEMES.get(scheme_code)
    if info is None:
        info = SchemeInfo(
            scheme_code=scheme_code,
            scheme_name=f"Fixture Fund {scheme_code}",
            fund_house="Fixture AMC",
            scheme_type="Open Ended Schemes",
            scheme_category="Equity Scheme - Flexi Cap Fund",
        )

    end_date = dt.date.today()
    start_date = end_date - dt.timedelta(days=int(years * 365.25))
    all_dates = pd.bdate_range(start=start_date, end=end_date)

    n = len(all_dates)
    if n < 10:
        raise ValueError(f"Cannot generate {years}-year fixture: only {n} business days.")

    rng = np.random.RandomState(seed)
    dt_frac = 1.0 / 252
    daily_drift = (annual_drift - 0.5 * annual_vol ** 2) * dt_frac
    daily_vol = annual_vol * np.sqrt(dt_frac)

    log_returns = daily_drift + daily_vol * rng.randn(n)
    log_returns[0] = 0.0

    log_prices = np.cumsum(log_returns)
    navs = base_nav * np.exp(log_prices)
    navs = np.maximum(navs, 1.0)

    series = pd.Series(data=navs, index=all_dates, name="nav", dtype=float)
    return NAVData(scheme_info=info, nav_series=series)


def get_fixture_benchmark_code() -> int:
    """Return the fixture benchmark scheme code."""
    return 100099


def is_fixture_code(scheme_code: int) -> bool:
    """Check if a scheme code is a fixture code."""
    return scheme_code >= 100000
