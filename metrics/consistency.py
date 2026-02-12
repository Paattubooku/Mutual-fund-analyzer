"""
metrics/consistency.py
──────────────────────
SECTION 1.3 — Consistency of Outperformance

This module analyses HOW RELIABLY a fund beats its benchmark:
  1. Calendar year return comparison (every year, fund vs benchmark)
  2. Consistency score (% of years beating benchmark)
  3. Up-Market Capture Ratio (does the fund amplify bull months?)
  4. Down-Market Capture Ratio (does the fund protect in bear months?)
  5. Capture Ratio (asymmetry = up / down — the higher the better)
  6. Monthly batting averages in up and down markets

Public API
----------
    calculate_calendar_year_returns(fund_nav, benchmark_nav=None)
    calculate_capture_ratios(fund_nav, benchmark_nav, months=36)
    generate_consistency_report(fund_nav, benchmark_nav=None)
"""

from __future__ import annotations

import datetime as dt
from typing import Optional, List, Tuple

import numpy as np
import pandas as pd

from data.models import (
    NAVData,
    CalendarYearReturn,
    CalendarYearAnalysis,
    MonthlyReturnData,
    CaptureRatios,
    ConsistencyReport,
)


# ────────────────────────────────────────────────
# HELPER: Build monthly return series from NAV data
# ────────────────────────────────────────────────

def _build_monthly_returns(nav_data: NAVData) -> pd.Series:
    """
    Convert daily NAV series to monthly returns.

    Uses the LAST available NAV of each month (month-end pricing).
    Returns a Series indexed by month-end date with return in decimal form.

    Example output:
        2020-01-31    0.025      (2.5% for January 2020)
        2020-02-29   -0.031      (-3.1% for February 2020)
        ...
    """
    series = nav_data.nav_series.copy()

    # Resample to month-end, taking last available NAV
    monthly_nav = series.resample('ME').last()

    # Drop any NaN values (months with no trading data)
    monthly_nav = monthly_nav.dropna()

    # Calculate month-over-month percentage change
    monthly_returns = monthly_nav.pct_change().dropna()

    return monthly_returns


def _align_monthly_returns(
    fund_nav: NAVData,
    benchmark_nav: NAVData,
) -> Tuple[pd.Series, pd.Series]:
    """
    Build monthly returns for both fund and benchmark,
    then align them on common months (inner join).

    Returns
    -------
    (fund_monthly, bench_monthly) — aligned pd.Series
    """
    fund_monthly = _build_monthly_returns(fund_nav)
    bench_monthly = _build_monthly_returns(benchmark_nav)

    # Align on common dates
    common_idx = fund_monthly.index.intersection(bench_monthly.index)

    if len(common_idx) == 0:
        raise ValueError(
            "No overlapping monthly data between fund and benchmark."
        )

    return fund_monthly.loc[common_idx], bench_monthly.loc[common_idx]


# ────────────────────────────────────────────────
# HELPER: Build yearly returns from NAV data
# ────────────────────────────────────────────────

def _get_year_end_nav(
    nav_series: pd.Series,
    year: int,
    boundary: str = "end",
) -> Optional[float]:
    """
    Get the NAV at the start or end of a calendar year.

    boundary="start" → first trading day of the year
    boundary="end"   → last trading day of the year
    """
    year_data = nav_series[nav_series.index.year == year]
    if len(year_data) == 0:
        return None
    if boundary == "start":
        return float(year_data.iloc[0])
    else:
        return float(year_data.iloc[-1])


def _calculate_yearly_return(
    nav_series: pd.Series,
    year: int,
) -> Optional[float]:
    """
    Calculate the calendar year return for a given year.

    Uses the last NAV of the previous year as the starting point
    and the last NAV of the given year as the ending point.

    Returns None if insufficient data.
    """
    # End NAV: last trading day of `year`
    end_nav = _get_year_end_nav(nav_series, year, "end")
    if end_nav is None:
        return None

    # Start NAV: last trading day of (year - 1)
    start_nav = _get_year_end_nav(nav_series, year - 1, "end")
    if start_nav is None:
        # Fallback: first trading day of `year`
        start_nav = _get_year_end_nav(nav_series, year, "start")
        if start_nav is None:
            return None

    if start_nav <= 0:
        return None

    return ((end_nav / start_nav) - 1.0) * 100.0


