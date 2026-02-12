"""
metrics/risk_adjusted.py
────────────────────────
SECTION 2 — Risk-Adjusted Return Ratios

Implements all seven core risk-adjusted metrics:
    1. Standard Deviation (σ)     — total volatility
    2. Beta (β)                   — systematic/market risk
    3. Jensen's Alpha (α)         — skill-based excess return
    4. Sharpe Ratio               — return per unit of total risk
    5. Sortino Ratio              — return per unit of downside risk
    6. Treynor Ratio              — return per unit of market risk
    7. Information Ratio          — consistency of active management

Public API
----------
    calculate_volatility(fund_nav, period_years=3)
    calculate_beta(fund_nav, benchmark_nav, period_years=3)
    calculate_risk_adjusted_ratios(fund_nav, benchmark_nav=None, period_years=3)
    generate_risk_adjusted_report(fund_nav, benchmark_nav=None, period_years=3)
"""

from __future__ import annotations

import datetime as dt
from typing import Optional, List, Tuple

import numpy as np
import pandas as pd

from config import RISK_FREE_RATE
from data.models import (
    NAVData,
    VolatilityMetrics,
    BetaAnalysis,
    RiskAdjustedRatios,
    RiskAdjustedReport,
)


# ────────────────────────────────────────────────
# HELPER: Build monthly returns from NAV
# ────────────────────────────────────────────────

def _monthly_returns(
    nav_data: NAVData,
    period_years: Optional[float] = None,
) -> pd.Series:
    """
    Convert daily NAV to monthly returns.
    Optionally restrict to the last `period_years`.

    Returns pd.Series indexed by month-end date,
    values are decimal returns (e.g. 0.05 = 5%).
    """
    series = nav_data.nav_series.copy()
    monthly_nav = series.resample('ME').last().dropna()
    monthly_ret = monthly_nav.pct_change().dropna()

    if period_years is not None:
        n_months = int(period_years * 12)
        if len(monthly_ret) > n_months:
            monthly_ret = monthly_ret.iloc[-n_months:]

    return monthly_ret


def _align_monthly(
    fund_nav: NAVData,
    benchmark_nav: NAVData,
    period_years: Optional[float] = None,
) -> Tuple[pd.Series, pd.Series]:
    """
    Build aligned monthly returns for fund and benchmark.
    """
    fund_m = _monthly_returns(fund_nav)
    bench_m = _monthly_returns(benchmark_nav)

    common = fund_m.index.intersection(bench_m.index)
    if len(common) == 0:
        raise ValueError("No overlapping monthly data between fund and benchmark.")

    fund_aligned = fund_m.loc[common]
    bench_aligned = bench_m.loc[common]

    if period_years is not None:
        n_months = int(period_years * 12)
        if len(fund_aligned) > n_months:
            fund_aligned = fund_aligned.iloc[-n_months:]
            bench_aligned = bench_aligned.iloc[-n_months:]

    return fund_aligned, bench_aligned


# ────────────────────────────────────────────────
# 1. STANDARD DEVIATION & DOWNSIDE DEVIATION
# ────────────────────────────────────────────────

