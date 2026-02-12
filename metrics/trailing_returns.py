"""
metrics/trailing_returns.py
───────────────────────────
SECTION 1.1 — Trailing Returns (Point-to-Point CAGR)

This is the most fundamental performance metric.  It calculates
the compound annualised growth rate (CAGR) from a past date to
the latest available NAV.

Public API
----------
    calculate_trailing_returns(nav_data, as_of_date=None)
    compare_trailing_returns(fund_nav, benchmark_nav, as_of_date=None)
    generate_trailing_report(fund_nav, benchmark_nav=None, as_of_date=None)
"""

from __future__ import annotations

import datetime as dt
from typing import Optional, List, Tuple

import pandas as pd

from config import TRAILING_PERIODS, MAX_NAV_LOOKBACK_DAYS
from data.models import (
    NAVData,
    TrailingReturn,
    TrailingReturnComparison,
    TrailingReturnReport,
)


# ────────────────────────────────────────────────
# HELPER: Find the nearest available NAV date
# ────────────────────────────────────────────────

def _find_nearest_date(
    nav_series: pd.Series,
    target: dt.date,
    max_lookback: int = MAX_NAV_LOOKBACK_DAYS,
) -> Optional[dt.date]:
    """
    Find the nearest trading day ON or BEFORE `target`.

    NAV data has gaps on weekends and market holidays.
    We search backwards up to `max_lookback` calendar days.
    Returns None if no data is found in that window.
    """
    for offset in range(max_lookback + 1):
        check = target - dt.timedelta(days=offset)
        ts = pd.Timestamp(check)
        if ts in nav_series.index:
            return check
    return None


def _get_nav_on_date(nav_series: pd.Series, target: dt.date) -> Optional[Tuple[dt.date, float]]:
    """
    Return (actual_date, nav_value) for the trading day
    nearest to `target`, or None.
    """
    actual = _find_nearest_date(nav_series, target)
    if actual is None:
        return None
    nav_val = float(nav_series.loc[pd.Timestamp(actual)])
    return actual, nav_val


# ────────────────────────────────────────────────
# CORE: CAGR / Absolute Return Calculation
# ────────────────────────────────────────────────

def _compute_return(
    start_nav: float,
    end_nav: float,
    start_date: dt.date,
    end_date: dt.date,
) -> Tuple[float, Optional[float], float]:
    """
    Returns
    -------
    absolute_pct : float
        Simple point-to-point return in %
    cagr_pct : float | None
        CAGR in % (None if period < 365 days)
    period_years : float
        Exact fractional years between start and end
    """
    absolute = (end_nav / start_nav) - 1.0
    absolute_pct = absolute * 100.0

    days = (end_date - start_date).days
    period_years = days / 365.25

    if days < 365:
        # Sub-1-year: CAGR is unreliable / misleading
        cagr_pct = None
    else:
        # CAGR = (End/Start)^(1/n) − 1
        cagr = (end_nav / start_nav) ** (1.0 / period_years) - 1.0
        cagr_pct = cagr * 100.0

    return absolute_pct, cagr_pct, period_years


# ────────────────────────────────────────────────
# PUBLIC: Calculate trailing returns for ONE fund
# ────────────────────────────────────────────────