# ────────────────────────────────────────────────
# PUBLIC: Calendar Year Returns
# ────────────────────────────────────────────────

def calculate_calendar_year_returns(
    fund_nav: NAVData,
    benchmark_nav: Optional[NAVData] = None,
) -> CalendarYearAnalysis:
    """
    Compare fund vs benchmark returns for every calendar year
    where both have data.

    Parameters
    ----------
    fund_nav      : NAVData for the fund
    benchmark_nav : NAVData for the benchmark (optional)

    Returns
    -------
    CalendarYearAnalysis with full year-by-year breakdown
    """
    fund_series = fund_nav.nav_series

    # Determine year range from fund data
    first_year = fund_series.index.min().year
    last_year = fund_series.index.max().year

    # We need at least the start-of-year NAV, so effective first year
    # is the year AFTER the inception year (unless fund started on Jan 1)
    inception_date = fund_nav.inception_date
    if inception_date.month > 1 or inception_date.day > 15:
        first_year = first_year + 1

    # Don't include current year if we haven't completed it
    today = dt.date.today()
    if last_year == today.year and today.month < 12:
        # Only include current year if we're far enough into it
        # We'll still calculate it but mark it as partial
        pass

    yearly_returns: List[CalendarYearReturn] = []

    for year in range(first_year, last_year + 1):
        fund_ret = _calculate_yearly_return(fund_series, year)
        if fund_ret is None:
            continue

        bench_ret = None
        excess = None
        beat = None

        if benchmark_nav is not None:
            bench_ret = _calculate_yearly_return(benchmark_nav.nav_series, year)
            if bench_ret is not None:
                excess = round(fund_ret - bench_ret, 2)
                beat = fund_ret > bench_ret

        yearly_returns.append(CalendarYearReturn(
            year=year,
            fund_return_pct=round(fund_ret, 2),
            benchmark_return_pct=round(bench_ret, 2) if bench_ret is not None else None,
            excess_return_pct=excess,
            beat_benchmark=beat,
        ))

    if not yearly_returns:
        raise ValueError(
            "Insufficient data to compute calendar year returns. "
            f"Fund inception: {fund_nav.inception_date}"
        )

    # ── Aggregate statistics ──
    total_years = len(yearly_returns)
    years_with_bench = [y for y in yearly_returns if y.beat_benchmark is not None]
    years_beat = sum(1 for y in years_with_bench if y.beat_benchmark)
    n_bench_years = len(years_with_bench)

    if n_bench_years > 0:
        consistency_pct = round(years_beat / n_bench_years * 100, 1)
        excess_values = [y.excess_return_pct for y in years_with_bench if y.excess_return_pct is not None]
        avg_excess = round(float(np.mean(excess_values)), 2) if excess_values else 0.0
        median_excess = round(float(np.median(excess_values)), 2) if excess_values else 0.0
    else:
        consistency_pct = 0.0
        avg_excess = 0.0
        median_excess = 0.0

    # ── Consistency grade ──
    consistency_grade = _grade_consistency(consistency_pct)

    # ── Best/Worst years ──
    best_year = max(yearly_returns, key=lambda y: y.fund_return_pct)
    worst_year = min(yearly_returns, key=lambda y: y.fund_return_pct)

    best_outperf = None
    worst_underperf = None
    if years_with_bench:
        outperf_sorted = sorted(
            years_with_bench,
            key=lambda y: y.excess_return_pct if y.excess_return_pct is not None else 0,
        )
        worst_underperf = outperf_sorted[0]
        best_outperf = outperf_sorted[-1]

    return CalendarYearAnalysis(
        yearly_returns=yearly_returns,
        total_years=total_years,
        years_beat_benchmark=years_beat,
        consistency_pct=consistency_pct,
        consistency_grade=consistency_grade,
        avg_annual_excess_pct=avg_excess,
        median_annual_excess_pct=median_excess,
        best_year=best_year,
        worst_year=worst_year,
        best_outperformance_year=best_outperf,
        worst_underperformance_year=worst_underperf,
    )


