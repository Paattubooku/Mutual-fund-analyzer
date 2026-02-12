"""
metrics/scoring_engine.py
─────────────────────────
SECTION 7 — Automated Scoring and Ranking Framework

The grand unification engine that:
    1. Collects all metrics from Sections 1-2
    2. Normalises them to 0-100 percentile scores
    3. Applies investment-goal-based weights
    4. Handles penalties and bonuses
    5. Produces composite scores with star ratings
    6. Ranks multiple funds within a category

Public API
----------
    score_fund(fund_metrics, profile, category_stats=None)
    rank_funds(fund_metrics_list, profile)
    get_investment_profile(name)
"""

from __future__ import annotations

import datetime as dt
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass

import numpy as np

from config import RISK_FREE_RATE
from data.models import (
    MetricScore,
    PenaltyBonus,
    InvestmentProfile,
    FundScore,
    RankingTable,
)


# ────────────────────────────────────────────────
# INVESTMENT PROFILES
# ────────────────────────────────────────────────

INVESTMENT_PROFILES: Dict[str, InvestmentProfile] = {
    "aggressive": InvestmentProfile(
        profile_name="Aggressive",
        performance_weight=0.40,
        risk_adjusted_weight=0.25,
        risk_management_weight=0.15,
        structural_weight=0.20,
        description="Maximise returns, high risk tolerance, 7+ year horizon",
    ),
    "growth": InvestmentProfile(
        profile_name="Growth",
        performance_weight=0.35,
        risk_adjusted_weight=0.25,
        risk_management_weight=0.20,
        structural_weight=0.20,
        description="Strong returns with moderate risk, 5-7 year horizon",
    ),
    "balanced": InvestmentProfile(
        profile_name="Balanced",
        performance_weight=0.25,
        risk_adjusted_weight=0.25,
        risk_management_weight=0.30,
        structural_weight=0.20,
        description="Balance of returns and safety, 3-5 year horizon",
    ),
    "conservative": InvestmentProfile(
        profile_name="Conservative",
        performance_weight=0.20,
        risk_adjusted_weight=0.25,
        risk_management_weight=0.30,
        structural_weight=0.25,
        description="Capital preservation priority, low risk, 3+ year horizon",
    ),
}


def get_investment_profile(name: str = "growth") -> InvestmentProfile:
    """Get an investment profile by name."""
    return INVESTMENT_PROFILES.get(name.lower(), INVESTMENT_PROFILES["growth"])


# ────────────────────────────────────────────────
# METRIC DEFINITIONS
# ────────────────────────────────────────────────

@dataclass
class MetricDefinition:
    """Defines how to extract, score, and weight a metric."""
    name: str
    key: str                              # key in fund_metrics dict
    direction: str                        # "higher_better" or "lower_better"
    category: str                         # "performance", "risk_adjusted", "risk_management", "structural"
    sub_weight: float                     # weight WITHIN the category (must sum to 1.0 per category)
    description: str


