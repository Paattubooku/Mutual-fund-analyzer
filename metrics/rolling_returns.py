"""
metrics/rolling_returns.py
──────────────────────────
SECTION 1.2 — Rolling Returns

Rolling returns measure CAGR across EVERY possible start date
for a given window length.  Unlike trailing returns (one data
point), rolling returns produce a DISTRIBUTION of thousands of
observations.

This module computes:
    1. Daily rolling CAGR for configurable window lengths
    2. Full distribution statistics (mean, median, min, max, σ, percentiles)
    3. Win rate vs benchmark
    4. Positive return probability
    5. Automated interpretation and quality grading

Public API
----------
    calculate_rolling_returns(nav_data, window_years, step_days=1)
    compare_rolling_returns(fund_nav, benchmark_nav, window_years, step_days=1)
    generate_rolling_report(fund_nav, benchmark_nav=None, windows=None)
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional, List, Tuple

import numpy as np
import pandas as pd

from config import RISK_FREE_RATE
from data.models import (
    NAVData,
    SchemeInfo,
    RollingReturnDistribution,
    RollingReturnTimeSeries,
    RollingReturnReport,
)


# ────────────────────────────────────────────────
# CONFIGURATION: Default rolling windows
# ────────────────────────────────────────────────

DEFAULT_ROLLING_WINDOWS: List[Tuple[str, float]] = [
    ("1 Year",   1.0),
    ("3 Years",  3.0),
    ("5 Years",  5.0),
    ("7 Years",  7.0),
    ("10 Years", 10.0),
]


# ────────────────────────────────────────────────
# CORE ENGINE: Vectorised rolling CAGR
# ────────────────────────────────────────────────

def _compute_rolling_cagr_vectorised(
    nav_series: pd.Series,
    window_days: int,
    step_days: int = 1,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute rolling CAGR using pure NumPy vectorisation.

    Instead of looping through every start date one by one
    (which is slow for 2500+ windows), we use array slicing:

        start_navs = nav_values[start_indices]
        end_navs   = nav_values[end_indices]
        cagr       = (end_navs / start_navs)^(1/years) − 1

    Parameters
    ----------
    nav_series  : pd.Series with DatetimeIndex (sorted ascending)
    window_days : approximate number of calendar days for the window
    step_days   : step size between consecutive windows (1=daily)

    Returns
    -------
    start_dates : np.ndarray of datetime64
    end_dates   : np.ndarray of datetime64
    start_navs  : np.ndarray of float
    cagr_values : np.ndarray of float (as decimals, e.g. 0.15 = 15%)
    """
    dates = nav_series.index.values                     # numpy datetime64
    navs = nav_series.values.astype(np.float64)         # numpy float64
    n = len(navs)

    # ── Build mapping: for each trading day index i, find
    #    the earliest trading day index j such that
    #    dates[j] − dates[i] ≥ window_days ──

    # Convert dates to "days since epoch" for fast arithmetic
    epoch = dates[0]
    days_since_epoch = ((dates - epoch) / np.timedelta64(1, 'D')).astype(np.float64)

    # For each start index, target end day number
    target_end_days = days_since_epoch + window_days

    # Use searchsorted to find the index of the first date ≥ target
    end_indices = np.searchsorted(days_since_epoch, target_end_days, side='left')

    # Build valid pairs: end_index must be within bounds
    all_starts = np.arange(0, n, step_days)
    valid_mask = np.array([
        idx < n and end_indices[idx] < n
        for idx in all_starts
    ])
    valid_starts = all_starts[valid_mask]

    if len(valid_starts) == 0:
        return (
            np.array([], dtype='datetime64[ns]'),
            np.array([], dtype='datetime64[ns]'),
            np.array([], dtype=np.float64),
            np.array([], dtype=np.float64),
        )

    valid_ends = end_indices[valid_starts]

    # ── Extract NAVs ──
    start_navs = navs[valid_starts]
    end_navs = navs[valid_ends]

    # ── Compute actual period in years ──
    start_day_nums = days_since_epoch[valid_starts]
    end_day_nums = days_since_epoch[valid_ends]
    actual_days = end_day_nums - start_day_nums
    actual_years = actual_days / 365.25

    # Guard against zero or negative periods
    actual_years = np.maximum(actual_years, 1e-6)

    # ── CAGR = (end/start)^(1/years) − 1 ──
    ratios = end_navs / start_navs
    # Guard against zero or negative NAVs (shouldn't happen, but safety)
    ratios = np.maximum(ratios, 1e-10)
    cagr_values = np.power(ratios, 1.0 / actual_years) - 1.0

    # ── Extract dates ──
    start_dates = dates[valid_starts]
    end_dates = dates[valid_ends]

    return start_dates, end_dates, start_navs, cagr_values