def _grade_consistency(pct: float) -> str:
    """Grade the consistency percentage."""
    if pct >= 80:
        return "EXCEPTIONAL"
    elif pct >= 70:
        return "STRONG"
    elif pct >= 60:
        return "GOOD"
    elif pct >= 50:
        return "AVERAGE"
    else:
        return "POOR"


# ────────────────────────────────────────────────
# PUBLIC: Capture Ratios
# ────────────────────────────────────────────────

def calculate_capture_ratios(
    fund_nav: NAVData,
    benchmark_nav: NAVData,
    months: Optional[int] = None,
) -> CaptureRatios:
    """
    Calculate Up-Market and Down-Market Capture Ratios.

    Method
    ------
    1. Build monthly returns for fund and benchmark
    2. Separate months into UP (benchmark > 0) and DOWN (benchmark < 0)
    3. Up Capture = (Geometric mean of fund in up months) /
                    (Geometric mean of bench in up months) × 100
    4. Down Capture = (Geometric mean of fund in down months) /
                      (Geometric mean of bench in down months) × 100

    Parameters
    ----------
    fund_nav      : NAVData for the fund
    benchmark_nav : NAVData for the benchmark
    months        : number of most recent months to use (None = all)

    Returns
    -------
    CaptureRatios dataclass
    """
    fund_monthly, bench_monthly = _align_monthly_returns(fund_nav, benchmark_nav)

    # Optionally restrict to last N months
    if months is not None and len(fund_monthly) > months:
        fund_monthly = fund_monthly.iloc[-months:]
        bench_monthly = bench_monthly.iloc[-months:]

    total_months = len(fund_monthly)

    if total_months < 12:
        raise ValueError(
            f"Need at least 12 months of overlapping data for capture ratios. "
            f"Found: {total_months} months."
        )

    # ── Separate up and down months (based on BENCHMARK) ──
    up_mask = bench_monthly > 0
    down_mask = bench_monthly < 0
    # Flat months (benchmark == 0) are excluded from both

    fund_up = fund_monthly[up_mask]
    bench_up = bench_monthly[up_mask]
    fund_down = fund_monthly[down_mask]
    bench_down = bench_monthly[down_mask]

    num_up = len(fund_up)
    num_down = len(fund_down)

    # ── Geometric mean calculation ──
    # Geometric mean of (1 + r) values, then subtract 1
    # Use the compound approach: product of (1+r) ^ (1/n) - 1

    def _geo_mean_return(returns: pd.Series) -> float:
        """Compute annualised geometric mean from monthly returns."""
        if len(returns) == 0:
            return 0.0
        compound = np.prod(1.0 + returns.values)
        n = len(returns)
        # Geometric mean monthly return
        geo_monthly = compound ** (1.0 / n) - 1.0
        return geo_monthly

    # ── Up-Market Capture ──
    if num_up > 0:
        fund_up_geo = _geo_mean_return(fund_up)
        bench_up_geo = _geo_mean_return(bench_up)

        if bench_up_geo != 0:
            up_capture = (fund_up_geo / bench_up_geo) * 100.0
        else:
            up_capture = 100.0

        avg_fund_up = float(fund_up.mean()) * 100.0
        avg_bench_up = float(bench_up.mean()) * 100.0

        # Batting average: % of up months where fund beat benchmark
        up_batting = float(np.sum(fund_up.values > bench_up.values) / num_up * 100)
    else:
        up_capture = 100.0
        avg_fund_up = 0.0
        avg_bench_up = 0.0
        up_batting = 0.0

    # ── Down-Market Capture ──
    if num_down > 0:
        fund_down_geo = _geo_mean_return(fund_down)
        bench_down_geo = _geo_mean_return(bench_down)

        if bench_down_geo != 0:
            down_capture = (fund_down_geo / bench_down_geo) * 100.0
        else:
            down_capture = 100.0

        avg_fund_down = float(fund_down.mean()) * 100.0
        avg_bench_down = float(bench_down.mean()) * 100.0

        # Batting average: % of down months where fund lost LESS than bench
        down_batting = float(
            np.sum(fund_down.values > bench_down.values) / num_down * 100
        )
    else:
        down_capture = 100.0
        avg_fund_down = 0.0
        avg_bench_down = 0.0
        down_batting = 0.0

    # ── Capture Ratio (asymmetry) ──
    if down_capture != 0:
        capture_ratio = up_capture / down_capture
    else:
        capture_ratio = float('inf')

    return CaptureRatios(
        up_capture_ratio=round(up_capture, 2),
        down_capture_ratio=round(down_capture, 2),
        capture_ratio=round(capture_ratio, 2),
        num_up_months=num_up,
        num_down_months=num_down,
        total_months=total_months,
        avg_fund_up_month_pct=round(avg_fund_up, 2),
        avg_bench_up_month_pct=round(avg_bench_up, 2),
        avg_fund_down_month_pct=round(avg_fund_down, 2),
        avg_bench_down_month_pct=round(avg_bench_down, 2),
        up_month_batting_avg_pct=round(up_batting, 1),
        down_month_batting_avg_pct=round(down_batting, 1),
    )


