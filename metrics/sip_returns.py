"""
metrics/sip_returns.py
──────────────────────
SECTION 1.4 — SIP Returns (XIRR-Based)

For SIP investors, CAGR is meaningless because money enters
at different times.  XIRR (Extended Internal Rate of Return)
is the only correct measure.

This module implements:
    1. Newton-Raphson XIRR solver for irregular cash flows
    2. SIP simulation across multiple horizons
    3. SIP vs Lump Sum comparison
    4. Rolling SIP XIRR (probability distribution)
    5. SIP date sensitivity analysis
    6. Automated advisory interpretation

Public API
----------
    calculate_xirr(cashflows)
    simulate_sip(nav_data, monthly_amount, start_date, end_date)
    generate_sip_report(fund_nav, benchmark_nav=None)
"""

from __future__ import annotations

import datetime as dt
from typing import Optional, List, Tuple, Dict

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

from config import RISK_FREE_RATE
from data.models import (
    NAVData,
    SIPSimulationResult,
    LumpSumComparison,
    RollingSIPDistribution,
    SIPDateSensitivity,
    SIPReturnReport,
)


# ────────────────────────────────────────────────
# CONFIGURATION
# ────────────────────────────────────────────────

DEFAULT_SIP_AMOUNT = 10_000.0       # ₹10,000 monthly

DEFAULT_SIP_PERIODS: List[Tuple[str, float]] = [
    ("1 Year",   1.0),
    ("3 Years",  3.0),
    ("5 Years",  5.0),
    ("7 Years",  7.0),
    ("10 Years", 10.0),
]

# For rolling SIP analysis — use monthly stepping to keep it fast
ROLLING_SIP_WINDOWS: List[Tuple[str, float]] = [
    ("3 Years",  3.0),
    ("5 Years",  5.0),
    ("7 Years",  7.0),
    ("10 Years", 10.0),
]

# For date sensitivity — analyse these specific days
SIP_SENSITIVITY_DAYS = [1, 5, 10, 15, 20, 25]
SIP_SENSITIVITY_YEARS = 5.0


# ────────────────────────────────────────────────
# CORE: XIRR Calculator (Newton-Raphson)
# ────────────────────────────────────────────────

def calculate_xirr(
    cashflows: List[Tuple[dt.date, float]],
    initial_guess: float = 0.1,
    max_iterations: int = 200,
    tolerance: float = 1e-7,
) -> Optional[float]:
    """
    Calculate XIRR using the Newton-Raphson method.

    XIRR is the rate `r` that satisfies:
        Σ [ CF_i / (1 + r)^((d_i - d_0) / 365) ] = 0

    Parameters
    ----------
    cashflows : list of (date, amount) tuples
        Negative amounts = outflows (investments)
        Positive amounts = inflows (redemptions/final value)
    initial_guess : float
        Starting point for Newton-Raphson (0.1 = 10%)
    max_iterations : int
        Maximum iterations before giving up
    tolerance : float
        Convergence threshold for NPV

    Returns
    -------
    float or None
        XIRR as a decimal (0.15 = 15%), or None if no convergence
    """
    if not cashflows or len(cashflows) < 2:
        return None

    # Separate dates and amounts into arrays
    dates = [cf[0] for cf in cashflows]
    amounts = np.array([cf[1] for cf in cashflows], dtype=np.float64)

    # Convert dates to year fractions from first date
    d0 = dates[0]
    year_fracs = np.array(
        [(d - d0).days / 365.0 for d in dates],
        dtype=np.float64,
    )

    # Check: must have both positive and negative cashflows
    if np.all(amounts >= 0) or np.all(amounts <= 0):
        return None

    rate = initial_guess

    for _ in range(max_iterations):
        # NPV = Σ amount_i / (1 + rate)^year_frac_i
        # dNPV/drate = Σ -year_frac_i × amount_i / (1 + rate)^(year_frac_i + 1)

        # Guard against (1 + rate) being zero or negative
        base = 1.0 + rate
        if base <= 0:
            rate = abs(rate) / 2.0
            continue

        powers = np.power(base, year_fracs)
        npv = np.sum(amounts / powers)

        # Check convergence
        if abs(npv) < tolerance:
            return rate

        # Derivative
        d_npv = np.sum(-year_fracs * amounts / (powers * base))

        if abs(d_npv) < 1e-14:
            # Derivative too small — try a different starting point
            rate += 0.01
            continue

        # Newton-Raphson update
        new_rate = rate - npv / d_npv

        # Clamp to prevent wild oscillations
        # XIRR rarely exceeds 200% or goes below -90%
        new_rate = max(new_rate, -0.99)
        new_rate = min(new_rate, 10.0)

        rate = new_rate

    # ── Fallback: bisection method if Newton-Raphson fails ──
    return _xirr_bisection(amounts, year_fracs, tolerance)