# ────────────────────────────────────────────────
# PUBLIC: Calculate rolling returns (single fund)
# ────────────────────────────────────────────────

def calculate_rolling_returns(
    nav_data: NAVData,
    window_years: float,
    window_label: str = "",
    step_days: int = 1,
) -> Tuple[RollingReturnDistribution, RollingReturnTimeSeries]:
    """
    Calculate rolling CAGR distribution for a single fund.

    Parameters
    ----------
    nav_data      : NAVData for the fund
    window_years  : rolling window length in years (e.g. 3.0)
    window_label  : display label (e.g. "3 Years")
    step_days     : step between windows (1=daily rolling, 5=weekly, 21=monthly)

    Returns
    -------
    (distribution, time_series) — summary stats + raw data
    """
    if not window_label:
        window_label = f"{window_years:.0f} Year{'s' if window_years != 1 else ''}"

    window_days = int(window_years * 365.25)

    start_dates, end_dates, start_navs, cagr_values = _compute_rolling_cagr_vectorised(
        nav_data.nav_series, window_days, step_days
    )

    num_obs = len(cagr_values)

    if num_obs == 0:
        raise ValueError(
            f"Insufficient NAV history for {window_label} rolling returns. "
            f"Fund has {nav_data.history_years:.1f} years of data, "
            f"need at least {window_years:.1f} years."
        )

    # ── Convert to percentages for stats ──
    cagr_pct = cagr_values * 100.0

    # ── Core statistics ──
    mean_ret = float(np.mean(cagr_pct))
    median_ret = float(np.median(cagr_pct))
    min_ret = float(np.min(cagr_pct))
    max_ret = float(np.max(cagr_pct))
    std_ret = float(np.std(cagr_pct, ddof=1)) if num_obs > 1 else 0.0

    # ── Percentiles ──
    p10 = float(np.percentile(cagr_pct, 10))
    p25 = float(np.percentile(cagr_pct, 25))
    p75 = float(np.percentile(cagr_pct, 75))
    p90 = float(np.percentile(cagr_pct, 90))

    # ── Probability metrics ──
    positive_pct = float(np.sum(cagr_pct > 0) / num_obs * 100)
    risk_free_annualised_pct = RISK_FREE_RATE * 100.0
    above_rf_pct = float(np.sum(cagr_pct > risk_free_annualised_pct) / num_obs * 100)

    # ── Min/Max date stamps ──
    min_idx = int(np.argmin(cagr_pct))
    max_idx = int(np.argmax(cagr_pct))

    min_start = pd.Timestamp(start_dates[min_idx]).date()
    min_end = pd.Timestamp(end_dates[min_idx]).date()
    max_start = pd.Timestamp(start_dates[max_idx]).date()
    max_end = pd.Timestamp(end_dates[max_idx]).date()

    distribution = RollingReturnDistribution(
        window_label=window_label,
        window_years=window_years,
        num_observations=num_obs,
        start_coverage_date=pd.Timestamp(start_dates[0]).date(),
        end_coverage_date=pd.Timestamp(end_dates[-1]).date(),
        mean_return_pct=round(mean_ret, 2),
        median_return_pct=round(median_ret, 2),
        min_return_pct=round(min_ret, 2),
        max_return_pct=round(max_ret, 2),
        std_dev_pct=round(std_ret, 2),
        percentile_10_pct=round(p10, 2),
        percentile_25_pct=round(p25, 2),
        percentile_75_pct=round(p75, 2),
        percentile_90_pct=round(p90, 2),
        positive_return_pct=round(positive_pct, 2),
        above_risk_free_pct=round(above_rf_pct, 2),
        min_return_start_date=min_start,
        min_return_end_date=min_end,
        max_return_start_date=max_start,
        max_return_end_date=max_end,
    )

    time_series = RollingReturnTimeSeries(
        window_label=window_label,
        window_years=window_years,
        dates=[pd.Timestamp(d).date() for d in end_dates],
        fund_returns=[round(float(v), 4) for v in cagr_pct],
    )

    return distribution, time_series