# ────────────────────────────────────────────────
# HELPER: Build MonthlyReturnData for output
# ────────────────────────────────────────────────

def _build_monthly_return_data(
    fund_nav: NAVData,
    benchmark_nav: NAVData,
) -> MonthlyReturnData:
    """Build aligned monthly return data for export."""
    fund_m, bench_m = _align_monthly_returns(fund_nav, benchmark_nav)

    months = [d.strftime("%Y-%m") for d in fund_m.index]
    fund_rets = [round(float(v) * 100, 2) for v in fund_m.values]
    bench_rets = [round(float(v) * 100, 2) for v in bench_m.values]

    return MonthlyReturnData(
        months=months,
        fund_returns_pct=fund_rets,
        benchmark_returns_pct=bench_rets,
    )


# ────────────────────────────────────────────────
# INTERPRETATION ENGINE
# ────────────────────────────────────────────────

def _interpret_consistency(
    cal_year: Optional[CalendarYearAnalysis],
    capture: Optional[CaptureRatios],
) -> List[str]:
    """
    Generate advisory-grade insights from consistency analysis.
    """
    insights: List[str] = []

    # ════════════════════════════════════════════
    # CALENDAR YEAR ANALYSIS
    # ════════════════════════════════════════════
    if cal_year is not None:
        insights.append("─" * 55)
        insights.append("📅  CALENDAR YEAR CONSISTENCY ANALYSIS")
        insights.append("─" * 55)

        # ── Consistency grade ──
        grade_icons = {
            "EXCEPTIONAL": "🏆",
            "STRONG": "✅",
            "GOOD": "🔶",
            "AVERAGE": "⚠️",
            "POOR": "❌",
        }
        icon = grade_icons.get(cal_year.consistency_grade, "")

        insights.append(
            f"{icon}  Consistency: {cal_year.years_beat_benchmark}/"
            f"{cal_year.total_years} years beat benchmark "
            f"({cal_year.consistency_pct:.1f}%) — "
            f"rated {cal_year.consistency_grade}"
        )

        # ── Average alpha ──
        if cal_year.avg_annual_excess_pct > 3:
            insights.append(
                f"✅  Average annual alpha: {cal_year.avg_annual_excess_pct:+.2f}% "
                f"— strong value addition by the fund manager."
            )
        elif cal_year.avg_annual_excess_pct > 1:
            insights.append(
                f"🔶  Average annual alpha: {cal_year.avg_annual_excess_pct:+.2f}% "
                f"— moderate value addition."
            )
        elif cal_year.avg_annual_excess_pct > 0:
            insights.append(
                f"⚠️   Average annual alpha: {cal_year.avg_annual_excess_pct:+.2f}% "
                f"— marginal — may not justify active management fees."
            )
        else:
            insights.append(
                f"❌  Average annual alpha: {cal_year.avg_annual_excess_pct:+.2f}% "
                f"— NEGATIVE — fund is destroying value vs benchmark."
            )

        # ── Median vs Mean alpha ──
        if cal_year.avg_annual_excess_pct != 0:
            skew = cal_year.avg_annual_excess_pct - cal_year.median_annual_excess_pct
            if abs(skew) > 1.5:
                if skew > 0:
                    insights.append(
                        f"📊  Mean alpha ({cal_year.avg_annual_excess_pct:+.2f}%) > "
                        f"Median ({cal_year.median_annual_excess_pct:+.2f}%) — "
                        f"a few exceptional years inflate the average."
                    )
                else:
                    insights.append(
                        f"📊  Mean alpha ({cal_year.avg_annual_excess_pct:+.2f}%) < "
                        f"Median ({cal_year.median_annual_excess_pct:+.2f}%) — "
                        f"a few bad years drag the average down."
                    )

        # ── Best/Worst absolute year ──
        if cal_year.best_year:
            insights.append(
                f"📈  Best year: {cal_year.best_year.year} "
                f"({cal_year.best_year.fund_return_pct:+.2f}%)"
            )
        if cal_year.worst_year:
            insights.append(
                f"📉  Worst year: {cal_year.worst_year.year} "
                f"({cal_year.worst_year.fund_return_pct:+.2f}%)"
            )

        # ── Best/Worst outperformance year ──
        if cal_year.best_outperformance_year and cal_year.best_outperformance_year.excess_return_pct is not None:
            y = cal_year.best_outperformance_year
            insights.append(
                f"🏆  Best outperformance: {y.year} — beat benchmark by "
                f"{y.excess_return_pct:+.2f}%"
            )
        if cal_year.worst_underperformance_year and cal_year.worst_underperformance_year.excess_return_pct is not None:
            y = cal_year.worst_underperformance_year
            if y.excess_return_pct < 0:
                insights.append(
                    f"⚠️   Worst underperformance: {y.year} — trailed benchmark by "
                    f"{y.excess_return_pct:.2f}%"
                )

        # ── Consecutive years analysis ──
        _analyse_streaks(cal_year, insights)

        # ── Actionable advice based on consistency grade ──
        if cal_year.consistency_grade == "POOR":
            insights.append(
                f"\n⚡  RECOMMENDATION: Fund beats benchmark less than half the time. "
                f"Strongly consider switching to a low-cost index fund."
            )
        elif cal_year.consistency_grade == "AVERAGE":
            insights.append(
                f"\n⚡  RECOMMENDATION: 50/50 coin flip vs benchmark. "
                f"Active management fees are questionable at this consistency level."
            )

        insights.append("")

    # ════════════════════════════════════════════
    # CAPTURE RATIO ANALYSIS
    # ════════════════════════════════════════════
    if capture is not None:
        insights.append("─" * 55)
        insights.append("📊  UP-MARKET / DOWN-MARKET CAPTURE ANALYSIS")
        insights.append(
            f"    Based on {capture.total_months} months "
            f"({capture.num_up_months} up, {capture.num_down_months} down)"
        )
        insights.append("─" * 55)

        # ── Up Capture ──
        if capture.up_capture_ratio > 105:
            insights.append(
                f"📈  Up-Market Capture: {capture.up_capture_ratio:.1f}% "
                f"— fund AMPLIFIES bull market gains (captures more upside)."
            )
        elif capture.up_capture_ratio >= 95:
            insights.append(
                f"📈  Up-Market Capture: {capture.up_capture_ratio:.1f}% "
                f"— fund roughly matches benchmark in rallies."
            )
        else:
            insights.append(
                f"📈  Up-Market Capture: {capture.up_capture_ratio:.1f}% "
                f"— fund LAGS benchmark during rallies (misses some upside)."
            )

        # ── Down Capture ──
        if capture.down_capture_ratio < 85:
            insights.append(
                f"🛡️   Down-Market Capture: {capture.down_capture_ratio:.1f}% "
                f"— EXCELLENT downside protection (loses significantly less)."
            )
        elif capture.down_capture_ratio < 95:
            insights.append(
                f"🛡️   Down-Market Capture: {capture.down_capture_ratio:.1f}% "
                f"— good downside protection (loses less than benchmark)."
            )
        elif capture.down_capture_ratio <= 105:
            insights.append(
                f"🔶  Down-Market Capture: {capture.down_capture_ratio:.1f}% "
                f"— roughly matches benchmark declines."
            )
        else:
            insights.append(
                f"❌  Down-Market Capture: {capture.down_capture_ratio:.1f}% "
                f"— fund AMPLIFIES losses (falls MORE than benchmark)."
            )

        # ── Capture Ratio (the key asymmetry metric) ──
        if capture.capture_ratio > 1.2:
            insights.append(
                f"🏆  Capture Ratio: {capture.capture_ratio:.2f} — EXCELLENT asymmetry. "
                f"Fund captures more upside and/or protects more downside."
            )
        elif capture.capture_ratio > 1.0:
            insights.append(
                f"✅  Capture Ratio: {capture.capture_ratio:.2f} — positive asymmetry. "
                f"Fund has favourable up/down characteristics."
            )
        elif capture.capture_ratio >= 0.9:
            insights.append(
                f"🔶  Capture Ratio: {capture.capture_ratio:.2f} — near-neutral. "
                f"Fund behaves similarly to benchmark in both directions."
            )
        else:
            insights.append(
                f"❌  Capture Ratio: {capture.capture_ratio:.2f} — NEGATIVE asymmetry. "
                f"Fund loses more in crashes than it gains in rallies."
            )

        # ── Ideal fund identification ──
        if capture.up_capture_ratio > 100 and capture.down_capture_ratio < 100:
            insights.append(
                f"\n✅  IDEAL PROFILE DETECTED: Up Capture > 100 AND Down Capture < 100."
            )
            insights.append(
                f"    This fund gains MORE in rallies and loses LESS in crashes."
            )
            insights.append(
                f"    This asymmetry is what CREATES alpha over full market cycles."
            )
        elif capture.up_capture_ratio < 100 and capture.down_capture_ratio < 100:
            insights.append(
                f"\n🛡️   DEFENSIVE PROFILE: Both captures below 100."
            )
            insights.append(
                f"    Fund is conservative — cushions falls but also misses some upside."
            )
            if capture.capture_ratio > 1.0:
                insights.append(
                    f"    However, the net asymmetry is positive (CR={capture.capture_ratio:.2f}), "
                    f"which still favours this fund."
                )
        elif capture.up_capture_ratio > 100 and capture.down_capture_ratio > 100:
            insights.append(
                f"\n⚠️   AGGRESSIVE PROFILE: Both captures above 100."
            )
            insights.append(
                f"    Fund amplifies ALL moves — suitable only for high risk tolerance."
            )

        # ── Monthly batting averages ──
        insights.append(
            f"\n    Up-month batting average:   {capture.up_month_batting_avg_pct:.1f}% "
            f"(fund beat benchmark in {capture.up_month_batting_avg_pct:.0f}% of up months)"
        )
        insights.append(
            f"    Down-month batting average: {capture.down_month_batting_avg_pct:.1f}% "
            f"(fund beat benchmark in {capture.down_month_batting_avg_pct:.0f}% of down months)"
        )

        # Average monthly returns detail
        insights.append(
            f"\n    Avg fund return in up months:   {capture.avg_fund_up_month_pct:+.2f}% "
            f"(bench: {capture.avg_bench_up_month_pct:+.2f}%)"
        )
        insights.append(
            f"    Avg fund return in down months: {capture.avg_fund_down_month_pct:+.2f}% "
            f"(bench: {capture.avg_bench_down_month_pct:+.2f}%)"
        )

        insights.append("")

    return insights