def calculate_volatility(
    fund_nav: NAVData,
    period_years: Optional[float] = 3,
    mar: Optional[float] = None,
) -> VolatilityMetrics:
    """
    Calculate total and downside volatility metrics.

    Parameters
    ----------
    fund_nav     : NAVData for the fund
    period_years : analysis window (None = all history)
    mar          : Minimum Acceptable Return (annualised, decimal)
                   Default = risk-free rate

    Returns
    -------
    VolatilityMetrics

    Formulas
    --------
    Standard Deviation (annualised):
        σ_annual = σ_monthly × √12

    Downside Deviation:
        DD = √[ Σ min(Ri − MAR_monthly, 0)² / n ]
        DD_annual = DD_monthly × √12
    """
    if mar is None:
        mar = RISK_FREE_RATE

    monthly_ret = _monthly_returns(fund_nav, period_years)
    n = len(monthly_ret)

    if n < 6:
        raise ValueError(
            f"Need at least 6 months of data. Found: {n} months."
        )

    ret_arr = monthly_ret.values

    # ── Total volatility ──
    monthly_std = float(np.std(ret_arr, ddof=1))
    annual_std = monthly_std * np.sqrt(12)

    # ── Downside deviation ──
    mar_monthly = (1 + mar) ** (1 / 12) - 1     # convert annual MAR to monthly
    downside_diffs = np.minimum(ret_arr - mar_monthly, 0.0)
    monthly_dd = float(np.sqrt(np.mean(downside_diffs ** 2)))
    annual_dd = monthly_dd * np.sqrt(12)

    # ── Return statistics ──
    monthly_mean = float(np.mean(ret_arr))
    annual_mean = monthly_mean * 12
    annual_median = float(np.median(ret_arr)) * 12
    neg_months = int(np.sum(ret_arr < 0))

    return VolatilityMetrics(
        monthly_std_dev_pct=round(monthly_std * 100, 4),
        annualised_std_dev_pct=round(annual_std * 100, 2),
        monthly_downside_dev_pct=round(monthly_dd * 100, 4),
        annualised_downside_dev_pct=round(annual_dd * 100, 2),
        annualised_mean_return_pct=round(annual_mean * 100, 2),
        annualised_median_return_pct=round(annual_median * 100, 2),
        num_months=n,
        num_negative_months=neg_months,
        pct_negative_months=round(neg_months / n * 100, 1),
        worst_month_pct=round(float(np.min(ret_arr)) * 100, 2),
        best_month_pct=round(float(np.max(ret_arr)) * 100, 2),
        mar_pct=round(mar * 100, 2),
    )


# ────────────────────────────────────────────────
# 2. BETA (Regression-based)
# ────────────────────────────────────────────────

def calculate_beta(
    fund_nav: NAVData,
    benchmark_nav: NAVData,
    period_years: Optional[float] = 3,
) -> BetaAnalysis:
    """
    Calculate Beta via OLS regression of fund returns on benchmark returns.

    Model:  R_fund = α + β × R_benchmark + ε

    Also computes:
      - R² (coefficient of determination)
      - Correlation (Pearson)
      - Tracking Error (σ of active returns)
      - Annualised Alpha from regression

    Parameters
    ----------
    fund_nav      : NAVData for the fund
    benchmark_nav : NAVData for the benchmark
    period_years  : analysis window

    Returns
    -------
    BetaAnalysis
    """
    fund_m, bench_m = _align_monthly(fund_nav, benchmark_nav, period_years)
    n = len(fund_m)

    if n < 12:
        raise ValueError(
            f"Need at least 12 months of overlapping data. Found: {n}."
        )

    f = fund_m.values
    b = bench_m.values

    # ── OLS Regression: f = α + β × b ──
    # β = Cov(f, b) / Var(b)
    # α = mean(f) − β × mean(b)

    cov_fb = np.cov(f, b, ddof=1)[0, 1]
    var_b = np.var(b, ddof=1)
    mean_f = np.mean(f)
    mean_b = np.mean(b)

    if var_b < 1e-14:
        raise ValueError("Benchmark has zero variance — cannot compute beta.")

    beta = float(cov_fb / var_b)
    alpha_monthly = float(mean_f - beta * mean_b)

    # ── R² ──
    ss_total = np.sum((f - mean_f) ** 2)
    predicted = alpha_monthly + beta * b
    ss_residual = np.sum((f - predicted) ** 2)

    if ss_total > 0:
        r_squared = float(1 - ss_residual / ss_total)
    else:
        r_squared = 0.0

    # ── Correlation ──
    std_f = np.std(f, ddof=1)
    std_b = np.std(b, ddof=1)
    if std_f > 0 and std_b > 0:
        correlation = float(cov_fb / (std_f * std_b))
    else:
        correlation = 0.0

    # ── Tracking Error ──
    active_returns = f - b
    tracking_error_monthly = float(np.std(active_returns, ddof=1))
    tracking_error_annual = tracking_error_monthly * np.sqrt(12)

    # ── Annualise alpha ──
    # Compound monthly alpha to annual
    alpha_annual = ((1 + alpha_monthly) ** 12 - 1) * 100

    # ── Beta category ──
    if beta > 1.1:
        beta_cat = "Aggressive"
    elif beta > 0.9:
        beta_cat = "Neutral"
    elif beta > 0.7:
        beta_cat = "Defensive"
    else:
        beta_cat = "Very Defensive"

    return BetaAnalysis(
        beta=round(beta, 4),
        alpha_monthly=round(alpha_monthly, 6),
        alpha_annualised_pct=round(alpha_annual, 2),
        r_squared=round(r_squared, 4),
        correlation=round(correlation, 4),
        tracking_error_pct=round(tracking_error_annual * 100, 2),
        num_months=n,
        beta_category=beta_cat,
    )