# ────────────────────────────────────────────────
# PUBLIC: Compare fund vs benchmark (rolling)
# ────────────────────────────────────────────────

def compare_rolling_returns(
    fund_nav: NAVData,
    benchmark_nav: NAVData,
    window_years: float,
    window_label: str = "",
    step_days: int = 1,
) -> Tuple[RollingReturnDistribution, RollingReturnTimeSeries]:
    """
    Compute rolling returns for both fund and benchmark,
    align them on common dates, and calculate:
      - Win rate (% of periods fund > benchmark)
      - Average excess return
      - Median excess return

    Returns the fund's distribution (enriched with benchmark metrics)
    and the time-series (with benchmark & excess columns).
    """
    if not window_label:
        window_label = f"{window_years:.0f} Year{'s' if window_years != 1 else ''}"

    window_days = int(window_years * 365.25)

    # ── Compute raw rolling for both ──
    f_starts, f_ends, _, f_cagrs = _compute_rolling_cagr_vectorised(
        fund_nav.nav_series, window_days, step_days
    )
    b_starts, b_ends, _, b_cagrs = _compute_rolling_cagr_vectorised(
        benchmark_nav.nav_series, window_days, step_days
    )

    if len(f_cagrs) == 0 or len(b_cagrs) == 0:
        raise ValueError(
            f"Insufficient history for {window_label} rolling comparison. "
            f"Fund: {fund_nav.history_years:.1f}y, "
            f"Benchmark: {benchmark_nav.history_years:.1f}y, "
            f"Need: {window_years:.1f}y."
        )

    # ── Align on common END dates ──
    # Build DataFrames keyed by end date, then inner-join
    f_df = pd.DataFrame({
        'end_date': f_ends,
        'start_date': f_starts,
        'fund_cagr': f_cagrs,
    })
    b_df = pd.DataFrame({
        'end_date': b_ends,
        'bench_cagr': b_cagrs,
    })

    merged = pd.merge(f_df, b_df, on='end_date', how='inner')

    if len(merged) == 0:
        raise ValueError(
            f"No overlapping dates for {window_label} rolling comparison."
        )

    fund_pct = merged['fund_cagr'].values * 100.0
    bench_pct = merged['bench_cagr'].values * 100.0
    excess_pct = fund_pct - bench_pct
    num_obs = len(fund_pct)

    # ── Fund distribution stats (same as single-fund) ──
    mean_ret = float(np.mean(fund_pct))
    median_ret = float(np.median(fund_pct))
    min_ret = float(np.min(fund_pct))
    max_ret = float(np.max(fund_pct))
    std_ret = float(np.std(fund_pct, ddof=1)) if num_obs > 1 else 0.0

    p10 = float(np.percentile(fund_pct, 10))
    p25 = float(np.percentile(fund_pct, 25))
    p75 = float(np.percentile(fund_pct, 75))
    p90 = float(np.percentile(fund_pct, 90))

    positive_pct = float(np.sum(fund_pct > 0) / num_obs * 100)
    rf_pct = RISK_FREE_RATE * 100.0
    above_rf_pct = float(np.sum(fund_pct > rf_pct) / num_obs * 100)

    # ── Benchmark comparison stats ──
    win_rate = float(np.sum(excess_pct > 0) / num_obs * 100)
    avg_excess = float(np.mean(excess_pct))
    median_excess = float(np.median(excess_pct))

    # ── Min/Max timestamps ──
    min_idx = int(np.argmin(fund_pct))
    max_idx = int(np.argmax(fund_pct))

    start_dates_arr = merged['start_date'].values
    end_dates_arr = merged['end_date'].values

    min_start = pd.Timestamp(start_dates_arr[min_idx]).date()
    min_end = pd.Timestamp(end_dates_arr[min_idx]).date()
    max_start = pd.Timestamp(start_dates_arr[max_idx]).date()
    max_end = pd.Timestamp(end_dates_arr[max_idx]).date()

    distribution = RollingReturnDistribution(
        window_label=window_label,
        window_years=window_years,
        num_observations=num_obs,
        start_coverage_date=pd.Timestamp(start_dates_arr[0]).date(),
        end_coverage_date=pd.Timestamp(end_dates_arr[-1]).date(),
        mean_return_pct=round(mean_ret, 2),
        median_return_pct=round(median_ret, 2),
        min_return_pct=round(min_ret, 2),
        max_return_pct=round(max_ret, 2),
        std_dev_pct=round(std_ret, 2),
        percentile_10_pct=round(p10, 2),
        percentile_25_pct=round(p25, 2),
        percentile_75_pct=round(p75, 2),
        percentile_90_pct=round(p90, 2),
        positive_return_pct=round(positive_pct, 2),
        above_risk_free_pct=round(above_rf_pct, 2),
        win_rate_vs_benchmark_pct=round(win_rate, 2),
        avg_excess_return_pct=round(avg_excess, 2),
        median_excess_return_pct=round(median_excess, 2),
        min_return_start_date=min_start,
        min_return_end_date=min_end,
        max_return_start_date=max_start,
        max_return_end_date=max_end,
    )

    time_series = RollingReturnTimeSeries(
        window_label=window_label,
        window_years=window_years,
        dates=[pd.Timestamp(d).date() for d in end_dates_arr],
        fund_returns=[round(float(v), 4) for v in fund_pct],
        benchmark_returns=[round(float(v), 4) for v in bench_pct],
        excess_returns=[round(float(v), 4) for v in excess_pct],
    )

    return distribution, time_series