# All metrics we can compute from NAV data + basic metadata
METRIC_DEFINITIONS: List[MetricDefinition] = [
    # ── PERFORMANCE (sub-weights sum to 1.0) ──
    MetricDefinition("3Y CAGR", "cagr_3y", "higher_better", "performance", 0.12,
                     "3-year compound annual growth rate"),
    MetricDefinition("5Y CAGR", "cagr_5y", "higher_better", "performance", 0.15,
                     "5-year compound annual growth rate"),
    MetricDefinition("3Y Rolling Avg", "rolling_3y_mean", "higher_better", "performance", 0.12,
                     "Average of all 3-year rolling returns"),
    MetricDefinition("5Y Rolling Avg", "rolling_5y_mean", "higher_better", "performance", 0.12,
                     "Average of all 5-year rolling returns"),
    MetricDefinition("Rolling Win Rate", "rolling_win_rate", "higher_better", "performance", 0.20,
                     "% of rolling periods beating benchmark"),
    MetricDefinition("Calendar Consistency", "calendar_consistency", "higher_better", "performance", 0.14,
                     "% of calendar years beating benchmark"),
    MetricDefinition("5Y SIP XIRR", "sip_xirr_5y", "higher_better", "performance", 0.15,
                     "5-year SIP annualised return"),

    # ── RISK-ADJUSTED (sub-weights sum to 1.0) ──
    MetricDefinition("Sharpe Ratio", "sharpe_3y", "higher_better", "risk_adjusted", 0.22,
                     "Return per unit of total risk"),
    MetricDefinition("Sortino Ratio", "sortino_3y", "higher_better", "risk_adjusted", 0.22,
                     "Return per unit of downside risk"),
    MetricDefinition("Jensen's Alpha", "alpha_3y", "higher_better", "risk_adjusted", 0.22,
                     "Excess return beyond CAPM prediction"),
    MetricDefinition("Information Ratio", "info_ratio_3y", "higher_better", "risk_adjusted", 0.18,
                     "Consistency of benchmark outperformance"),
    MetricDefinition("Capture Ratio", "capture_ratio", "higher_better", "risk_adjusted", 0.16,
                     "Up-capture / Down-capture asymmetry"),

    # ── RISK MANAGEMENT (sub-weights sum to 1.0) ──
    MetricDefinition("Std Deviation", "std_dev_3y", "lower_better", "risk_management", 0.20,
                     "Annualised volatility — lower is less risky"),
    MetricDefinition("Max Drawdown", "max_drawdown", "lower_better", "risk_management", 0.25,
                     "Deepest peak-to-trough decline"),
    MetricDefinition("Downside Deviation", "downside_dev_3y", "lower_better", "risk_management", 0.15,
                     "Volatility of negative returns only"),
    MetricDefinition("Rolling Minimum", "rolling_3y_min", "higher_better", "risk_management", 0.20,
                     "Worst-case rolling return (higher = safer)"),
    MetricDefinition("Down Capture", "down_capture", "lower_better", "risk_management", 0.10,
                     "How much benchmark loss the fund captures"),
    MetricDefinition("Negative Month %", "pct_negative_months", "lower_better", "risk_management", 0.10,
                     "Percentage of months with negative returns"),

    # ── STRUCTURAL (sub-weights sum to 1.0) ──
    MetricDefinition("Expense Ratio", "expense_ratio", "lower_better", "structural", 0.50,
                     "Annual fee — lower preserves more wealth"),
    MetricDefinition("Fund Age", "fund_age_years", "higher_better", "structural", 0.30,
                     "Years since inception — longer = more reliable data"),
    MetricDefinition("AUM Appropriateness", "aum_score", "higher_better", "structural", 0.20,
                     "Whether AUM is appropriate for the strategy"),
]


# ────────────────────────────────────────────────
# METRIC EXTRACTION: Build metrics dict from reports
# ────────────────────────────────────────────────