def calculate_trailing_returns(
    nav_data: NAVData,
    as_of_date: Optional[dt.date] = None,
) -> List[TrailingReturn]:
    """
    Calculate trailing returns for all standard periods
    defined in config.TRAILING_PERIODS.

    Parameters
    ----------
    nav_data    : NAVData — the fund's historical NAV data
    as_of_date  : date    — the "today" reference point
                            (defaults to the latest available NAV date)

    Returns
    -------
    List[TrailingReturn] — one entry per period
        (periods where the fund doesn't have enough history are SKIPPED)
    """
    series = nav_data.nav_series

    # ── determine end date ──
    if as_of_date is None:
        end_date = nav_data.latest_date
    else:
        result = _get_nav_on_date(series, as_of_date)
        if result is None:
            raise ValueError(
                f"No NAV data found near as_of_date={as_of_date}. "
                f"Fund data runs {nav_data.inception_date} → {nav_data.latest_date}."
            )
        end_date = result[0]

    end_nav_result = _get_nav_on_date(series, end_date)
    if end_nav_result is None:
        raise ValueError(f"Cannot resolve end NAV for date {end_date}")
    end_date_actual, end_nav = end_nav_result

    results: List[TrailingReturn] = []

    for label, offset, annualised_flag in TRAILING_PERIODS:

        # ── compute start date ──
        if offset is None:
            # "Since Inception"
            target_start = nav_data.inception_date
        else:
            target_start = end_date_actual - offset

        # ── resolve to nearest trading day ──
        start_result = _get_nav_on_date(series, target_start)
        if start_result is None:
            # Fund doesn't have data this far back — skip
            continue

        start_date_actual, start_nav = start_result

        # ── guard: start must be before end ──
        if start_date_actual >= end_date_actual:
            continue

        # ── compute returns ──
        abs_pct, cagr_pct, period_years = _compute_return(
            start_nav, end_nav, start_date_actual, end_date_actual
        )

        # For "Since Inception", update the annualised flag
        # based on whether the fund is older than 1 year
        if offset is None:
            annualised_flag = period_years >= 1.0

        results.append(TrailingReturn(
            period_label=label,
            start_date=start_date_actual,
            end_date=end_date_actual,
            start_nav=round(start_nav, 4),
            end_nav=round(end_nav, 4),
            absolute_return_pct=round(abs_pct, 2),
            cagr_pct=round(cagr_pct, 2) if cagr_pct is not None else None,
            period_years=round(period_years, 2),
            is_annualized=annualised_flag,
        ))

    return results


# ────────────────────────────────────────────────
# PUBLIC: Compare fund vs benchmark
# ────────────────────────────────────────────────

def compare_trailing_returns(
    fund_nav: NAVData,
    benchmark_nav: NAVData,
    as_of_date: Optional[dt.date] = None,
) -> List[TrailingReturnComparison]:
    """
    Side-by-side comparison of trailing returns:
    fund vs benchmark, for every common period.
    """
    fund_returns = calculate_trailing_returns(fund_nav, as_of_date)
    bench_returns = calculate_trailing_returns(benchmark_nav, as_of_date)

    # Index benchmark returns by period label for O(1) lookup
    bench_map = {r.period_label: r for r in bench_returns}

    comparisons: List[TrailingReturnComparison] = []

    for fr in fund_returns:
        br = bench_map.get(fr.period_label)
        if br is not None:
            excess = round(fr.primary_return_pct - br.primary_return_pct, 2)
            beat = fr.primary_return_pct > br.primary_return_pct
        else:
            excess = None
            beat = None

        comparisons.append(TrailingReturnComparison(
            period_label=fr.period_label,
            fund_return=fr,
            benchmark_return=br,
            excess_return_pct=excess,
            beat_benchmark=beat,
        ))

    return comparisons


# ────────────────────────────────────────────────
# INTERPRETATION ENGINE
# ────────────────────────────────────────────────