# ────────────────────────────────────────────────
# INTERPRETATION ENGINE
# ────────────────────────────────────────────────

def _grade_win_rate(rate: float) -> str:
    """Grade the benchmark win rate."""
    if rate >= 80:
        return "EXCELLENT"
    elif rate >= 70:
        return "STRONG"
    elif rate >= 60:
        return "GOOD"
    elif rate >= 50:
        return "AVERAGE"
    else:
        return "POOR"


def _interpret_rolling(
    distributions: List[RollingReturnDistribution],
) -> List[str]:
    """
    Generate advisory-grade insights from rolling return distributions.
    """
    insights: List[str] = []

    for dist in distributions:
        label = dist.window_label
        insights.append(f"{'─' * 50}")
        insights.append(f"📊  {label} Rolling Returns  ({dist.num_observations:,} observations)")
        insights.append(f"{'─' * 50}")

        # ── 1. Positive return probability ──
        if dist.positive_return_pct == 100.0:
            insights.append(
                f"✅  The fund has NEVER delivered a negative return over "
                f"any {label} period — 100% positive return probability."
            )
        elif dist.positive_return_pct >= 95:
            insights.append(
                f"✅  {dist.positive_return_pct:.1f}% of {label} periods "
                f"delivered positive returns — very high reliability."
            )
        elif dist.positive_return_pct >= 80:
            insights.append(
                f"🔶  {dist.positive_return_pct:.1f}% of {label} periods "
                f"were positive — good but not exceptional."
            )
        else:
            insights.append(
                f"❌  Only {dist.positive_return_pct:.1f}% of {label} periods "
                f"were positive — significant loss probability."
            )

        # ── 2. Minimum rolling return (worst case) ──
        if dist.min_return_pct > 0:
            insights.append(
                f"🛡️   Worst-case {label} CAGR = {dist.min_return_pct:+.2f}% "
                f"(still positive!) — strong downside protection."
            )
        elif dist.min_return_pct > -5:
            insights.append(
                f"🔶  Worst-case {label} CAGR = {dist.min_return_pct:+.2f}% "
                f"— mild downside, manageable."
            )
        elif dist.min_return_pct > -15:
            insights.append(
                f"⚠️   Worst-case {label} CAGR = {dist.min_return_pct:+.2f}% "
                f"— material potential loss."
            )
        else:
            insights.append(
                f"❌  Worst-case {label} CAGR = {dist.min_return_pct:+.2f}% "
                f"— severe drawdown risk."
            )

        if dist.min_return_start_date and dist.min_return_end_date:
            insights.append(
                f"     ↳ Occurred: {dist.min_return_start_date} → {dist.min_return_end_date}"
            )

        # ── 3. Return consistency (std dev) ──
        if dist.std_dev_pct < 3:
            insights.append(
                f"✅  Rolling return σ = {dist.std_dev_pct:.2f}% — "
                f"very consistent returns across periods."
            )
        elif dist.std_dev_pct < 6:
            insights.append(
                f"🔶  Rolling return σ = {dist.std_dev_pct:.2f}% — "
                f"moderate variation across entry points."
            )
        else:
            insights.append(
                f"⚠️   Rolling return σ = {dist.std_dev_pct:.2f}% — "
                f"high variation — entry timing matters significantly."
            )

        # ── 4. Median vs Mean skewness check ──
        skew_diff = dist.mean_return_pct - dist.median_return_pct
        if skew_diff > 1.0:
            insights.append(
                f"📈  Mean ({dist.mean_return_pct:.2f}%) > Median "
                f"({dist.median_return_pct:.2f}%) — positively skewed "
                f"(a few outstanding periods pull average up)."
            )
        elif skew_diff < -1.0:
            insights.append(
                f"📉  Mean ({dist.mean_return_pct:.2f}%) < Median "
                f"({dist.median_return_pct:.2f}%) — negatively skewed "
                f"(a few bad periods drag average down)."
            )

        # ── 5. Risk-free rate comparison ──
        if dist.above_risk_free_pct == 100:
            insights.append(
                f"✅  Fund beat the risk-free rate ({RISK_FREE_RATE*100:.1f}%) "
                f"in 100% of {label} periods — always added equity premium."
            )
        elif dist.above_risk_free_pct >= 85:
            insights.append(
                f"✅  Fund beat risk-free rate in {dist.above_risk_free_pct:.1f}% "
                f"of {label} periods — strong equity premium delivery."
            )
        elif dist.above_risk_free_pct >= 60:
            insights.append(
                f"🔶  Fund beat risk-free rate in only {dist.above_risk_free_pct:.1f}% "
                f"of {label} periods — equity premium not always captured."
            )
        else:
            insights.append(
                f"❌  Fund beat risk-free rate in only {dist.above_risk_free_pct:.1f}% "
                f"of {label} periods — poor risk-reward profile."
            )

        # ── 6. Benchmark win rate (if available) ──
        if dist.win_rate_vs_benchmark_pct is not None:
            grade = _grade_win_rate(dist.win_rate_vs_benchmark_pct)
            icon = {"EXCELLENT": "🏆", "STRONG": "✅", "GOOD": "🔶",
                    "AVERAGE": "⚠️", "POOR": "❌"}.get(grade, "")

            insights.append(
                f"{icon}  Benchmark win rate: {dist.win_rate_vs_benchmark_pct:.1f}% "
                f"— rated {grade}"
            )

            if dist.avg_excess_return_pct is not None:
                insights.append(
                    f"     ↳ Avg excess return: {dist.avg_excess_return_pct:+.2f}% | "
                    f"Median excess: {dist.median_excess_return_pct:+.2f}%"
                )

            # Specific actionable advice based on win rate
            if dist.win_rate_vs_benchmark_pct < 50 and dist.window_years >= 3:
                insights.append(
                    f"     ⚡ RECOMMENDATION: Fund fails to beat benchmark "
                    f"majority of the time over {label} — consider switching "
                    f"to a low-cost index fund."
                )
            elif dist.win_rate_vs_benchmark_pct >= 80 and dist.window_years >= 3:
                insights.append(
                    f"     ⚡ This is among the elite — beating benchmark "
                    f"≥80% of the time over {label} is very rare."
                )

        # ── 7. Range spread insight ──
        spread = dist.max_return_pct - dist.min_return_pct
        insights.append(
            f"📊  Return range: {dist.min_return_pct:+.2f}% to "
            f"{dist.max_return_pct:+.2f}% (spread: {spread:.1f}pp)"
        )
        insights.append(
            f"     ↳ IQR (P25–P75): {dist.percentile_25_pct:.2f}% to "
            f"{dist.percentile_75_pct:.2f}%"
        )
        insights.append(
            f"     ↳ P10–P90 range: {dist.percentile_10_pct:.2f}% to "
            f"{dist.percentile_90_pct:.2f}%"
        )

        insights.append("")  # blank line separator

    # ── Cross-window insights ──
    if len(distributions) >= 2:
        insights.append(f"{'═' * 50}")
        insights.append("📋  CROSS-WINDOW SUMMARY")
        insights.append(f"{'═' * 50}")

        # Check if longer windows have lower std dev (expected)
        sorted_dists = sorted(distributions, key=lambda d: d.window_years)
        for i in range(1, len(sorted_dists)):
            prev = sorted_dists[i - 1]
            curr = sorted_dists[i]
            if curr.std_dev_pct < prev.std_dev_pct:
                insights.append(
                    f"✅  {curr.window_label} σ ({curr.std_dev_pct:.2f}%) < "
                    f"{prev.window_label} σ ({prev.std_dev_pct:.2f}%) — "
                    f"longer holding reduces return volatility (as expected)."
                )

        # Check if longer windows have higher positive % (expected)
        for i in range(1, len(sorted_dists)):
            prev = sorted_dists[i - 1]
            curr = sorted_dists[i]
            if curr.positive_return_pct > prev.positive_return_pct:
                pass  # expected, don't clutter
            elif curr.positive_return_pct < prev.positive_return_pct:
                insights.append(
                    f"⚠️   Unusual: {curr.window_label} has LOWER positive % "
                    f"({curr.positive_return_pct:.1f}%) than {prev.window_label} "
                    f"({prev.positive_return_pct:.1f}%) — investigate."
                )

        # Minimum holding period recommendation
        for dist in sorted_dists:
            if dist.min_return_pct > 0:
                insights.append(
                    f"\n💡  MINIMUM HOLDING PERIOD: {dist.window_label}"
                )
                insights.append(
                    f"    Over any {dist.window_label} window, the fund has "
                    f"NEVER lost money (worst: {dist.min_return_pct:+.2f}%)."
                )
                insights.append(
                    f"    This is the minimum horizon to virtually eliminate "
                    f"loss probability with this fund."
                )
                break
        else:
            # No window guarantees positive return
            longest = sorted_dists[-1]
            insights.append(
                f"\n⚠️   Even over {longest.window_label}, the fund has experienced "
                f"negative returns (worst: {longest.min_return_pct:+.2f}%). "
                f"Longer holding periods or SIP approach recommended."
            )

        # Overall quality grade based on longest available win rate
        for dist in reversed(sorted_dists):
            if dist.win_rate_vs_benchmark_pct is not None:
                wr = dist.win_rate_vs_benchmark_pct
                label = dist.window_label
                if wr >= 80:
                    insights.append(
                        f"\n🏆  OVERALL VERDICT: EXCEPTIONAL active fund — "
                        f"{wr:.0f}% win rate over {label}."
                    )
                elif wr >= 70:
                    insights.append(
                        f"\n✅  OVERALL VERDICT: STRONG active fund — "
                        f"{wr:.0f}% win rate over {label}."
                    )
                elif wr >= 60:
                    insights.append(
                        f"\n🔶  OVERALL VERDICT: GOOD active fund — "
                        f"{wr:.0f}% win rate over {label}, but "
                        f"monitor for consistency."
                    )
                elif wr >= 50:
                    insights.append(
                        f"\n⚠️   OVERALL VERDICT: AVERAGE — "
                        f"{wr:.0f}% win rate over {label}. "
                        f"Active fees may not be justified."
                    )
                else:
                    insights.append(
                        f"\n❌  OVERALL VERDICT: UNDERPERFORMING — "
                        f"{wr:.0f}% win rate over {label}. "
                        f"Strongly recommend switching to index fund."
                    )
                break

    return insights