def extract_metrics_from_reports(
    trailing_report=None,
    rolling_report=None,
    consistency_report=None,
    sip_report=None,
    risk_report=None,
    nav_data=None,
) -> Dict[str, Optional[float]]:
    """
    Extract all scoring metrics from the analysis reports
    produced by Sections 1-2.

    Returns a flat dict: metric_key → value
    """
    metrics: Dict[str, Optional[float]] = {}

    # ── From trailing returns ──
    if trailing_report:
        for comp in trailing_report.comparisons:
            if comp.period_label == "3 Years" and comp.fund_return:
                metrics["cagr_3y"] = comp.fund_return.primary_return_pct
            if comp.period_label == "5 Years" and comp.fund_return:
                metrics["cagr_5y"] = comp.fund_return.primary_return_pct

    # ── From rolling returns ──
    if rolling_report:
        for dist in rolling_report.distributions:
            if "3 Year" in dist.window_label:
                metrics["rolling_3y_mean"] = dist.mean_return_pct
                metrics["rolling_3y_min"] = dist.min_return_pct
                if dist.win_rate_vs_benchmark_pct is not None:
                    metrics["rolling_win_rate"] = dist.win_rate_vs_benchmark_pct
            if "5 Year" in dist.window_label:
                metrics["rolling_5y_mean"] = dist.mean_return_pct
                # Use 5Y win rate if available and 3Y isn't
                if "rolling_win_rate" not in metrics and dist.win_rate_vs_benchmark_pct is not None:
                    metrics["rolling_win_rate"] = dist.win_rate_vs_benchmark_pct

    # ── From consistency ──
    if consistency_report:
        if consistency_report.calendar_year_analysis:
            metrics["calendar_consistency"] = consistency_report.calendar_year_analysis.consistency_pct
        if consistency_report.capture_ratios:
            cr = consistency_report.capture_ratios
            metrics["capture_ratio"] = cr.capture_ratio
            metrics["down_capture"] = cr.down_capture_ratio

    # ── From SIP returns ──
    if sip_report:
        for result in sip_report.sip_results:
            if "5 Year" in result.period_label and result.xirr_pct is not None:
                metrics["sip_xirr_5y"] = result.xirr_pct
            # Fallback to 3Y if 5Y not available
            if "3 Year" in result.period_label and "sip_xirr_5y" not in metrics:
                if result.xirr_pct is not None:
                    metrics["sip_xirr_5y"] = result.xirr_pct

    # ── From risk-adjusted report ──
    if risk_report:
        r = risk_report.ratios
        metrics["sharpe_3y"] = r.sharpe_ratio
        metrics["sortino_3y"] = r.sortino_ratio
        metrics["alpha_3y"] = r.jensens_alpha_pct
        metrics["info_ratio_3y"] = r.information_ratio
        metrics["std_dev_3y"] = r.std_dev_pct

        v = risk_report.volatility
        metrics["downside_dev_3y"] = v.annualised_downside_dev_pct
        metrics["pct_negative_months"] = v.pct_negative_months

    # ── Max drawdown from NAV data ──
    if nav_data:
        metrics["max_drawdown"] = _calculate_max_drawdown(nav_data)
        metrics["fund_age_years"] = nav_data.history_years

    # ── Expense ratio (from scheme info) ──
    # Will be set externally if available

    # ── AUM score (default to neutral if not available) ──
    if "aum_score" not in metrics:
        metrics["aum_score"] = 50.0

    return metrics


def _calculate_max_drawdown(nav_data) -> float:
    """Calculate maximum drawdown from NAV series."""
    navs = nav_data.nav_series.values.astype(np.float64)
    running_max = np.maximum.accumulate(navs)
    drawdowns = (navs - running_max) / running_max * 100.0
    return round(float(np.min(drawdowns)), 2)


# ────────────────────────────────────────────────
# NORMALISATION: Percentile scoring
# ────────────────────────────────────────────────

def _normalise_single_value(
    value: float,
    all_values: List[float],
    direction: str,
) -> float:
    """
    Convert a raw metric value to a 0-100 percentile score
    within the comparison set.

    Parameters
    ----------
    value      : the fund's metric value
    all_values : list of all funds' values for this metric
    direction  : "higher_better" or "lower_better"

    Returns
    -------
    float : 0-100 percentile score
    """
    if len(all_values) <= 1:
        return 50.0

    arr = np.array(all_values, dtype=float)
    arr = arr[~np.isnan(arr)]

    if len(arr) <= 1:
        return 50.0

    # Percentile rank
    count_below = np.sum(arr < value)
    count_equal = np.sum(arr == value)
    n = len(arr)

    # Average rank method for ties
    percentile = (count_below + 0.5 * count_equal) / n * 100

    if direction == "lower_better":
        percentile = 100 - percentile

    return round(max(0, min(100, percentile)), 2)