# ────────────────────────────────────────────────
# 3-7. ALL RISK-ADJUSTED RATIOS
# ────────────────────────────────────────────────

def calculate_risk_adjusted_ratios(
    fund_nav: NAVData,
    benchmark_nav: Optional[NAVData] = None,
    period_years: Optional[float] = 3,
) -> RiskAdjustedRatios:
    """
    Calculate all seven risk-adjusted ratios.

    Formulas
    --------
    Jensen's Alpha:
        α = R_fund − [R_rf + β × (R_bench − R_rf)]

    Sharpe Ratio:
        S = (R_fund − R_rf) / σ_fund

    Sortino Ratio:
        So = (R_fund − R_rf) / σ_downside

    Treynor Ratio:
        T = (R_fund − R_rf) / β

    Information Ratio:
        IR = (R_fund − R_bench) / Tracking_Error

    Parameters
    ----------
    fund_nav      : NAVData for the fund
    benchmark_nav : NAVData for the benchmark (optional)
    period_years  : analysis window (default 3 years)

    Returns
    -------
    RiskAdjustedRatios
    """
    rf = RISK_FREE_RATE
    rf_pct = rf * 100

    # ── Volatility ──
    vol = calculate_volatility(fund_nav, period_years, mar=rf)
    fund_return = vol.annualised_mean_return_pct / 100.0
    fund_return_pct = vol.annualised_mean_return_pct
    std_dev = vol.annualised_std_dev_pct / 100.0
    downside_dev = vol.annualised_downside_dev_pct / 100.0

    # ── Sharpe Ratio ──
    # S = (R_fund − R_rf) / σ
    if std_dev > 1e-8:
        sharpe = (fund_return - rf) / std_dev
    else:
        sharpe = 0.0

    # ── Sortino Ratio ──
    # So = (R_fund − R_rf) / σ_downside
    if downside_dev > 1e-8:
        sortino = (fund_return - rf) / downside_dev
    else:
        sortino = 0.0

    # ── Beta-dependent ratios (need benchmark) ──
    beta_val = None
    benchmark_return_pct = None
    jensens_alpha_pct = None
    treynor = None
    information = None
    beta_analysis = None

    if benchmark_nav is not None:
        try:
            beta_analysis = calculate_beta(fund_nav, benchmark_nav, period_years)
            beta_val = beta_analysis.beta

            # Benchmark return
            bench_m = _monthly_returns(benchmark_nav, period_years)
            benchmark_return = float(np.mean(bench_m.values)) * 12
            benchmark_return_pct = round(benchmark_return * 100, 2)

            # ── Jensen's Alpha ──
            # α = R_fund − [R_rf + β × (R_bench − R_rf)]
            expected_return = rf + beta_val * (benchmark_return - rf)
            jensens_alpha = fund_return - expected_return
            jensens_alpha_pct = round(jensens_alpha * 100, 2)

            # ── Treynor Ratio ──
            # T = (R_fund − R_rf) / β
            if abs(beta_val) > 1e-6:
                treynor = (fund_return - rf) / beta_val
            else:
                treynor = 0.0

            # ── Information Ratio ──
            # IR = (R_fund − R_bench) / Tracking Error
            te = beta_analysis.tracking_error_pct / 100.0
            if te > 1e-8:
                information = (fund_return - benchmark_return) / te
            else:
                information = 0.0

        except ValueError:
            pass

    # ── Determine period for the report ──
    fund_m = _monthly_returns(fund_nav, period_years)
    actual_years = len(fund_m) / 12.0

    # ── Grades ──
    sharpe_grade = _grade_sharpe(sharpe)
    sortino_grade = _grade_sortino(sortino)
    alpha_grade = _grade_alpha(jensens_alpha_pct) if jensens_alpha_pct is not None else None
    treynor_grade = _grade_treynor(treynor) if treynor is not None else None
    info_grade = _grade_information(information) if information is not None else None

    return RiskAdjustedRatios(
        fund_return_pct=round(fund_return_pct, 2),
        benchmark_return_pct=benchmark_return_pct,
        risk_free_rate_pct=round(rf_pct, 2),
        period_years=round(actual_years, 1),
        jensens_alpha_pct=jensens_alpha_pct,
        alpha_grade=alpha_grade,
        sharpe_ratio=round(sharpe, 4),
        sharpe_grade=sharpe_grade,
        sortino_ratio=round(sortino, 4),
        sortino_grade=sortino_grade,
        treynor_ratio=round(treynor, 4) if treynor is not None else None,
        treynor_grade=treynor_grade,
        information_ratio=round(information, 4) if information is not None else None,
        information_grade=info_grade,
        beta=round(beta_val, 4) if beta_val is not None else None,
        std_dev_pct=round(std_dev * 100, 2),
    )