def _xirr_bisection(
    amounts: np.ndarray,
    year_fracs: np.ndarray,
    tolerance: float = 1e-7,
    max_iterations: int = 300,
) -> Optional[float]:
    """
    Bisection fallback for XIRR when Newton-Raphson doesn't converge.
    Slower but guaranteed to converge if a root exists in [-0.99, 5.0].
    """

    def npv_at_rate(r: float) -> float:
        base = 1.0 + r
        if base <= 0:
            return float('inf')
        return float(np.sum(amounts / np.power(base, year_fracs)))

    low, high = -0.99, 5.0

    npv_low = npv_at_rate(low)
    npv_high = npv_at_rate(high)

    # Check if root exists in this range
    if npv_low * npv_high > 0:
        return None

    for _ in range(max_iterations):
        mid = (low + high) / 2.0
        npv_mid = npv_at_rate(mid)

        if abs(npv_mid) < tolerance:
            return mid

        if npv_mid * npv_low < 0:
            high = mid
            npv_high = npv_mid
        else:
            low = mid
            npv_low = npv_mid

    return (low + high) / 2.0


# ────────────────────────────────────────────────
# HELPER: Find nearest trading day NAV
# ────────────────────────────────────────────────

def _get_nav_on_or_after(
    nav_series: pd.Series,
    target: dt.date,
    max_forward: int = 10,
) -> Optional[Tuple[dt.date, float]]:
    """
    Find the NAV on `target` date or the nearest SUBSEQUENT trading day.
    For SIP, if the SIP date falls on a weekend/holiday, units are
    allotted on the next trading day.
    """
    for offset in range(max_forward + 1):
        check = target + dt.timedelta(days=offset)
        ts = pd.Timestamp(check)
        if ts in nav_series.index:
            return check, float(nav_series.loc[ts])
    return None


def _get_nav_on_or_before(
    nav_series: pd.Series,
    target: dt.date,
    max_back: int = 10,
) -> Optional[Tuple[dt.date, float]]:
    """Find the NAV on or before target date."""
    for offset in range(max_back + 1):
        check = target - dt.timedelta(days=offset)
        ts = pd.Timestamp(check)
        if ts in nav_series.index:
            return check, float(nav_series.loc[ts])
    return None


# ────────────────────────────────────────────────
# PUBLIC: Simulate SIP
# ────────────────────────────────────────────────