def _normalise_without_peers(value: float, metric_def: MetricDefinition) -> float:
    """
    Normalise a single metric when no peer comparison is available.
    Uses absolute thresholds based on the metric type.
    """
    key = metric_def.key
    direction = metric_def.direction

    # Absolute scale mappings (metric_key → (worst, best))
    absolute_scales = {
        "cagr_3y":               (-5, 25),
        "cagr_5y":               (-3, 22),
        "rolling_3y_mean":       (0, 25),
        "rolling_5y_mean":       (2, 22),
        "rolling_win_rate":      (30, 90),
        "calendar_consistency":  (30, 90),
        "sip_xirr_5y":           (0, 25),
        "sharpe_3y":             (-0.5, 1.5),
        "sortino_3y":            (-0.5, 2.5),
        "alpha_3y":              (-5, 8),
        "info_ratio_3y":         (-0.5, 1.0),
        "capture_ratio":         (0.7, 1.5),
        "std_dev_3y":            (8, 30),      # lower better
        "max_drawdown":          (-50, -5),     # lower better (less negative)
        "downside_dev_3y":       (4, 20),       # lower better
        "rolling_3y_min":        (-15, 10),
        "down_capture":          (60, 120),     # lower better
        "pct_negative_months":   (20, 55),      # lower better
        "expense_ratio":         (0.1, 2.0),    # lower better
        "fund_age_years":        (1, 15),
        "aum_score":             (0, 100),
    }

    scale = absolute_scales.get(key, (0, 100))
    worst, best = scale

    if direction == "lower_better":
        # For lower_better, worst is the high end, best is the low end
        score = (worst - value) / (worst - best) * 100 if worst != best else 50
    else:
        score = (value - worst) / (best - worst) * 100 if best != worst else 50

    return round(max(0, min(100, score)), 2)


# ────────────────────────────────────────────────
# PENALTIES AND BONUSES
# ────────────────────────────────────────────────