# ────────────────────────────────────────────────
# PUBLIC: Full report (one-call convenience)
# ────────────────────────────────────────────────

def generate_rolling_report(
    fund_nav: NAVData,
    benchmark_nav: Optional[NAVData] = None,
    windows: Optional[List[Tuple[str, float]]] = None,
    step_days: int = 1,
) -> RollingReturnReport:
    """
    End-to-end rolling return analysis:
      1. Calculate rolling returns for each window length
      2. Compare vs benchmark if provided
      3. Generate automated interpretation
      4. Package everything into RollingReturnReport

    Parameters
    ----------
    fund_nav      : NAVData for the fund
    benchmark_nav : NAVData for benchmark (optional)
    windows       : list of (label, years) tuples
                    defaults to DEFAULT_ROLLING_WINDOWS
    step_days     : 1=daily, 5=weekly, 21=monthly rolling
                    (daily is most thorough but slowest)

    Returns
    -------
    RollingReturnReport
    """
    if windows is None:
        windows = DEFAULT_ROLLING_WINDOWS

    distributions: List[RollingReturnDistribution] = []
    time_series_list: List[RollingReturnTimeSeries] = []

    for label, years in windows:
        # ── Check if fund has enough history ──
        if fund_nav.history_years < years:
            continue  # skip this window — not enough data

        if benchmark_nav is not None and benchmark_nav.history_years < years:
            # Benchmark too short — fall back to fund-only for this window
            try:
                dist, ts = calculate_rolling_returns(
                    fund_nav, years, label, step_days
                )
            except ValueError:
                continue
        elif benchmark_nav is not None:
            try:
                dist, ts = compare_rolling_returns(
                    fund_nav, benchmark_nav, years, label, step_days
                )
            except ValueError:
                continue
        else:
            try:
                dist, ts = calculate_rolling_returns(
                    fund_nav, years, label, step_days
                )
            except ValueError:
                continue

        distributions.append(dist)
        time_series_list.append(ts)

    if not distributions:
        raise ValueError(
            f"No rolling windows could be computed. "
            f"Fund history: {fund_nav.history_years:.1f} years. "
            f"Minimum required: {min(y for _, y in windows):.1f} years."
        )

    interpretation = _interpret_rolling(distributions)

    return RollingReturnReport(
        scheme_info=fund_nav.scheme_info,
        benchmark_info=benchmark_nav.scheme_info if benchmark_nav else None,
        as_of_date=fund_nav.latest_date,
        distributions=distributions,
        time_series=time_series_list,
        interpretation=interpretation,
    )