def simulate_sip(
    nav_data: NAVData,
    monthly_amount: float = DEFAULT_SIP_AMOUNT,
    start_date: Optional[dt.date] = None,
    end_date: Optional[dt.date] = None,
    sip_day: int = 1,
) -> SIPSimulationResult:
    """
    Simulate a monthly SIP from start_date to end_date.

    Process
    -------
    1. On the `sip_day` of each month, invest `monthly_amount`
    2. Allot units at the NAV of that day (or next trading day)
    3. At end_date, calculate total units × final NAV = final value
    4. Build cashflow list and compute XIRR

    Parameters
    ----------
    nav_data       : NAVData for the fund
    monthly_amount : amount invested per month
    start_date     : first SIP date (None → inception)
    end_date       : valuation date (None → latest)
    sip_day        : day of month for SIP (1-28)

    Returns
    -------
    SIPSimulationResult
    """
    series = nav_data.nav_series
    sip_day = min(sip_day, 28)  # avoid month-end issues

    if start_date is None:
        start_date = nav_data.inception_date
    if end_date is None:
        end_date = nav_data.latest_date

    # ── Generate SIP dates ──
    sip_dates: List[dt.date] = []
    current = dt.date(start_date.year, start_date.month, sip_day)
    if current < start_date:
        current += relativedelta(months=1)

    while current <= end_date:
        sip_dates.append(current)
        current += relativedelta(months=1)

    if len(sip_dates) < 1:
        raise ValueError(
            f"No SIP installments possible between {start_date} and {end_date}."
        )

    # ── Execute SIP: allot units at each date ──
    cashflows: List[Tuple[dt.date, float]] = []
    total_units = 0.0
    actual_installments = 0

    for sip_date in sip_dates:
        result = _get_nav_on_or_after(series, sip_date)
        if result is None:
            continue  # skip if no NAV available

        actual_date, nav_val = result
        if nav_val <= 0:
            continue

        units = monthly_amount / nav_val
        total_units += units
        cashflows.append((actual_date, -monthly_amount))  # outflow
        actual_installments += 1

    if actual_installments == 0:
        raise ValueError("No SIP installments could be executed.")

    # ── Final valuation ──
    end_result = _get_nav_on_or_before(series, end_date)
    if end_result is None:
        raise ValueError(f"No NAV available near end date {end_date}.")

    final_date, final_nav = end_result
    final_value = total_units * final_nav
    total_invested = monthly_amount * actual_installments

    # Add final value as positive cashflow (redemption)
    cashflows.append((final_date, final_value))

    # ── Calculate XIRR ──
    xirr = calculate_xirr(cashflows)
    xirr_pct = round(xirr * 100, 2) if xirr is not None else None

    # ── Absolute return ──
    abs_return = ((final_value / total_invested) - 1.0) * 100.0

    # ── Period calculation ──
    period_days = (final_date - cashflows[0][0]).days
    period_years = period_days / 365.25

    # ── Period label ──
    if period_years >= 1:
        label = f"{period_years:.1f} Years"
    else:
        months = int(period_years * 12)
        label = f"{months} Months"

    return SIPSimulationResult(
        period_label=label,
        sip_start_date=cashflows[0][0],
        sip_end_date=final_date,
        monthly_amount=monthly_amount,
        num_installments=actual_installments,
        total_invested=round(total_invested, 2),
        final_value=round(final_value, 2),
        absolute_return_pct=round(abs_return, 2),
        xirr_pct=xirr_pct,
        wealth_multiple=round(final_value / total_invested, 2),
    )


# ────────────────────────────────────────────────
# PUBLIC: SIP for standard trailing periods
# ────────────────────────────────────────────────

def calculate_trailing_sip_returns(
    nav_data: NAVData,
    monthly_amount: float = DEFAULT_SIP_AMOUNT,
    periods: Optional[List[Tuple[str, float]]] = None,
    sip_day: int = 1,
) -> List[SIPSimulationResult]:
    """
    Calculate SIP returns for standard trailing periods
    (1Y, 3Y, 5Y, 7Y, 10Y from today backwards).
    """
    if periods is None:
        periods = DEFAULT_SIP_PERIODS

    end_date = nav_data.latest_date
    results: List[SIPSimulationResult] = []

    for label, years in periods:
        start = end_date - relativedelta(years=int(years),
                                         months=int((years % 1) * 12))

        if start < nav_data.inception_date:
            continue

        try:
            result = simulate_sip(
                nav_data, monthly_amount, start, end_date, sip_day
            )
            # Override the label with the standard one
            result = SIPSimulationResult(
                period_label=label,
                sip_start_date=result.sip_start_date,
                sip_end_date=result.sip_end_date,
                monthly_amount=result.monthly_amount,
                num_installments=result.num_installments,
                total_invested=result.total_invested,
                final_value=result.final_value,
                absolute_return_pct=result.absolute_return_pct,
                xirr_pct=result.xirr_pct,
                wealth_multiple=result.wealth_multiple,
            )
            results.append(result)
        except ValueError:
            continue

    return results


# ────────────────────────────────────────────────
# PUBLIC: SIP vs Lump Sum comparison
# ────────────────────────────────────────────────