def _evaluate_penalties_bonuses(
    metrics: Dict[str, Optional[float]],
    fund_age: float,
) -> Tuple[List[PenaltyBonus], List[PenaltyBonus]]:
    """
    Evaluate all penalty and bonus conditions.
    """
    penalties: List[PenaltyBonus] = []
    bonuses: List[PenaltyBonus] = []

    # ── PENALTIES ──

    # P1: Fund age < 3 years but >= filter threshold
    penalties.append(PenaltyBonus(
        label="Young Fund",
        points=-10,
        reason="Fund has less than 3 years of history — limited data reliability",
        triggered=fund_age < 3,
    ))

    # P2: Negative alpha over 3 years
    alpha = metrics.get("alpha_3y")
    penalties.append(PenaltyBonus(
        label="Negative Alpha",
        points=-10,
        reason=f"3Y Jensen's Alpha is negative ({alpha:+.2f}%) — not justifying active management" if alpha is not None else "",
        triggered=alpha is not None and alpha < 0,
    ))

    # P3: Rolling win rate below 50%
    wr = metrics.get("rolling_win_rate")
    penalties.append(PenaltyBonus(
        label="Low Win Rate",
        points=-8,
        reason=f"Rolling win rate ({wr:.1f}%) below 50% — fund loses to benchmark majority of time" if wr is not None else "",
        triggered=wr is not None and wr < 50,
    ))

    # P4: High expense ratio
    ter = metrics.get("expense_ratio")
    penalties.append(PenaltyBonus(
        label="High Expense Ratio",
        points=-5,
        reason=f"TER ({ter:.2f}%) is above 1.0% — significant cost drag" if ter is not None else "",
        triggered=ter is not None and ter > 1.0,
    ))

    # P5: Extreme drawdown
    dd = metrics.get("max_drawdown")
    penalties.append(PenaltyBonus(
        label="Extreme Drawdown",
        points=-8,
        reason=f"Maximum drawdown ({dd:.1f}%) exceeds -40% — severe capital destruction risk" if dd is not None else "",
        triggered=dd is not None and dd < -40,
    ))

    # P6: Low Sharpe
    sharpe = metrics.get("sharpe_3y")
    penalties.append(PenaltyBonus(
        label="Poor Risk-Adjusted Return",
        points=-5,
        reason=f"Sharpe Ratio ({sharpe:.3f}) is negative — fund returned less than risk-free rate" if sharpe is not None else "",
        triggered=sharpe is not None and sharpe < 0,
    ))

    # ── BONUSES ──

    # B1: Exceptional rolling win rate
    bonuses.append(PenaltyBonus(
        label="Elite Win Rate",
        points=+8,
        reason=f"Rolling win rate ({wr:.1f}%) exceeds 80% — elite consistency" if wr is not None else "",
        triggered=wr is not None and wr > 80,
    ))

    # B2: Long fund age with consistent performance
    bonuses.append(PenaltyBonus(
        label="Proven Track Record",
        points=+5,
        reason=f"Fund has {fund_age:.1f} years of history with positive alpha — battle-tested",
        triggered=fund_age >= 10 and alpha is not None and alpha > 0,
    ))

    # B3: Excellent Sharpe
    bonuses.append(PenaltyBonus(
        label="Excellent Risk-Adjusted Returns",
        points=+5,
        reason=f"Sharpe Ratio ({sharpe:.3f}) exceeds 1.0 — excellent return per unit risk" if sharpe is not None else "",
        triggered=sharpe is not None and sharpe > 1.0,
    ))

    # B4: Low expense ratio
    bonuses.append(PenaltyBonus(
        label="Low Cost",
        points=+5,
        reason=f"TER ({ter:.2f}%) below 0.5% — minimal wealth destruction" if ter is not None else "",
        triggered=ter is not None and ter < 0.5,
    ))

    # B5: Never lost money over 3Y rolling
    rolling_min = metrics.get("rolling_3y_min")
    bonuses.append(PenaltyBonus(
        label="Capital Protection",
        points=+7,
        reason=f"Minimum 3Y rolling return ({rolling_min:+.2f}%) is positive — fund has NEVER lost money over any 3-year period" if rolling_min is not None else "",
        triggered=rolling_min is not None and rolling_min > 0,
    ))

    # B6: Ideal capture profile
    cr = metrics.get("capture_ratio")
    bonuses.append(PenaltyBonus(
        label="Ideal Asymmetry",
        points=+5,
        reason=f"Capture Ratio ({cr:.2f}) exceeds 1.2 — fund gains more in rallies and/or loses less in crashes" if cr is not None else "",
        triggered=cr is not None and cr > 1.2,
    ))

    return penalties, bonuses


# ────────────────────────────────────────────────
# HARD FILTERS (Disqualification)
# ────────────────────────────────────────────────

def _check_hard_filters(
    metrics: Dict[str, Optional[float]],
    fund_age: float,
) -> Tuple[bool, List[str]]:
    """
    Check if the fund should be disqualified entirely.

    Returns (disqualified, reasons)
    """
    reasons = []

    # F1: Fund age < 1 year
    if fund_age < 1:
        reasons.append(f"Fund is less than 1 year old ({fund_age:.1f}y) — insufficient data")

    return len(reasons) > 0, reasons


# ────────────────────────────────────────────────
# STAR RATING
# ────────────────────────────────────────────────

def _compute_star_rating(score: float) -> Tuple[int, str, str]:
    """
    Convert composite score to star rating.

    Returns (stars, label, recommendation)
    """
    if score >= 85:
        return 5, "EXCEPTIONAL", "Strong buy — top-tier fund across all dimensions"
    elif score >= 72:
        return 4, "VERY GOOD", "Recommended — consistent quality fund"
    elif score >= 58:
        return 3, "GOOD", "Acceptable — decent fund, monitor for improvement"
    elif score >= 42:
        return 2, "AVERAGE", "Below expectations — consider alternatives"
    else:
        return 1, "POOR", "Avoid — switch to index fund or better active fund"


# ────────────────────────────────────────────────
# PUBLIC: Score a single fund
# ────────────────────────────────────────────────