# ────────────────────────────────────────────────
# GRADING FUNCTIONS
# ────────────────────────────────────────────────

def _grade_sharpe(ratio: float) -> str:
    if ratio > 1.0:
        return "EXCELLENT"
    elif ratio > 0.5:
        return "GOOD"
    elif ratio > 0.0:
        return "ACCEPTABLE"
    else:
        return "POOR"


def _grade_sortino(ratio: float) -> str:
    if ratio > 2.0:
        return "EXCELLENT"
    elif ratio > 1.0:
        return "GOOD"
    elif ratio > 0.5:
        return "AVERAGE"
    else:
        return "POOR"


def _grade_alpha(alpha_pct: Optional[float]) -> Optional[str]:
    if alpha_pct is None:
        return None
    if alpha_pct > 3.0:
        return "EXCELLENT"
    elif alpha_pct > 1.0:
        return "GOOD"
    elif alpha_pct > 0.0:
        return "MARGINAL"
    else:
        return "NEGATIVE"


def _grade_treynor(ratio: Optional[float]) -> Optional[str]:
    if ratio is None:
        return None
    if ratio > 0.12:
        return "EXCELLENT"
    elif ratio > 0.06:
        return "GOOD"
    elif ratio > 0.0:
        return "ACCEPTABLE"
    else:
        return "POOR"


def _grade_information(ratio: Optional[float]) -> Optional[str]:
    if ratio is None:
        return None
    if ratio > 0.75:
        return "EXCEPTIONAL"
    elif ratio > 0.50:
        return "VERY GOOD"
    elif ratio > 0.25:
        return "GOOD"
    elif ratio > 0.0:
        return "MARGINAL"
    else:
        return "NEGATIVE"


# ────────────────────────────────────────────────
# MULTI-PERIOD ANALYSIS
# ────────────────────────────────────────────────

def calculate_multi_period_ratios(
    fund_nav: NAVData,
    benchmark_nav: Optional[NAVData] = None,
    periods: Optional[List[float]] = None,
) -> List[Tuple[float, RiskAdjustedRatios, Optional[BetaAnalysis], VolatilityMetrics]]:
    """
    Calculate risk-adjusted ratios across multiple time windows.

    Parameters
    ----------
    periods : list of period lengths in years
              Default: [1, 3, 5]

    Returns
    -------
    List of (period_years, ratios, beta_analysis, volatility) tuples
    """
    if periods is None:
        periods = [1.0, 3.0, 5.0]

    results = []

    for p in periods:
        if fund_nav.history_years < p:
            continue

        try:
            vol = calculate_volatility(fund_nav, p, mar=RISK_FREE_RATE)
            beta_a = None
            if benchmark_nav is not None:
                try:
                    beta_a = calculate_beta(fund_nav, benchmark_nav, p)
                except ValueError:
                    pass

            ratios = calculate_risk_adjusted_ratios(fund_nav, benchmark_nav, p)
            results.append((p, ratios, beta_a, vol))
        except ValueError:
            continue

    return results