def compare_sip_vs_lumpsum(
    nav_data: NAVData,
    monthly_amount: float = DEFAULT_SIP_AMOUNT,
    periods: Optional[List[Tuple[str, float]]] = None,
    sip_day: int = 1,
) -> List[LumpSumComparison]:
    """
    Compare SIP returns vs Lump Sum for each trailing period.

    For fair comparison:
    - SIP: monthly_amount × N months invested over time
    - Lump Sum: same TOTAL amount invested at the START
    """
    if periods is None:
        periods = DEFAULT_SIP_PERIODS

    end_date = nav_data.latest_date
    series = nav_data.nav_series
    comparisons: List[LumpSumComparison] = []

    for label, years in periods:
        start = end_date - relativedelta(years=int(years),
                                         months=int((years % 1) * 12))

        if start < nav_data.inception_date:
            continue

        # ── SIP ──
        try:
            sip_result = simulate_sip(
                nav_data, monthly_amount, start, end_date, sip_day
            )
        except ValueError:
            continue

        sip_xirr = sip_result.xirr_pct
        sip_invested = sip_result.total_invested
        sip_final = sip_result.final_value

        # ── Lump Sum: invest same total at the START ──
        start_result = _get_nav_on_or_after(series, start)
        end_result = _get_nav_on_or_before(series, end_date)

        if start_result is None or end_result is None:
            continue

        ls_start_date, ls_start_nav = start_result
        ls_end_date, ls_end_nav = end_result

        ls_invested = sip_invested  # same total amount
        ls_units = ls_invested / ls_start_nav
        ls_final = ls_units * ls_end_nav

        # Lump sum CAGR
        period_yrs = (ls_end_date - ls_start_date).days / 365.25
        if period_yrs >= 1:
            ls_cagr = ((ls_final / ls_invested) ** (1.0 / period_yrs) - 1.0) * 100
        else:
            ls_cagr = ((ls_final / ls_invested) - 1.0) * 100

        ls_cagr = round(ls_cagr, 2)

        # ── Advantage calculation ──
        if sip_xirr is not None:
            advantage = round(sip_xirr - ls_cagr, 2)
            if abs(advantage) < 0.5:
                winner = "TIE"
            elif advantage > 0:
                winner = "SIP"
            else:
                winner = "LUMP SUM"
        else:
            advantage = None
            winner = "N/A"

        comparisons.append(LumpSumComparison(
            period_label=label,
            sip_xirr_pct=sip_xirr,
            lumpsum_cagr_pct=ls_cagr,
            sip_total_invested=round(sip_invested, 2),
            sip_final_value=round(sip_final, 2),
            lumpsum_invested=round(ls_invested, 2),
            lumpsum_final_value=round(ls_final, 2),
            sip_advantage_pct=advantage,
            winner=winner,
        ))

    return comparisons


# ────────────────────────────────────────────────
# PUBLIC: Rolling SIP XIRR Distribution
# ────────────────────────────────────────────────