def score_fund(
    fund_metrics: Dict[str, Optional[float]],
    profile: InvestmentProfile,
    scheme_code: int = 0,
    scheme_name: str = "Unknown",
    scheme_category: str = "Equity",
    peer_metrics: Optional[List[Dict[str, Optional[float]]]] = None,
) -> FundScore:
    """
    Score a single fund based on its metrics and the investment profile.

    Parameters
    ----------
    fund_metrics  : dict of metric_key → value
    profile       : InvestmentProfile (Aggressive, Growth, etc.)
    scheme_code   : fund identifier
    scheme_name   : fund name
    scheme_category: SEBI category
    peer_metrics  : list of metric dicts for peer funds
                    (used for percentile normalisation)
                    If None, absolute scales are used

    Returns
    -------
    FundScore
    """
    fund_age = fund_metrics.get("fund_age_years", 0) or 0

    # ── Hard filters ──
    disqualified, disq_reasons = _check_hard_filters(fund_metrics, fund_age)

    # ── Compute metric scores ──
    metric_scores: List[MetricScore] = []
    category_scores: Dict[str, List[Tuple[float, float]]] = {
        "performance": [],
        "risk_adjusted": [],
        "risk_management": [],
        "structural": [],
    }

    for mdef in METRIC_DEFINITIONS:
        raw_value = fund_metrics.get(mdef.key)

        if raw_value is None:
            continue

        # Normalise
        if peer_metrics and len(peer_metrics) >= 3:
            peer_values = [
                pm.get(mdef.key) for pm in peer_metrics
                if pm.get(mdef.key) is not None
            ]
            if len(peer_values) >= 2:
                percentile = _normalise_single_value(raw_value, peer_values, mdef.direction)
            else:
                percentile = _normalise_without_peers(raw_value, mdef)
        else:
            percentile = _normalise_without_peers(raw_value, mdef)

        # Weighted contribution within category
        weighted = percentile * mdef.sub_weight

        metric_scores.append(MetricScore(
            metric_name=mdef.name,
            raw_value=round(raw_value, 4) if raw_value is not None else None,
            percentile_score=percentile,
            weight=mdef.sub_weight,
            weighted_contribution=round(weighted, 2),
            direction=mdef.direction,
            category_label=mdef.category.replace("_", " ").title(),
        ))

        category_scores[mdef.category].append((percentile, mdef.sub_weight))

    # ── Category sub-scores ──
    def _weighted_avg(items: List[Tuple[float, float]]) -> float:
        if not items:
            return 50.0
        total_w = sum(w for _, w in items)
        if total_w == 0:
            return 50.0
        return sum(s * w for s, w in items) / total_w

    perf_score = _weighted_avg(category_scores["performance"])
    risk_adj_score = _weighted_avg(category_scores["risk_adjusted"])
    risk_mgmt_score = _weighted_avg(category_scores["risk_management"])
    structural_score_val = _weighted_avg(category_scores["structural"])

    # ── Raw composite (profile-weighted) ──
    raw_composite = (
        perf_score * profile.performance_weight +
        risk_adj_score * profile.risk_adjusted_weight +
        risk_mgmt_score * profile.risk_management_weight +
        structural_score_val * profile.structural_weight
    )

    # ── Penalties and bonuses ──
    penalties, bonuses = _evaluate_penalties_bonuses(fund_metrics, fund_age)

    total_penalty = sum(p.points for p in penalties if p.triggered)
    total_bonus = sum(b.points for b in bonuses if b.triggered)

    # ── Final score ──
    final_score = raw_composite + total_penalty + total_bonus
    final_score = max(0, min(100, final_score))

    # ── Star rating ──
    if disqualified:
        stars, label, recommendation = 0, "DISQUALIFIED", "Fund does not meet minimum criteria"
    else:
        stars, label, recommendation = _compute_star_rating(final_score)

    return FundScore(
        scheme_code=scheme_code,
        scheme_name=scheme_name,
        scheme_category=scheme_category,
        fund_age_years=round(fund_age, 1),
        profile=profile,
        metric_scores=metric_scores,
        performance_score=round(perf_score, 2),
        risk_adjusted_score=round(risk_adj_score, 2),
        risk_management_score=round(risk_mgmt_score, 2),
        structural_score=round(structural_score_val, 2),
        penalties=[p for p in penalties if p.triggered],
        bonuses=[b for b in bonuses if b.triggered],
        total_penalty=total_penalty,
        total_bonus=total_bonus,
        raw_composite=round(raw_composite, 2),
        final_score=round(final_score, 2),
        star_rating=stars,
        rating_label=label,
        recommendation=recommendation,
        disqualified=disqualified,
        disqualification_reasons=disq_reasons,
    )