# ────────────────────────────────────────────────
# INTERPRETATION ENGINE
# ────────────────────────────────────────────────

def _interpret_risk_adjusted(
    vol: VolatilityMetrics,
    beta_analysis: Optional[BetaAnalysis],
    ratios: RiskAdjustedRatios,
    multi_period: Optional[List[Tuple[float, RiskAdjustedRatios, Optional[BetaAnalysis], VolatilityMetrics]]] = None,
) -> List[str]:
    """Generate advisory-grade insights from risk-adjusted analysis."""
    insights: List[str] = []

    # ════════════════════════════════════════
    # VOLATILITY ANALYSIS
    # ════════════════════════════════════════
    insights.append("─" * 55)
    insights.append("📊  VOLATILITY ANALYSIS")
    insights.append("─" * 55)

    std = vol.annualised_std_dev_pct
    if std < 12:
        insights.append(
            f"✅  Annualised σ = {std:.2f}% — LOW volatility. "
            f"Typical of large-cap or balanced funds."
        )
    elif std < 18:
        insights.append(
            f"🔶  Annualised σ = {std:.2f}% — MODERATE volatility. "
            f"Normal for diversified equity funds."
        )
    elif std < 25:
        insights.append(
            f"⚠️   Annualised σ = {std:.2f}% — HIGH volatility. "
            f"Expected for mid/small-cap funds."
        )
    else:
        insights.append(
            f"❌  Annualised σ = {std:.2f}% — VERY HIGH volatility. "
            f"Sectoral/thematic level risk."
        )

    # Downside vs total comparison
    dd = vol.annualised_downside_dev_pct
    if dd < std * 0.6:
        insights.append(
            f"✅  Downside deviation ({dd:.2f}%) is significantly less than "
            f"total σ ({std:.2f}%) — most volatility comes from UPSIDE moves."
        )
    elif dd < std * 0.8:
        insights.append(
            f"🔶  Downside deviation ({dd:.2f}%) is moderately less than "
            f"total σ ({std:.2f}%) — reasonable upside/downside split."
        )
    else:
        insights.append(
            f"⚠️   Downside deviation ({dd:.2f}%) is close to "
            f"total σ ({std:.2f}%) — fund volatility is skewed to the DOWNSIDE."
        )

    # Negative months
    insights.append(
        f"📊  {vol.num_negative_months}/{vol.num_months} months were negative "
        f"({vol.pct_negative_months:.1f}%)"
    )
    insights.append(
        f"    Worst month: {vol.worst_month_pct:+.2f}% | "
        f"Best month: {vol.best_month_pct:+.2f}%"
    )
    insights.append("")

    # ════════════════════════════════════════
    # BETA ANALYSIS
    # ════════════════════════════════════════
    if beta_analysis is not None:
        ba = beta_analysis
        insights.append("─" * 55)
        insights.append("📊  BETA & BENCHMARK RELATIONSHIP")
        insights.append("─" * 55)

        # Beta interpretation
        if ba.beta > 1.1:
            insights.append(
                f"📈  β = {ba.beta:.2f} ({ba.beta_category}) — fund is MORE "
                f"volatile than benchmark. In a +10% rally, expect ~{ba.beta * 10:+.1f}%. "
                f"In a -10% crash, expect ~{ba.beta * -10:+.1f}%."
            )
        elif ba.beta > 0.9:
            insights.append(
                f"📊  β = {ba.beta:.2f} ({ba.beta_category}) — fund moves "
                f"roughly in line with the benchmark."
            )
        else:
            insights.append(
                f"🛡️   β = {ba.beta:.2f} ({ba.beta_category}) — fund is LESS "
                f"volatile than benchmark. Dampens both gains and losses."
            )

        # R-squared
        r2 = ba.r_squared
        if r2 > 0.90:
            insights.append(
                f"📊  R² = {r2:.2f} — benchmark explains {r2 * 100:.0f}% of "
                f"fund movements. Fund closely tracks its benchmark."
            )
        elif r2 > 0.70:
            insights.append(
                f"📊  R² = {r2:.2f} — benchmark explains {r2 * 100:.0f}% of "
                f"fund movements. Fund takes meaningful active bets."
            )
        else:
            insights.append(
                f"📊  R² = {r2:.2f} — benchmark explains only {r2 * 100:.0f}% "
                f"of movements. Fund has a significantly different composition."
            )

        # Tracking error
        te = ba.tracking_error_pct
        if te < 3:
            insights.append(
                f"📊  Tracking Error = {te:.2f}% — very tight tracking "
                f"(closet indexer concern if TE < 2%)."
            )
        elif te < 8:
            insights.append(
                f"📊  Tracking Error = {te:.2f}% — moderate active management."
            )
        else:
            insights.append(
                f"📊  Tracking Error = {te:.2f}% — highly active management "
                f"(high conviction bets)."
            )

        # Regression alpha
        if ba.alpha_annualised_pct > 2:
            insights.append(
                f"✅  Regression Alpha = {ba.alpha_annualised_pct:+.2f}% per year "
                f"— statistically significant value addition."
            )
        elif ba.alpha_annualised_pct > 0:
            insights.append(
                f"🔶  Regression Alpha = {ba.alpha_annualised_pct:+.2f}% per year "
                f"— positive but modest."
            )
        else:
            insights.append(
                f"❌  Regression Alpha = {ba.alpha_annualised_pct:+.2f}% per year "
                f"— fund manager is destroying value after adjusting for beta."
            )

        insights.append("")

    # ════════════════════════════════════════
    # RATIO ANALYSIS
    # ════════════════════════════════════════
    insights.append("─" * 55)
    insights.append("📊  RISK-ADJUSTED RATIO ANALYSIS")
    insights.append("─" * 55)

    r = ratios
    grade_icons = {
        "EXCELLENT": "🏆", "EXCEPTIONAL": "🏆",
        "VERY GOOD": "✅",
        "GOOD": "✅",
        "ACCEPTABLE": "🔶", "AVERAGE": "🔶",
        "MARGINAL": "⚠️",
        "POOR": "❌", "NEGATIVE": "❌",
    }

    # 1. Sharpe
    icon = grade_icons.get(r.sharpe_grade, "")
    insights.append(
        f"{icon}  Sharpe Ratio = {r.sharpe_ratio:.3f} — {r.sharpe_grade}"
    )
    insights.append(
        f"     For every 1% of total risk, the fund earned "
        f"{r.sharpe_ratio:.3f}% excess return over risk-free rate."
    )

    # 2. Sortino
    icon = grade_icons.get(r.sortino_grade, "")
    insights.append(
        f"{icon}  Sortino Ratio = {r.sortino_ratio:.3f} — {r.sortino_grade}"
    )
    if r.sortino_ratio > r.sharpe_ratio * 1.3:
        insights.append(
            f"     Sortino >> Sharpe → most volatility is UPSIDE (beneficial)."
        )
    elif r.sortino_ratio < r.sharpe_ratio * 0.8:
        insights.append(
            f"     Sortino << Sharpe → concerning — volatility is skewed DOWNSIDE."
        )

    # 3. Jensen's Alpha
    if r.jensens_alpha_pct is not None:
        icon = grade_icons.get(r.alpha_grade, "")
        insights.append(
            f"{icon}  Jensen's Alpha = {r.jensens_alpha_pct:+.2f}% — {r.alpha_grade}"
        )
        if r.alpha_grade == "EXCELLENT":
            insights.append(
                f"     The fund delivered {r.jensens_alpha_pct:.2f}% MORE than "
                f"what its risk level (β={r.beta:.2f}) would predict. "
                f"This is genuine fund manager SKILL."
            )
        elif r.alpha_grade == "NEGATIVE":
            insights.append(
                f"     The fund returned LESS than what a passive portfolio "
                f"with β={r.beta:.2f} would achieve. Active management is "
                f"DESTROYING value."
            )

    # 4. Treynor
    if r.treynor_ratio is not None:
        icon = grade_icons.get(r.treynor_grade, "")
        insights.append(
            f"{icon}  Treynor Ratio = {r.treynor_ratio:.4f} — {r.treynor_grade}"
        )
        insights.append(
            f"     Use this when evaluating the fund within a diversified portfolio "
            f"(where only market risk matters, not total risk)."
        )

    # 5. Information Ratio
    if r.information_ratio is not None:
        icon = grade_icons.get(r.information_grade, "")
        insights.append(
            f"{icon}  Information Ratio = {r.information_ratio:.3f} — {r.information_grade}"
        )
        if r.information_ratio > 0.5:
            insights.append(
                f"     Fund manager generates CONSISTENT alpha relative to "
                f"tracking error. This is the hallmark of skilled active management."
            )
        elif r.information_ratio < 0:
            insights.append(
                f"     Fund consistently UNDERPERFORMS its benchmark after "
                f"adjusting for tracking error. Switch to index fund."
            )

    insights.append("")

    # ════════════════════════════════════════
    # SHARPE vs SORTINO COMPARISON
    # ════════════════════════════════════════
    insights.append("─" * 55)
    insights.append("🔍  SHARPE vs SORTINO DEEP DIVE")
    insights.append("─" * 55)

    ratio_diff = r.sortino_ratio / max(r.sharpe_ratio, 0.001) if r.sharpe_ratio > 0 else 0

    if ratio_diff > 1.5:
        insights.append(
            f"✅  Sortino/Sharpe ratio = {ratio_diff:.2f} — STRONG upside skew."
        )
        insights.append(
            f"    The fund's volatility is predominantly on the upside."
        )
        insights.append(
            f"    Sharpe penalises this upside volatility unfairly."
        )
        insights.append(
            f"    Sortino correctly shows the fund is BETTER than Sharpe suggests."
        )
    elif ratio_diff > 1.1:
        insights.append(
            f"🔶  Sortino/Sharpe ratio = {ratio_diff:.2f} — mild upside skew."
        )
        insights.append(
            f"    Both ratios paint a similar picture."
        )
    else:
        insights.append(
            f"⚠️   Sortino/Sharpe ratio = {ratio_diff:.2f} — minimal or negative skew."
        )
        insights.append(
            f"    Downside volatility is significant relative to total volatility."
        )
        insights.append(
            f"    This fund's losses are proportional to its gains — no free lunch."
        )

    insights.append("")

    # ════════════════════════════════════════
    # OVERALL VERDICT
    # ════════════════════════════════════════
    insights.append("─" * 55)
    insights.append("📋  OVERALL RISK-ADJUSTED VERDICT")
    insights.append("─" * 55)

    # Score based on grades
    grade_scores = {
        "EXCELLENT": 5, "EXCEPTIONAL": 5, "VERY GOOD": 4,
        "GOOD": 3, "ACCEPTABLE": 2, "AVERAGE": 2,
        "MARGINAL": 1, "POOR": 0, "NEGATIVE": 0,
    }

    scores = [grade_scores.get(r.sharpe_grade, 0), grade_scores.get(r.sortino_grade, 0)]
    if r.alpha_grade:
        scores.append(grade_scores.get(r.alpha_grade, 0))
    if r.information_grade:
        scores.append(grade_scores.get(r.information_grade, 0))

    avg_score = sum(scores) / len(scores)

    if avg_score >= 4:
        insights.append("🏆  EXCEPTIONAL risk-adjusted performance.")
        insights.append("    This fund delivers strong returns while managing risk effectively.")
        insights.append("    Active management fees are WELL JUSTIFIED.")
    elif avg_score >= 3:
        insights.append("✅  GOOD risk-adjusted performance.")
        insights.append("    Fund delivers reasonable returns for the risk taken.")
    elif avg_score >= 2:
        insights.append("🔶  AVERAGE risk-adjusted performance.")
        insights.append("    Returns are acceptable but not compelling given the risk.")
        insights.append("    Consider whether a lower-cost index fund might be better.")
    elif avg_score >= 1:
        insights.append("⚠️   BELOW AVERAGE risk-adjusted performance.")
        insights.append("    The fund takes considerable risk without commensurate returns.")
        insights.append("    Strongly recommend evaluating alternatives.")
    else:
        insights.append("❌  POOR risk-adjusted performance.")
        insights.append("    Active management is destroying value.")
        insights.append("    Switch to a low-cost index fund immediately.")

    # ════════════════════════════════════════
    # MULTI-PERIOD STABILITY (if available)
    # ════════════════════════════════════════
    if multi_period and len(multi_period) >= 2:
        insights.append("")
        insights.append("─" * 55)
        insights.append("📊  RATIO STABILITY ACROSS TIME PERIODS")
        insights.append("─" * 55)

        sharpe_values = [(p, r.sharpe_ratio) for p, r, _, _ in multi_period]
        if len(sharpe_values) >= 2:
            min_s = min(s for _, s in sharpe_values)
            max_s = max(s for _, s in sharpe_values)

            if max_s - min_s < 0.2:
                insights.append(
                    f"✅  Sharpe Ratio is STABLE across periods "
                    f"(range: {min_s:.3f} to {max_s:.3f}). "
                    f"Performance is consistent, not a fluke."
                )
            elif max_s - min_s < 0.5:
                insights.append(
                    f"🔶  Sharpe Ratio shows moderate variation "
                    f"(range: {min_s:.3f} to {max_s:.3f}). "
                    f"Some period-dependency in risk-adjusted returns."
                )
            else:
                insights.append(
                    f"⚠️   Sharpe Ratio varies significantly "
                    f"(range: {min_s:.3f} to {max_s:.3f}). "
                    f"Risk-adjusted performance is inconsistent."
                )

    insights.append("")

    return insights