def calculate_rolling_sip_xirr(
    nav_data: NAVData,
    window_years: float,
    window_label: str = "",
    monthly_amount: float = DEFAULT_SIP_AMOUNT,
    sip_day: int = 1,
    step_months: int = 1,
    benchmark_nav: Optional[NAVData] = None,
) -> RollingSIPDistribution:
    """
    Calculate SIP XIRR for every possible start date,
    rolling forward by `step_months` each time.

    This produces a DISTRIBUTION of SIP returns — answering:
    "If I had started a SIP on any random month, what would
    my return distribution look like?"
    """
    if not window_label:
        window_label = f"{window_years:.0f} Year{'s' if window_years != 1 else ''}"

    end_limit = nav_data.latest_date
    window_offset = relativedelta(years=int(window_years),
                                  months=int((window_years % 1) * 12))

    # Generate all possible start months
    first_possible = nav_data.inception_date
    last_possible = end_limit - window_offset

    if last_possible < first_possible:
        raise ValueError(
            f"Insufficient history for {window_label} rolling SIP. "
            f"Fund: {nav_data.history_years:.1f}y, need: {window_years:.1f}y."
        )

    # ── Iterate through start months ──
    xirr_values: List[float] = []
    start_dates: List[dt.date] = []
    bench_xirr_values: List[float] = []

    current_start = dt.date(first_possible.year, first_possible.month, sip_day)
    if current_start < first_possible:
        current_start += relativedelta(months=1)

    while current_start <= last_possible:
        sip_end = current_start + window_offset

        if sip_end > end_limit:
            break

        # Fund SIP
        try:
            result = simulate_sip(
                nav_data, monthly_amount, current_start, sip_end, sip_day
            )
            if result.xirr_pct is not None:
                xirr_values.append(result.xirr_pct)
                start_dates.append(current_start)

                # Benchmark SIP (if provided)
                if benchmark_nav is not None:
                    try:
                        bench_result = simulate_sip(
                            benchmark_nav, monthly_amount,
                            current_start, sip_end, sip_day
                        )
                        if bench_result.xirr_pct is not None:
                            bench_xirr_values.append(bench_result.xirr_pct)
                        else:
                            bench_xirr_values.append(float('nan'))
                    except (ValueError, Exception):
                        bench_xirr_values.append(float('nan'))
        except (ValueError, Exception):
            pass

        current_start += relativedelta(months=step_months)

    if len(xirr_values) < 3:
        raise ValueError(
            f"Too few observations ({len(xirr_values)}) for {window_label} rolling SIP."
        )

    # ── Statistics ──
    arr = np.array(xirr_values)
    num_obs = len(arr)

    rf_pct = RISK_FREE_RATE * 100.0

    # ── Benchmark comparison ──
    win_rate = None
    bench_mean = None

    if bench_xirr_values:
        bench_arr = np.array(bench_xirr_values)
        valid_mask = ~np.isnan(bench_arr)
        if np.sum(valid_mask) > 0:
            valid_fund = arr[valid_mask]
            valid_bench = bench_arr[valid_mask]
            win_rate = round(
                float(np.sum(valid_fund > valid_bench) / len(valid_fund) * 100), 2
            )
            bench_mean = round(float(np.nanmean(bench_arr)), 2)

    # Min/max start dates
    min_idx = int(np.argmin(arr))
    max_idx = int(np.argmax(arr))

    return RollingSIPDistribution(
        period_label=window_label,
        period_years=window_years,
        num_observations=num_obs,
        mean_xirr_pct=round(float(np.mean(arr)), 2),
        median_xirr_pct=round(float(np.median(arr)), 2),
        min_xirr_pct=round(float(np.min(arr)), 2),
        max_xirr_pct=round(float(np.max(arr)), 2),
        std_dev_pct=round(float(np.std(arr, ddof=1)), 2) if num_obs > 1 else 0.0,
        percentile_10_pct=round(float(np.percentile(arr, 10)), 2),
        percentile_25_pct=round(float(np.percentile(arr, 25)), 2),
        percentile_75_pct=round(float(np.percentile(arr, 75)), 2),
        percentile_90_pct=round(float(np.percentile(arr, 90)), 2),
        positive_xirr_pct=round(float(np.sum(arr > 0) / num_obs * 100), 2),
        above_risk_free_pct=round(float(np.sum(arr > rf_pct) / num_obs * 100), 2),
        min_xirr_start_date=start_dates[min_idx] if start_dates else None,
        max_xirr_start_date=start_dates[max_idx] if start_dates else None,
        benchmark_mean_xirr_pct=bench_mean,
        win_rate_vs_benchmark_pct=win_rate,
    )


# ────────────────────────────────────────────────
# PUBLIC: SIP Date Sensitivity
# ────────────────────────────────────────────────

def calculate_sip_date_sensitivity(
    nav_data: NAVData,
    period_years: float = SIP_SENSITIVITY_YEARS,
    monthly_amount: float = DEFAULT_SIP_AMOUNT,
    days: Optional[List[int]] = None,
) -> SIPDateSensitivity:
    """
    Analyse whether the day-of-month for SIP matters.

    Simulates SIPs starting on different days of the month
    (1st, 5th, 10th, 15th, 20th, 25th) and compares XIRR.

    Spoiler: In most cases, the difference is < 0.5% —
    confirming that SIP date selection anxiety is overblown.
    """
    if days is None:
        days = SIP_SENSITIVITY_DAYS

    end_date = nav_data.latest_date
    start_date = end_date - relativedelta(
        years=int(period_years),
        months=int((period_years % 1) * 12)
    )

    if start_date < nav_data.inception_date:
        start_date = nav_data.inception_date

    # ── Calculate average rolling SIP XIRR for each day ──
    day_results: Dict[int, float] = {}

    for day in days:
        xirr_values = []
        step_date = start_date

        # Roll through multiple start points to get an average
        while step_date + relativedelta(years=int(period_years)) <= end_date:
            sip_end = step_date + relativedelta(years=int(period_years))
            try:
                result = simulate_sip(
                    nav_data, monthly_amount, step_date, sip_end, sip_day=day
                )
                if result.xirr_pct is not None:
                    xirr_values.append(result.xirr_pct)
            except (ValueError, Exception):
                pass
            step_date += relativedelta(months=3)

        if xirr_values:
            day_results[day] = round(float(np.mean(xirr_values)), 2)

    if not day_results:
        raise ValueError("Could not compute SIP date sensitivity.")

    best_day = max(day_results, key=day_results.get)
    worst_day = min(day_results, key=day_results.get)

    label = f"{period_years:.0f} Year{'s' if period_years != 1 else ''}"

    return SIPDateSensitivity(
        period_label=label,
        day_results=day_results,
        best_day=best_day,
        worst_day=worst_day,
        best_day_xirr_pct=day_results[best_day],
        worst_day_xirr_pct=day_results[worst_day],
        spread_pct=round(day_results[best_day] - day_results[worst_day], 2),
    )