def _interpret(comparisons: List[TrailingReturnComparison]) -> List[str]:
    """
    Generate human-readable, advisory-grade insights
    from the trailing-return comparison.

    Rules are derived from Section 1.1 of the analysis framework.
    """
    insights: List[str] = []

    lookup = {c.period_label: c for c in comparisons}

    # ── Rule 1: 1-year noise warning ──
    c1y = lookup.get("1 Year")
    if c1y:
        ret = c1y.fund_return.primary_return_pct
        if abs(ret) > 30:
            insights.append(
                f"⚠️  1Y return ({ret:+.2f}%) is extreme — "
                f"never use a single year in isolation for decisions."
            )

    # ── Rule 2: 3-year is the minimum reliable window ──
    c3y = lookup.get("3 Years")
    if c3y:
        ret = c3y.fund_return.primary_return_pct
        if c3y.excess_return_pct is not None:
            if c3y.excess_return_pct > 0:
                insights.append(
                    f"✅  3Y CAGR ({ret:.2f}%) beats benchmark by "
                    f"{c3y.excess_return_pct:+.2f}% — solid medium-term performance."
                )
            else:
                insights.append(
                    f"❌  3Y CAGR ({ret:.2f}%) trails benchmark by "
                    f"{c3y.excess_return_pct:.2f}% — underperformance concern."
                )
    else:
        insights.append(
            "⚠️  Fund does not have 3 years of history — "
            "insufficient data for reliable equity evaluation."
        )

    # ── Rule 3: 5Y and 7Y should beat benchmark ──
    for label in ("5 Years", "7 Years"):
        c = lookup.get(label)
        if c and c.excess_return_pct is not None:
            ret = c.fund_return.primary_return_pct
            if c.excess_return_pct > 2:
                insights.append(
                    f"✅  {label} CAGR ({ret:.2f}%) outperforms benchmark "
                    f"by {c.excess_return_pct:+.2f}% — strong wealth creation."
                )
            elif c.excess_return_pct > 0:
                insights.append(
                    f"🔶  {label} CAGR ({ret:.2f}%) marginally beats benchmark "
                    f"({c.excess_return_pct:+.2f}%) — alpha may not justify active fees."
                )
            else:
                insights.append(
                    f"❌  {label} CAGR ({ret:.2f}%) underperforms benchmark "
                    f"by {c.excess_return_pct:.2f}% — consider switching to index fund."
                )

    # ── Rule 4: 10Y filters exceptional managers ──
    c10y = lookup.get("10 Years")
    if c10y:
        ret = c10y.fund_return.primary_return_pct
        if c10y.excess_return_pct is not None and c10y.excess_return_pct > 2:
            insights.append(
                f"🏆  10Y CAGR ({ret:.2f}%) with {c10y.excess_return_pct:+.2f}% alpha — "
                f"truly exceptional long-term track record."
            )

    # ── Rule 5: Since Inception check ──
    csi = lookup.get("Since Inception")
    if csi:
        yrs = csi.fund_return.period_years
        ret = csi.fund_return.primary_return_pct
        if yrs >= 7:
            insights.append(
                f"📊  Since Inception ({yrs:.1f} yrs) CAGR = {ret:.2f}% — "
                f"fund has a meaningful long-term record."
            )
        else:
            insights.append(
                f"📊  Since Inception ({yrs:.1f} yrs) CAGR = {ret:.2f}% — "
                f"track record still maturing (< 7 years)."
            )

    # ── Overall alpha summary ──
    beat_count = sum(1 for c in comparisons if c.beat_benchmark is True)
    total = sum(1 for c in comparisons if c.beat_benchmark is not None)
    if total > 0:
        pct = beat_count / total * 100
        insights.append(
            f"\n📈  Benchmark beaten in {beat_count}/{total} "
            f"trailing periods ({pct:.0f}%)."
        )

    return insights


# ────────────────────────────────────────────────
# PUBLIC: Full report (one-call convenience)
# ────────────────────────────────────────────────

def generate_trailing_report(
    fund_nav: NAVData,
    benchmark_nav: Optional[NAVData] = None,
    as_of_date: Optional[dt.date] = None,
) -> TrailingReturnReport:
    """
    End-to-end trailing-return analysis:
      1. Calculate trailing returns for the fund.
      2. (Optionally) calculate for benchmark and compare.
      3. Generate automated interpretation.
      4. Package everything in a TrailingReturnReport.
    """
    if benchmark_nav is not None:
        comparisons = compare_trailing_returns(fund_nav, benchmark_nav, as_of_date)
    else:
        # No benchmark — wrap fund-only returns
        fund_returns = calculate_trailing_returns(fund_nav, as_of_date)
        comparisons = [
            TrailingReturnComparison(
                period_label=r.period_label,
                fund_return=r,
                benchmark_return=None,
                excess_return_pct=None,
                beat_benchmark=None,
            )
            for r in fund_returns
        ]

    interpretation = _interpret(comparisons)

    return TrailingReturnReport(
        scheme_info=fund_nav.scheme_info,
        benchmark_info=benchmark_nav.scheme_info if benchmark_nav else None,
        as_of_date=comparisons[0].fund_return.end_date if comparisons else dt.date.today(),
        comparisons=comparisons,
        interpretation=interpretation,
    )