# ────────────────────────────────────────────────
# PUBLIC: Full report (one-call convenience)
# ────────────────────────────────────────────────

def generate_risk_adjusted_report(
    fund_nav: NAVData,
    benchmark_nav: Optional[NAVData] = None,
    period_years: float = 3,
) -> RiskAdjustedReport:
    """
    End-to-end risk-adjusted analysis:
      1. Volatility metrics (σ, downside σ)
      2. Beta analysis (β, R², tracking error)
      3. All seven risk-adjusted ratios
      4. Multi-period stability check
      5. Automated interpretation

    Parameters
    ----------
    fund_nav      : NAVData for the fund
    benchmark_nav : NAVData for benchmark (optional)
    period_years  : primary analysis window (default 3 years)

    Returns
    -------
    RiskAdjustedReport
    """
    # ── 1. Volatility ──
    vol = calculate_volatility(fund_nav, period_years, mar=RISK_FREE_RATE)

    # ── 2. Beta ──
    beta_analysis = None
    if benchmark_nav is not None:
        try:
            beta_analysis = calculate_beta(fund_nav, benchmark_nav, period_years)
        except ValueError:
            pass

    # ── 3. Ratios ──
    ratios = calculate_risk_adjusted_ratios(fund_nav, benchmark_nav, period_years)

    # ── 4. Multi-period ──
    multi = None
    try:
        multi = calculate_multi_period_ratios(fund_nav, benchmark_nav)
    except ValueError:
        pass

    # ── Period description ──
    fund_m = _monthly_returns(fund_nav, period_years)
    if len(fund_m) > 0:
        start = fund_m.index[0].strftime("%b %Y")
        end = fund_m.index[-1].strftime("%b %Y")
        period_desc = f"{ratios.period_years:.1f} Years ({start} — {end})"
    else:
        period_desc = f"{period_years} Years"

    # ── 5. Interpretation ──
    interpretation = _interpret_risk_adjusted(vol, beta_analysis, ratios, multi)

    return RiskAdjustedReport(
        scheme_info=fund_nav.scheme_info,
        benchmark_info=benchmark_nav.scheme_info if benchmark_nav else None,
        as_of_date=fund_nav.latest_date,
        period_description=period_desc,
        volatility=vol,
        beta_analysis=beta_analysis,
        ratios=ratios,
        interpretation=interpretation,
    )