# ────────────────────────────────────────────────
# INTERPRETATION ENGINE
# ────────────────────────────────────────────────

def _interpret_sip(
    sip_results: List[SIPSimulationResult],
    lumpsum_comparisons: List[LumpSumComparison],
    rolling_sip: List[RollingSIPDistribution],
    date_sensitivity: Optional[SIPDateSensitivity],
) -> List[str]:
    """Generate advisory-grade insights from SIP analysis."""
    insights: List[str] = []

    # ════════════════════════════════════════
    # TRAILING SIP RETURNS
    # ════════════════════════════════════════
    if sip_results:
        insights.append("─" * 55)
        insights.append("💰  SIP RETURN ANALYSIS")
        insights.append("─" * 55)

        for result in sip_results:
            if result.xirr_pct is not None:
                if result.xirr_pct > 15:
                    icon = "🏆"
                elif result.xirr_pct > 12:
                    icon = "✅"
                elif result.xirr_pct > 8:
                    icon = "🔶"
                elif result.xirr_pct > 0:
                    icon = "⚠️"
                else:
                    icon = "❌"

                insights.append(
                    f"{icon}  {result.period_label} SIP XIRR: "
                    f"{result.xirr_pct:+.2f}% | "
                    f"₹{result.total_invested:,.0f} → ₹{result.final_value:,.0f} "
                    f"({result.wealth_multiple:.2f}×)"
                )

        # ── Wealth creation insight ──
        long_sip = [r for r in sip_results if r.wealth_multiple >= 2.0]
        if long_sip:
            best = max(long_sip, key=lambda r: r.wealth_multiple)
            insights.append(
                f"\n💎  Best wealth creation: {best.period_label} SIP turned "
                f"₹{best.total_invested:,.0f} into ₹{best.final_value:,.0f} "
                f"— a {best.wealth_multiple:.2f}× multiple!"
            )

        insights.append("")

    # ════════════════════════════════════════
    # SIP vs LUMP SUM
    # ════════════════════════════════════════
    if lumpsum_comparisons:
        insights.append("─" * 55)
        insights.append("⚔️   SIP vs LUMP SUM COMPARISON")
        insights.append("─" * 55)

        sip_wins = sum(1 for c in lumpsum_comparisons if c.winner == "SIP")
        ls_wins = sum(1 for c in lumpsum_comparisons if c.winner == "LUMP SUM")
        ties = sum(1 for c in lumpsum_comparisons if c.winner == "TIE")

        for comp in lumpsum_comparisons:
            if comp.sip_advantage_pct is not None:
                if comp.winner == "SIP":
                    insights.append(
                        f"  ✅ {comp.period_label}: SIP wins by "
                        f"{comp.sip_advantage_pct:+.2f}% "
                        f"(SIP: {comp.sip_xirr_pct:.2f}% vs LS: {comp.lumpsum_cagr_pct:.2f}%)"
                    )
                elif comp.winner == "LUMP SUM":
                    insights.append(
                        f"  📈 {comp.period_label}: Lump Sum wins by "
                        f"{abs(comp.sip_advantage_pct):.2f}% "
                        f"(LS: {comp.lumpsum_cagr_pct:.2f}% vs SIP: {comp.sip_xirr_pct:.2f}%)"
                    )
                else:
                    insights.append(
                        f"  🔶 {comp.period_label}: Virtual tie "
                        f"(SIP: {comp.sip_xirr_pct:.2f}% ≈ LS: {comp.lumpsum_cagr_pct:.2f}%)"
                    )

        insights.append(
            f"\n  Score: SIP {sip_wins} | Lump Sum {ls_wins} | Tie {ties}"
        )

        if ls_wins > sip_wins:
            insights.append(
                "  📊  In a generally RISING market, lump sum tends to win "
                "because money is invested earlier and compounds longer."
            )
        elif sip_wins > ls_wins:
            insights.append(
                "  📊  SIP winning suggests VOLATILE periods where rupee-cost "
                "averaging helped acquire units at lower prices."
            )
        else:
            insights.append(
                "  📊  No clear winner — both strategies are viable for this fund."
            )

        insights.append(
            "  💡  TIP: If you have a lump sum AND are nervous about timing, "
            "use a Systematic Transfer Plan (STP) over 6-12 months."
        )
        insights.append("")

    # ════════════════════════════════════════
    # ROLLING SIP DISTRIBUTION
    # ════════════════════════════════════════
    if rolling_sip:
        insights.append("─" * 55)
        insights.append("📊  ROLLING SIP XIRR DISTRIBUTION")
        insights.append("─" * 55)

        for dist in rolling_sip:
            insights.append(
                f"\n  {dist.period_label} SIP ({dist.num_observations} start points):"
            )

            # Positive probability
            if dist.positive_xirr_pct == 100:
                insights.append(
                    f"  ✅  100% of start dates gave positive SIP returns — "
                    f"remarkable consistency."
                )
            elif dist.positive_xirr_pct >= 95:
                insights.append(
                    f"  ✅  {dist.positive_xirr_pct:.1f}% of start dates gave "
                    f"positive returns — very reliable."
                )
            elif dist.positive_xirr_pct >= 80:
                insights.append(
                    f"  🔶  {dist.positive_xirr_pct:.1f}% positive — "
                    f"generally reliable but timing-sensitive."
                )
            else:
                insights.append(
                    f"  ❌  Only {dist.positive_xirr_pct:.1f}% positive — "
                    f"high risk of loss for this SIP window."
                )

            # Return range
            insights.append(
                f"  📊  XIRR range: {dist.min_xirr_pct:+.2f}% to "
                f"{dist.max_xirr_pct:+.2f}% "
                f"(mean: {dist.mean_xirr_pct:+.2f}%, "
                f"median: {dist.median_xirr_pct:+.2f}%)"
            )

            # Benchmark win rate
            if dist.win_rate_vs_benchmark_pct is not None:
                wr = dist.win_rate_vs_benchmark_pct
                if wr >= 70:
                    insights.append(
                        f"  🏆  SIP beats benchmark index SIP in "
                        f"{wr:.1f}% of start dates — strong outperformance."
                    )
                elif wr >= 50:
                    insights.append(
                        f"  🔶  SIP beats benchmark index SIP in "
                        f"{wr:.1f}% of start dates — moderate edge."
                    )
                else:
                    insights.append(
                        f"  ❌  SIP beats benchmark index SIP in only "
                        f"{wr:.1f}% of start dates — index SIP may be better."
                    )

            # Worst start date warning
            if dist.min_xirr_start_date:
                insights.append(
                    f"  ⚠️   Worst SIP start: {dist.min_xirr_start_date} "
                    f"→ XIRR = {dist.min_xirr_pct:+.2f}%"
                )

        insights.append("")

    # ════════════════════════════════════════
    # DATE SENSITIVITY
    # ════════════════════════════════════════
    if date_sensitivity:
        insights.append("─" * 55)
        insights.append("📆  SIP DATE SENSITIVITY ANALYSIS")
        insights.append("─" * 55)

        ds = date_sensitivity

        if ds.spread_pct < 0.5:
            insights.append(
                f"✅  The day of month barely matters! "
                f"Spread between best and worst day: only {ds.spread_pct:.2f}%"
            )
            insights.append(
                f"    Best: {ds.best_day}th ({ds.best_day_xirr_pct:.2f}%) | "
                f"Worst: {ds.worst_day}th ({ds.worst_day_xirr_pct:.2f}%)"
            )
            insights.append(
                "    💡  Don't overthink your SIP date. "
                "Just pick whatever is convenient."
            )
        elif ds.spread_pct < 1.5:
            insights.append(
                f"🔶  Modest variation across SIP days: "
                f"spread = {ds.spread_pct:.2f}%"
            )
            insights.append(
                f"    Best: {ds.best_day}th ({ds.best_day_xirr_pct:.2f}%) | "
                f"Worst: {ds.worst_day}th ({ds.worst_day_xirr_pct:.2f}%)"
            )
        else:
            insights.append(
                f"⚠️   Noticeable variation: spread = {ds.spread_pct:.2f}%"
            )
            insights.append(
                f"    Best day: {ds.best_day}th → avg XIRR: {ds.best_day_xirr_pct:.2f}%"
            )
            insights.append(
                f"    Worst day: {ds.worst_day}th → avg XIRR: {ds.worst_day_xirr_pct:.2f}%"
            )

        # Print all days
        insights.append("\n    Day-wise average XIRR:")
        for day in sorted(ds.day_results.keys()):
            xirr = ds.day_results[day]
            bar_len = max(0, int((xirr - ds.worst_day_xirr_pct) / max(ds.spread_pct, 0.1) * 20))
            bar = "█" * bar_len
            marker = " ← BEST" if day == ds.best_day else (" ← WORST" if day == ds.worst_day else "")
            insights.append(
                f"      {day:>2}th:  {xirr:>6.2f}%  {bar}{marker}"
            )

        insights.append("")

    return insights