def _analyse_streaks(
    cal_year: CalendarYearAnalysis,
    insights: List[str],
) -> None:
    """Analyse winning and losing streaks in calendar year data."""
    years = cal_year.yearly_returns
    with_bench = [y for y in years if y.beat_benchmark is not None]

    if not with_bench:
        return

    # ── Current streak ──
    current_streak = 0
    current_type = None
    for yr in reversed(with_bench):
        if current_type is None:
            current_type = yr.beat_benchmark
            current_streak = 1
        elif yr.beat_benchmark == current_type:
            current_streak += 1
        else:
            break

    if current_type is True and current_streak >= 3:
        insights.append(
            f"🔥  Current WIN STREAK: {current_streak} consecutive years "
            f"beating benchmark — momentum is strong."
        )
    elif current_type is False and current_streak >= 2:
        insights.append(
            f"⚠️   Current LOSING STREAK: {current_streak} consecutive years "
            f"trailing benchmark — watch closely."
        )

    # ── Longest win streak ──
    max_win_streak = 0
    max_lose_streak = 0
    streak = 0
    prev_beat = None

    for yr in with_bench:
        if yr.beat_benchmark == prev_beat:
            streak += 1
        else:
            streak = 1
            prev_beat = yr.beat_benchmark

        if yr.beat_benchmark and streak > max_win_streak:
            max_win_streak = streak
        if not yr.beat_benchmark and streak > max_lose_streak:
            max_lose_streak = streak

    if max_win_streak >= 4:
        insights.append(
            f"📊  Longest winning streak: {max_win_streak} consecutive years."
        )
    if max_lose_streak >= 3:
        insights.append(
            f"⚠️   Longest losing streak: {max_lose_streak} consecutive years "
            f"of underperformance."
        )