# ────────────────────────────────────────────────
# PUBLIC: Rank multiple funds
# ────────────────────────────────────────────────

def rank_funds(
    fund_entries: List[Dict],
    profile: InvestmentProfile,
    category: str = "Equity",
) -> RankingTable:
    """
    Score and rank multiple funds with peer-relative normalisation.

    Parameters
    ----------
    fund_entries : list of dicts, each with:
        {
            "scheme_code": int,
            "scheme_name": str,
            "scheme_category": str,
            "metrics": Dict[str, Optional[float]],
        }
    profile  : InvestmentProfile
    category : display category name

    Returns
    -------
    RankingTable
    """
    # Collect all metrics for peer normalisation
    all_metrics = [entry["metrics"] for entry in fund_entries]

    # Score each fund
    scores: List[FundScore] = []
    for entry in fund_entries:
        fs = score_fund(
            fund_metrics=entry["metrics"],
            profile=profile,
            scheme_code=entry.get("scheme_code", 0),
            scheme_name=entry.get("scheme_name", "Unknown"),
            scheme_category=entry.get("scheme_category", category),
            peer_metrics=all_metrics,
        )
        scores.append(fs)

    # Sort by final score descending
    scores.sort(key=lambda s: s.final_score, reverse=True)

    # Top picks (exclude disqualified)
    qualified = [s for s in scores if not s.disqualified]
    top_picks = qualified[:min(3, len(qualified))]

    # Interpretation
    interpretation = _interpret_ranking(scores, top_picks, profile)

    return RankingTable(
        profile=profile,
        category=category,
        as_of_date=dt.date.today(),
        fund_scores=scores,
        top_picks=top_picks,
        interpretation=interpretation,
    )


def _interpret_ranking(
    scores: List[FundScore],
    top_picks: List[FundScore],
    profile: InvestmentProfile,
) -> List[str]:
    """Generate ranking interpretation."""
    insights: List[str] = []

    insights.append(f"Profile: {profile.profile_name} — {profile.description}")
    insights.append(f"Funds analysed: {len(scores)}")
    insights.append("")

    if top_picks:
        insights.append("🏆  TOP PICKS:")
        for i, pick in enumerate(top_picks, 1):
            stars = "★" * pick.star_rating + "☆" * (5 - pick.star_rating)
            insights.append(
                f"    {i}. {pick.scheme_name}"
            )
            insights.append(
                f"       {stars}  Score: {pick.final_score:.1f}/100  —  {pick.rating_label}"
            )
            insights.append(f"       {pick.recommendation}")

            # Key strengths
            strong_metrics = sorted(
                [m for m in pick.metric_scores if m.percentile_score >= 70],
                key=lambda m: m.percentile_score,
                reverse=True,
            )[:3]
            if strong_metrics:
                strengths = ", ".join(f"{m.metric_name} (P{m.percentile_score:.0f})" for m in strong_metrics)
                insights.append(f"       Key strengths: {strengths}")

            insights.append("")

    # Disqualified funds
    disq = [s for s in scores if s.disqualified]
    if disq:
        insights.append("❌  DISQUALIFIED FUNDS:")
        for s in disq:
            insights.append(f"    • {s.scheme_name}: {', '.join(s.disqualification_reasons)}")
        insights.append("")

    return insights