# ────────────────────────────────────────────────
# PUBLIC: Full report (one-call convenience)
# ────────────────────────────────────────────────

def generate_sip_report(
    fund_nav: NAVData,
    benchmark_nav: Optional[NAVData] = None,
    monthly_amount: float = DEFAULT_SIP_AMOUNT,
    sip_day: int = 1,
) -> SIPReturnReport:
    """
    End-to-end SIP analysis:
      1. Trailing SIP returns for standard periods
      2. SIP vs Lump Sum comparison
      3. Rolling SIP XIRR distribution
      4. SIP date sensitivity
      5. Automated interpretation

    Parameters
    ----------
    fund_nav       : NAVData for the fund
    benchmark_nav  : NAVData for benchmark (optional)
    monthly_amount : SIP amount (default ₹10,000)
    sip_day        : day of month (default 1st)

    Returns
    -------
    SIPReturnReport
    """
    # ── 1. Trailing SIP returns ──
    sip_results = calculate_trailing_sip_returns(
        fund_nav, monthly_amount, sip_day=sip_day
    )

    # ── 2. SIP vs Lump Sum ──
    lumpsum_comparisons = compare_sip_vs_lumpsum(
        fund_nav, monthly_amount, sip_day=sip_day
    )

    # ── 3. Rolling SIP XIRR ──
    rolling_sip: List[RollingSIPDistribution] = []
    for label, years in ROLLING_SIP_WINDOWS:
        if fund_nav.history_years < years + 1:
            continue
        try:
            dist = calculate_rolling_sip_xirr(
                fund_nav, years, label, monthly_amount,
                sip_day=sip_day, step_months=1,
                benchmark_nav=benchmark_nav,
            )
            rolling_sip.append(dist)
        except ValueError:
            continue

    # ── 4. Date sensitivity ──
    date_sensitivity = None
    try:
        date_sensitivity = calculate_sip_date_sensitivity(
            fund_nav, monthly_amount=monthly_amount
        )
    except ValueError:
        pass

    # ── 5. Interpretation ──
    interpretation = _interpret_sip(
        sip_results, lumpsum_comparisons, rolling_sip, date_sensitivity
    )

    return SIPReturnReport(
        scheme_info=fund_nav.scheme_info,
        benchmark_info=benchmark_nav.scheme_info if benchmark_nav else None,
        as_of_date=fund_nav.latest_date,
        sip_results=sip_results,
        lumpsum_comparisons=lumpsum_comparisons,
        rolling_sip=rolling_sip,
        date_sensitivity=date_sensitivity,
        interpretation=interpretation,
    )