# ────────────────────────────────────────────────
# PUBLIC: Full report (one-call convenience)
# ────────────────────────────────────────────────

def generate_consistency_report(
    fund_nav: NAVData,
    benchmark_nav: Optional[NAVData] = None,
    capture_months: Optional[int] = None,
) -> ConsistencyReport:
    """
    End-to-end consistency analysis:
      1. Calendar year returns (fund vs benchmark, every year)
      2. Capture ratios (up/down market behaviour)
      3. Monthly return data (for downstream use)
      4. Automated interpretation

    Parameters
    ----------
    fund_nav        : NAVData for the fund
    benchmark_nav   : NAVData for the benchmark (optional)
    capture_months  : months for capture ratio (None = all available)

    Returns
    -------
    ConsistencyReport
    """
    # ── Calendar year analysis ──
    cal_year = None
    try:
        cal_year = calculate_calendar_year_returns(fund_nav, benchmark_nav)
    except ValueError:
        pass   # fund too young for calendar year analysis

    # ── Capture ratios ──
    capture = None
    monthly_data = None

    if benchmark_nav is not None:
        try:
            capture = calculate_capture_ratios(
                fund_nav, benchmark_nav, months=capture_months
            )
        except ValueError:
            pass   # insufficient overlapping data

        try:
            monthly_data = _build_monthly_return_data(fund_nav, benchmark_nav)
        except ValueError:
            pass

    # ── Interpretation ──
    interpretation = _interpret_consistency(cal_year, capture)

    return ConsistencyReport(
        scheme_info=fund_nav.scheme_info,
        benchmark_info=benchmark_nav.scheme_info if benchmark_nav else None,
        as_of_date=fund_nav.latest_date,
        calendar_year_analysis=cal_year,
        capture_ratios=capture,
        monthly_data=monthly_data,
        interpretation=interpretation,
    )