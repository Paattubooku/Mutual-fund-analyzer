"""
metrics/structural_analysis.py
──────────────────────────────
SECTION 4 — Structural and Qualitative Indicators

Analyses non-performance factors that silently impact wealth:
    4.1  Expense Ratio (TER) — the primary return drag
    4.2  Portfolio Turnover — hidden trading costs
    4.3  Fund Manager Tenure — stability and track record
    4.4  AUM Analysis — size-strategy compatibility
    4.5  Exit Load Structure
    4.6  Fund House Pedigree

Public API
----------
    analyse_expense_ratio(metadata, category_benchmark)
    analyse_turnover(metadata, category_benchmark)
    analyse_fund_manager(metadata)
    analyse_aum(metadata, category_benchmark)
    generate_structural_report(metadata)
"""

from __future__ import annotations

import datetime as dt
from typing import Optional, List, Dict, Tuple

import numpy as np

from data.models import (
    ExpenseRatioAnalysis,
    TurnoverAnalysis,
    FundManagerInfo,
    FundManagerAnalysis,
    AUMAnalysis,
    ExitLoadInfo,
    FundHouseInfo,
    StructuralReport,
)
from data.fund_metadata_provider import get_category_benchmark


# ────────────────────────────────────────────────
# 4.1: EXPENSE RATIO ANALYSIS
# ────────────────────────────────────────────────

def analyse_expense_ratio(
    metadata: Dict,
    category_benchmark: Optional[Dict] = None,
) -> ExpenseRatioAnalysis:
    """
    Analyse expense ratio with long-term compounding cost impact.

    The compounding COST of TER over time:
        Investment: ₹10,00,000 | Gross Return: 14% | Period: 20 years
        A 2% TER fund DESTROYS ₹56.4 LAKHS vs zero-cost.

    Parameters
    ----------
    metadata           : dict with expense_ratio_direct, expense_ratio_regular
    category_benchmark : dict with avg_ter_direct, avg_ter_regular

    Returns
    -------
    ExpenseRatioAnalysis
    """
    ter_direct = metadata.get("expense_ratio_direct")
    ter_regular = metadata.get("expense_ratio_regular")

    cat_direct = category_benchmark.get("avg_ter_direct") if category_benchmark else None
    cat_regular = category_benchmark.get("avg_ter_regular") if category_benchmark else None

    # Cost vs category
    cheaper = None
    cost_diff = None
    if ter_direct is not None and cat_direct is not None:
        cost_diff = round(ter_direct - cat_direct, 3)
        cheaper = cost_diff < 0

    # ── Long-term cost simulation ──
    investment = 10_00_000                  # ₹10 lakhs
    gross_return = 0.14                     # 14% assumed gross return
    ter_values = {}

    if ter_direct is not None:
        ter_values["Direct Plan"] = ter_direct / 100.0
    if ter_regular is not None:
        ter_values["Regular Plan"] = ter_regular / 100.0
    # Add index fund reference
    ter_values["Index Fund (0.15%)"] = 0.0015
    ter_values["Zero Cost (Gross)"] = 0.0

    simulations = {}
    for horizon in [5, 10, 15, 20, 25]:
        sim = {}
        for label, ter in ter_values.items():
            net_return = gross_return - ter
            final = investment * ((1 + net_return) ** horizon)
            cost_drag = investment * ((1 + gross_return) ** horizon) - final
            sim[label] = {
                "final_value": round(final, 0),
                "cost_drag": round(cost_drag, 0),
                "net_return_pct": round(net_return * 100, 2),
            }
        simulations[f"{horizon}Y"] = sim

    # ── Alpha break-even ──
    alpha_breakeven = None
    index_ter = 0.15 / 100.0
    if ter_direct is not None:
        alpha_breakeven = round((ter_direct / 100.0 - index_ter) * 100, 2)

    # ── Grading ──
    grade = _grade_expense_ratio(ter_direct)

    return ExpenseRatioAnalysis(
        current_direct_pct=ter_direct,
        current_regular_pct=ter_regular,
        category_avg_direct_pct=cat_direct,
        category_avg_regular_pct=cat_regular,
        cheaper_than_category=cheaper,
        cost_difference_pct=cost_diff,
        cost_simulations=simulations,
        expense_grade=grade,
        alpha_breakeven_pct=alpha_breakeven,
    )


def _grade_expense_ratio(ter_direct: Optional[float]) -> str:
    if ter_direct is None:
        return "UNKNOWN"
    if ter_direct < 0.5:
        return "EXCELLENT"
    elif ter_direct < 0.8:
        return "GOOD"
    elif ter_direct < 1.2:
        return "AVERAGE"
    else:
        return "EXPENSIVE"


# ────────────────────────────────────────────────
# 4.2: PORTFOLIO TURNOVER ANALYSIS
# ────────────────────────────────────────────────

def analyse_turnover(
    metadata: Dict,
    category_benchmark: Optional[Dict] = None,
) -> TurnoverAnalysis:
    """
    Analyse portfolio turnover with hidden cost estimation.

    Hidden costs per trade:
      1. Brokerage: 0.01-0.05%
      2. Impact cost: 0.05-0.50% for large orders
      3. STT: 0.1% on sell side
      4. SEBI charges, stamp duty, GST

    A fund with 200% turnover replaces its ENTIRE portfolio
    twice a year — hidden costs can add 0.5-1.5% annual drag
    BEYOND the stated TER.

    Parameters
    ----------
    metadata           : dict with turnover_ratio
    category_benchmark : dict with avg_turnover

    Returns
    -------
    TurnoverAnalysis
    """
    turnover = metadata.get("turnover_ratio")
    ter_direct = metadata.get("expense_ratio_direct", 0)
    cat_turnover = category_benchmark.get("avg_turnover") if category_benchmark else None

    if turnover is None:
        turnover = 0.0

    # ── Hidden cost estimation ──
    # Average brokerage per trade (buy + sell)
    brokerage = turnover / 100 * 0.03          # ~0.03% per side average
    # Impact cost (higher for larger funds / less liquid stocks)
    impact = turnover / 100 * 0.15             # ~0.15% average impact
    # STT (0.1% on sell, so turnover/2 is sell volume)
    stt = (turnover / 100 / 2) * 0.10          # STT on sell side

    total_hidden = round(brokerage + impact + stt, 3)
    effective_total = round((ter_direct or 0) + total_hidden, 3)

    # ── Grading ──
    if turnover < 25:
        grade = "Buy & Hold"
    elif turnover < 50:
        grade = "Low Turnover"
    elif turnover < 100:
        grade = "Moderate"
    elif turnover < 200:
        grade = "High"
    else:
        grade = "Very High"

    return TurnoverAnalysis(
        turnover_ratio_pct=turnover,
        category_avg_turnover_pct=cat_turnover,
        turnover_grade=grade,
        estimated_brokerage_drag_pct=round(brokerage * 100, 3),
        estimated_impact_cost_drag_pct=round(impact * 100, 3),
        estimated_stt_drag_pct=round(stt * 100, 3),
        total_hidden_cost_pct=round(total_hidden * 100, 3),
        effective_total_cost_pct=round(effective_total * 100, 3),
    )


# ────────────────────────────────────────────────
# 4.3: FUND MANAGER ANALYSIS
# ────────────────────────────────────────────────

def analyse_fund_manager(metadata: Dict) -> FundManagerAnalysis:
    """
    Analyse fund manager tenure, stability, and track record.

    Key rules:
      - Minimum desirable tenure: 3 years
      - Preferred: 5+ years
      - Frequent changes (< 2 years each): INSTABILITY flag
      - Manager handling > 7 funds: STRETCHED flag

    Parameters
    ----------
    metadata : dict with managers, manager_history

    Returns
    -------
    FundManagerAnalysis
    """
    today = dt.date.today()

    # ── Parse current managers ──
    managers_raw = metadata.get("managers", [])
    current_managers: List[FundManagerInfo] = []

    for m in managers_raw:
        start_str = m.get("start_date")
        start_date = None
        tenure = None
        if start_str:
            try:
                start_date = dt.datetime.strptime(start_str, "%Y-%m-%d").date()
                tenure = round((today - start_date).days / 365.25, 1)
            except (ValueError, TypeError):
                pass

        current_managers.append(FundManagerInfo(
            name=m.get("name", "Unknown"),
            designation=m.get("designation"),
            tenure_start_date=start_date,
            tenure_years=tenure,
            total_experience_years=m.get("experience_years"),
            num_funds_managed=m.get("num_funds"),
            qualification=m.get("qualification"),
        ))

    # ── Manager history ──
    history = metadata.get("manager_history", [])
    total_changes = max(0, len(history) - 1)       # first appointment isn't a "change"

    # ── Average tenure ──
    tenures = []
    for h in history:
        t = h.get("tenure_years")
        if t is not None:
            tenures.append(t)

    avg_tenure = round(float(np.mean(tenures)), 1) if tenures else None

    # ── Current tenure (max among co-managers) ──
    current_tenures = [m.tenure_years for m in current_managers if m.tenure_years is not None]
    current_tenure = max(current_tenures) if current_tenures else None

    # ── Stability grade ──
    if total_changes == 0:
        stability = "VERY STABLE"
    elif total_changes <= 2 and (avg_tenure or 0) >= 4:
        stability = "STABLE"
    elif total_changes <= 3 and (avg_tenure or 0) >= 2:
        stability = "MODERATE"
    else:
        stability = "UNSTABLE"

    # ── Tenure grade ──
    if current_tenure is not None:
        if current_tenure >= 7:
            tenure_grade = "EXCELLENT"
        elif current_tenure >= 3:
            tenure_grade = "GOOD"
        elif current_tenure >= 1:
            tenure_grade = "CONCERN"
        else:
            tenure_grade = "HIGH RISK"
    else:
        tenure_grade = "UNKNOWN"

    return FundManagerAnalysis(
        current_managers=current_managers,
        manager_history=history,
        total_manager_changes=total_changes,
        avg_manager_tenure_years=avg_tenure,
        current_tenure_years=current_tenure,
        stability_grade=stability,
        tenure_grade=tenure_grade,
    )


# ────────────────────────────────────────────────
# 4.4: AUM ANALYSIS
# ────────────────────────────────────────────────

def analyse_aum(
    metadata: Dict,
    category_benchmark: Optional[Dict] = None,
) -> AUMAnalysis:
    """
    Analyse AUM with size-strategy compatibility.

    AUM Sizing Rules:
        Small Cap Fund with ₹20,000 Cr AUM → SERIOUS CONCERN
        Mid Cap Fund with ₹30,000 Cr AUM   → CAUTION
        Large Cap Fund with ₹50,000 Cr AUM  → Generally OK

    Parameters
    ----------
    metadata           : dict with aum_cr, aum_history, category
    category_benchmark : dict with ideal_aum_min, ideal_aum_max, concern_aum

    Returns
    -------
    AUMAnalysis
    """
    current_aum = metadata.get("aum_cr")
    aum_history = metadata.get("aum_history", [])
    category = metadata.get("category", "")

    # ── AUM trend ──
    trend = "Unknown"
    growth_1y = None

    if len(aum_history) >= 2:
        latest = aum_history[0].get("aum_cr", 0)
        # Find 1-year ago
        one_year_ago = None
        for entry in aum_history:
            date_str = entry.get("date", "")
            try:
                entry_date = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
                if (dt.date.today() - entry_date).days >= 300:
                    one_year_ago = entry.get("aum_cr")
                    break
            except (ValueError, TypeError):
                continue

        if one_year_ago and one_year_ago > 0:
            growth_1y = round((latest / one_year_ago - 1) * 100, 1)

            if growth_1y > 80:
                trend = "Spiking"
            elif growth_1y > 20:
                trend = "Growing"
            elif growth_1y > -10:
                trend = "Stable"
            else:
                trend = "Declining"

    # ── Size-strategy compatibility ──
    ideal_min = 2000
    ideal_max = 30000
    concern_level = 50000

    if category_benchmark:
        ideal_min = category_benchmark.get("ideal_aum_min", ideal_min)
        ideal_max = category_benchmark.get("ideal_aum_max", ideal_max)
        concern_level = category_benchmark.get("concern_aum", concern_level)

    size_appropriate = True
    size_grade = "OPTIMAL"
    size_concern = None

    if current_aum is not None:
        if current_aum < ideal_min:
            size_appropriate = False
            size_grade = "CONCERN"
            size_concern = f"AUM ₹{current_aum:,.0f} Cr is below minimum ideal ₹{ideal_min:,.0f} Cr — potential liquidity risk."
        elif current_aum <= ideal_max:
            size_appropriate = True
            size_grade = "OPTIMAL"
        elif current_aum <= concern_level:
            size_appropriate = True
            size_grade = "ACCEPTABLE"
            size_concern = f"AUM ₹{current_aum:,.0f} Cr is above ideal range (₹{ideal_max:,.0f} Cr) — monitor for performance drag."
        else:
            size_appropriate = False
            size_grade = "CRITICAL"
            cat_key = _extract_category_key(category)
            size_concern = f"AUM ₹{current_aum:,.0f} Cr significantly exceeds ideal for {cat_key} strategy — deployment challenges likely."

    return AUMAnalysis(
        current_aum_cr=current_aum,
        aum_history=aum_history,
        aum_trend=trend,
        aum_growth_1y_pct=growth_1y,
        category=category,
        ideal_aum_range_cr=(ideal_min, ideal_max),
        size_appropriate=size_appropriate,
        size_grade=size_grade,
        size_concern=size_concern,
    )


def _extract_category_key(category: str) -> str:
    """Extract readable category from full SEBI category string."""
    cat_lower = category.lower()
    for key in ["small cap", "mid cap", "large cap", "flexi cap", "multi cap",
                 "elss", "value", "focused", "index"]:
        if key in cat_lower:
            return key.title()
    return "Equity"


# ────────────────────────────────────────────────
# 4.5: EXIT LOAD
# ────────────────────────────────────────────────

def parse_exit_load(metadata: Dict) -> ExitLoadInfo:
    """Parse exit load structure from metadata."""
    load_data = metadata.get("exit_load", [])
    lock_in = metadata.get("lock_in_days")

    sip_note = (
        "Each SIP installment has its OWN exit load clock. "
        "The earliest installments become exit-load-free first."
    )

    return ExitLoadInfo(
        load_structure=load_data,
        lock_in_period_days=lock_in,
        sip_consideration=sip_note,
    )


# ────────────────────────────────────────────────
# 4.6: FUND HOUSE PEDIGREE
# ────────────────────────────────────────────────

def analyse_fund_house(metadata: Dict) -> FundHouseInfo:
    """Analyse fund house / AMC quality."""
    fh = metadata.get("fund_house", {})

    name = fh.get("name", "Unknown AMC")
    aum = fh.get("aum_cr")
    rank = fh.get("rank")
    schemes = fh.get("total_schemes")
    years = fh.get("years_in_operation")

    # Grade
    if rank is not None and rank <= 5:
        grade = "TOP TIER"
    elif rank is not None and rank <= 15:
        grade = "ESTABLISHED"
    elif aum and aum > 50000:
        grade = "ESTABLISHED"
    elif aum and aum > 10000:
        grade = "MID TIER"
    else:
        grade = "SMALL"

    return FundHouseInfo(
        amc_name=name,
        amc_aum_cr=aum,
        amc_rank=rank,
        total_schemes=schemes,
        years_in_operation=years,
        reputation_grade=grade,
    )


# ────────────────────────────────────────────────
# OVERALL STRUCTURAL SCORING
# ────────────────────────────────────────────────

def _compute_structural_score(
    expense: Optional[ExpenseRatioAnalysis],
    turnover: Optional[TurnoverAnalysis],
    manager: Optional[FundManagerAnalysis],
    aum: Optional[AUMAnalysis],
    fund_house: Optional[FundHouseInfo],
) -> Tuple[float, str]:
    """
    Compute an overall structural quality score (0-100).

    Weights:
        Expense Ratio:    30%
        Turnover:         15%
        Fund Manager:     25%
        AUM:              15%
        Fund House:       15%
    """
    scores: Dict[str, float] = {}

    # ── Expense ratio score (30%) ──
    if expense:
        grade_scores = {"EXCELLENT": 95, "GOOD": 75, "AVERAGE": 50, "EXPENSIVE": 25, "UNKNOWN": 40}
        scores["expense"] = grade_scores.get(expense.expense_grade, 40)
    else:
        scores["expense"] = 50

    # ── Turnover score (15%) ──
    if turnover and turnover.turnover_ratio_pct is not None:
        tr = turnover.turnover_ratio_pct
        if tr < 25:
            scores["turnover"] = 95
        elif tr < 50:
            scores["turnover"] = 80
        elif tr < 100:
            scores["turnover"] = 60
        elif tr < 200:
            scores["turnover"] = 35
        else:
            scores["turnover"] = 15
    else:
        scores["turnover"] = 50

    # ── Manager score (25%) ──
    if manager:
        tenure_scores = {"EXCELLENT": 95, "GOOD": 75, "CONCERN": 40, "HIGH RISK": 15, "UNKNOWN": 35}
        stability_scores = {"VERY STABLE": 95, "STABLE": 80, "MODERATE": 55, "UNSTABLE": 20}
        t_score = tenure_scores.get(manager.tenure_grade, 35)
        s_score = stability_scores.get(manager.stability_grade, 35)
        scores["manager"] = 0.6 * t_score + 0.4 * s_score

        # Penalty for too many funds
        if manager.current_managers:
            for m in manager.current_managers:
                if m.num_funds_managed and m.num_funds_managed > 7:
                    scores["manager"] = max(scores["manager"] - 15, 0)
    else:
        scores["manager"] = 40

    # ── AUM score (15%) ──
    if aum:
        size_scores = {"OPTIMAL": 90, "ACCEPTABLE": 70, "CONCERN": 40, "CRITICAL": 15}
        scores["aum"] = size_scores.get(aum.size_grade, 50)

        if aum.aum_trend == "Spiking":
            scores["aum"] = max(scores["aum"] - 10, 0)
        elif aum.aum_trend == "Declining":
            scores["aum"] = max(scores["aum"] - 15, 0)
    else:
        scores["aum"] = 50

    # ── Fund house score (15%) ──
    if fund_house:
        house_scores = {"TOP TIER": 90, "ESTABLISHED": 75, "MID TIER": 55, "SMALL": 35}
        scores["fund_house"] = house_scores.get(fund_house.reputation_grade, 45)
    else:
        scores["fund_house"] = 50

    # ── Weighted composite ──
    weights = {
        "expense": 0.30,
        "turnover": 0.15,
        "manager": 0.25,
        "aum": 0.15,
        "fund_house": 0.15,
    }

    composite = sum(scores[k] * weights[k] for k in scores)
    composite = round(composite, 1)

    # Grade
    if composite >= 80:
        grade = "EXCELLENT"
    elif composite >= 65:
        grade = "GOOD"
    elif composite >= 50:
        grade = "AVERAGE"
    elif composite >= 35:
        grade = "BELOW AVERAGE"
    else:
        grade = "POOR"

    return composite, grade


# ────────────────────────────────────────────────
# INTERPRETATION ENGINE
# ────────────────────────────────────────────────

def _interpret_structural(
    expense: Optional[ExpenseRatioAnalysis],
    turnover: Optional[TurnoverAnalysis],
    manager: Optional[FundManagerAnalysis],
    aum: Optional[AUMAnalysis],
    exit_load: Optional[ExitLoadInfo],
    fund_house: Optional[FundHouseInfo],
    score: float,
    grade: str,
) -> List[str]:
    """Generate advisory-grade insights from structural analysis."""
    insights: List[str] = []

    # ════════════════════════════════════════
    # EXPENSE RATIO
    # ════════════════════════════════════════
    if expense:
        insights.append("─" * 55)
        insights.append("💰  EXPENSE RATIO ANALYSIS")
        insights.append("─" * 55)

        grade_icons = {"EXCELLENT": "🏆", "GOOD": "✅", "AVERAGE": "🔶", "EXPENSIVE": "❌"}
        icon = grade_icons.get(expense.expense_grade, "")

        if expense.current_direct_pct is not None:
            insights.append(
                f"{icon}  Direct TER: {expense.current_direct_pct:.2f}% — {expense.expense_grade}"
            )

        if expense.current_regular_pct is not None:
            diff = expense.current_regular_pct - (expense.current_direct_pct or 0)
            insights.append(
                f"    Regular TER: {expense.current_regular_pct:.2f}% "
                f"(commission drag: {diff:.2f}%)"
            )
            if diff > 0.6:
                insights.append(
                    f"    ⚡ Switching from Regular to Direct saves {diff:.2f}% annually!"
                )

        if expense.cheaper_than_category is not None:
            if expense.cheaper_than_category:
                insights.append(
                    f"    ✅ {abs(expense.cost_difference_pct):.2f}% CHEAPER than category average "
                    f"({expense.category_avg_direct_pct:.2f}%)"
                )
            else:
                insights.append(
                    f"    ⚠️  {expense.cost_difference_pct:.2f}% MORE than category average "
                    f"({expense.category_avg_direct_pct:.2f}%)"
                )

        if expense.alpha_breakeven_pct is not None:
            insights.append(
                f"\n    📊 Alpha Break-Even: Fund must generate ≥{expense.alpha_breakeven_pct:.2f}% "
                f"alpha to justify cost vs index fund."
            )

        # Cost simulation highlight
        if "20Y" in expense.cost_simulations:
            sim_20y = expense.cost_simulations["20Y"]
            if "Direct Plan" in sim_20y and "Zero Cost (Gross)" in sim_20y:
                cost = sim_20y["Direct Plan"]["cost_drag"]
                insights.append(
                    f"\n    💸 20-Year cost on ₹10L investment: ₹{cost:,.0f} "
                    f"(at 14% gross return)"
                )

        insights.append("")

    # ════════════════════════════════════════
    # TURNOVER
    # ════════════════════════════════════════
    if turnover:
        insights.append("─" * 55)
        insights.append("🔄  PORTFOLIO TURNOVER ANALYSIS")
        insights.append("─" * 55)

        tr_icons = {"Buy & Hold": "🏆", "Low Turnover": "✅", "Moderate": "🔶",
                     "High": "⚠️", "Very High": "❌"}
        icon = tr_icons.get(turnover.turnover_grade, "")

        insights.append(
            f"{icon}  Turnover: {turnover.turnover_ratio_pct:.0f}% — {turnover.turnover_grade}"
        )

        if turnover.category_avg_turnover_pct:
            diff = turnover.turnover_ratio_pct - turnover.category_avg_turnover_pct
            insights.append(
                f"    vs Category Avg: {diff:+.0f}% "
                f"(category: {turnover.category_avg_turnover_pct:.0f}%)"
            )

        insights.append(f"\n    Hidden cost breakdown:")
        insights.append(f"      Brokerage drag:    {turnover.estimated_brokerage_drag_pct:.3f}%")
        insights.append(f"      Impact cost drag:  {turnover.estimated_impact_cost_drag_pct:.3f}%")
        insights.append(f"      STT drag:          {turnover.estimated_stt_drag_pct:.3f}%")
        insights.append(f"      ─────────────────────────")
        insights.append(f"      Total hidden cost: {turnover.total_hidden_cost_pct:.3f}%")
        insights.append(
            f"\n    📊 Effective total cost (TER + hidden): "
            f"{turnover.effective_total_cost_pct:.3f}%"
        )

        insights.append("")

    # ════════════════════════════════════════
    # FUND MANAGER
    # ════════════════════════════════════════
    if manager:
        insights.append("─" * 55)
        insights.append("👤  FUND MANAGER ANALYSIS")
        insights.append("─" * 55)

        for m in manager.current_managers:
            tenure_str = f"{m.tenure_years:.1f} years" if m.tenure_years else "Unknown"
            exp_str = f"{m.total_experience_years} years" if m.total_experience_years else "Unknown"
            funds_str = f"{m.num_funds_managed} funds" if m.num_funds_managed else "Unknown"

            insights.append(f"    {m.name} ({m.designation or 'Fund Manager'})")
            insights.append(f"      Tenure: {tenure_str} | Experience: {exp_str} | Managing: {funds_str}")

            if m.num_funds_managed and m.num_funds_managed > 7:
                insights.append(f"      ⚠️  Managing {m.num_funds_managed} funds — attention may be stretched thin.")
            if m.qualification:
                insights.append(f"      Qualification: {m.qualification}")

        # Stability
        stability_icons = {"VERY STABLE": "🏆", "STABLE": "✅", "MODERATE": "🔶", "UNSTABLE": "❌"}
        tenure_icons = {"EXCELLENT": "🏆", "GOOD": "✅", "CONCERN": "⚠️", "HIGH RISK": "❌"}

        insights.append(
            f"\n    {stability_icons.get(manager.stability_grade, '')}  "
            f"Stability: {manager.stability_grade} "
            f"({manager.total_manager_changes} manager changes)"
        )
        insights.append(
            f"    {tenure_icons.get(manager.tenure_grade, '')}  "
            f"Current Tenure: {manager.tenure_grade}"
        )

        if manager.tenure_grade == "HIGH RISK":
            insights.append(
                f"\n    ⚡ WARNING: Manager has < 1 year tenure. "
                f"Track record under current manager is INSUFFICIENT. "
                f"Historical performance may not repeat."
            )
        elif manager.tenure_grade == "CONCERN":
            insights.append(
                f"\n    ⚠️  Manager tenure < 3 years — allow 6-12 months "
                f"for strategy to fully establish."
            )

        if manager.stability_grade == "UNSTABLE":
            insights.append(
                f"\n    ❌ Frequent manager changes indicate organisational instability. "
                f"Past performance is unreliable as a future indicator."
            )

        insights.append("")

    # ════════════════════════════════════════
    # AUM
    # ════════════════════════════════════════
    if aum:
        insights.append("─" * 55)
        insights.append("📊  AUM ANALYSIS")
        insights.append("─" * 55)

        if aum.current_aum_cr:
            insights.append(f"    Current AUM: ₹{aum.current_aum_cr:,.0f} Cr")
            insights.append(
                f"    Ideal Range for {_extract_category_key(aum.category)}: "
                f"₹{aum.ideal_aum_range_cr[0]:,.0f} - ₹{aum.ideal_aum_range_cr[1]:,.0f} Cr"
            )

        size_icons = {"OPTIMAL": "✅", "ACCEPTABLE": "🔶", "CONCERN": "⚠️", "CRITICAL": "❌"}
        insights.append(
            f"    {size_icons.get(aum.size_grade, '')}  Size Grade: {aum.size_grade}"
        )

        if aum.size_concern:
            insights.append(f"    {aum.size_concern}")

        if aum.aum_trend:
            trend_icons = {"Growing": "📈", "Stable": "📊", "Declining": "📉", "Spiking": "🚀"}
            insights.append(
                f"    {trend_icons.get(aum.aum_trend, '')}  Trend: {aum.aum_trend}"
            )

        if aum.aum_growth_1y_pct is not None:
            insights.append(f"    1-Year AUM Growth: {aum.aum_growth_1y_pct:+.1f}%")

            if aum.aum_growth_1y_pct > 80:
                insights.append(
                    f"    ⚠️  Rapid AUM growth may indicate hot money chasing performance. "
                    f"Watch for deployment challenges."
                )

        insights.append("")

    # ════════════════════════════════════════
    # EXIT LOAD
    # ════════════════════════════════════════
    if exit_load:
        insights.append("─" * 55)
        insights.append("🚪  EXIT LOAD STRUCTURE")
        insights.append("─" * 55)

        for entry in exit_load.load_structure:
            period = entry.get("period", "Unknown")
            load = entry.get("load_pct", 0)
            if load > 0:
                insights.append(f"    {period}: {load:.1f}%")
            else:
                insights.append(f"    {period}: NIL ✅")

        if exit_load.lock_in_period_days:
            insights.append(
                f"\n    🔒 Lock-in Period: {exit_load.lock_in_period_days} days"
            )

        insights.append(f"\n    💡 SIP Note: {exit_load.sip_consideration}")
        insights.append("")

    # ════════════════════════════════════════
    # FUND HOUSE
    # ════════════════════════════════════════
    if fund_house:
        insights.append("─" * 55)
        insights.append("🏛️   FUND HOUSE PEDIGREE")
        insights.append("─" * 55)

        house_icons = {"TOP TIER": "🏆", "ESTABLISHED": "✅", "MID TIER": "🔶", "SMALL": "⚠️"}
        insights.append(
            f"    {house_icons.get(fund_house.reputation_grade, '')}  "
            f"{fund_house.amc_name} — {fund_house.reputation_grade}"
        )

        if fund_house.amc_aum_cr:
            insights.append(f"    AMC AUM: ₹{fund_house.amc_aum_cr:,.0f} Cr")
        if fund_house.amc_rank:
            insights.append(f"    Industry Rank: #{fund_house.amc_rank}")
        if fund_house.total_schemes:
            insights.append(f"    Total Schemes: {fund_house.total_schemes}")

            if fund_house.total_schemes > 100:
                insights.append(
                    f"    ⚠️  Large number of schemes — resources may be spread thin."
                )
        if fund_house.years_in_operation:
            insights.append(f"    Years in Operation: {fund_house.years_in_operation}")

        insights.append("")

    # ════════════════════════════════════════
    # OVERALL VERDICT
    # ════════════════════════════════════════
    insights.append("═" * 55)
    insights.append("📋  OVERALL STRUCTURAL QUALITY")
    insights.append("═" * 55)

    grade_icons_full = {
        "EXCELLENT": "🏆", "GOOD": "✅", "AVERAGE": "🔶",
        "BELOW AVERAGE": "⚠️", "POOR": "❌",
    }
    icon = grade_icons_full.get(grade, "")

    insights.append(f"    {icon}  Score: {score:.1f}/100 — {grade}")

    # Score bar
    bar_width = 40
    filled = int(score / 100 * bar_width)
    empty = bar_width - filled
    insights.append(f"    │{'█' * filled}{'░' * empty}│ {score:.1f}%")

    if grade == "EXCELLENT":
        insights.append(
            "    Fund has excellent structural characteristics. "
            "Low cost, stable management, appropriate size."
        )
    elif grade == "GOOD":
        insights.append(
            "    Structural quality is sound. No major concerns."
        )
    elif grade == "AVERAGE":
        insights.append(
            "    Some structural concerns exist. Monitor for changes."
        )
    else:
        insights.append(
            "    Significant structural risks present. Consider alternatives."
        )

    insights.append("")

    return insights


# ────────────────────────────────────────────────
# PUBLIC: Full report (one-call convenience)
# ────────────────────────────────────────────────

def generate_structural_report(
    metadata: Dict,
) -> StructuralReport:
    """
    End-to-end structural analysis:
      1. Expense ratio with cost simulations
      2. Portfolio turnover with hidden cost estimation
      3. Fund manager tenure and stability
      4. AUM size-strategy compatibility
      5. Exit load structure
      6. Fund house pedigree
      7. Overall structural score and interpretation

    Parameters
    ----------
    metadata : dict with all fund metadata fields

    Returns
    -------
    StructuralReport
    """
    category = metadata.get("category", "")
    cat_benchmark = get_category_benchmark(category)

    # ── 1. Expense ratio ──
    expense = analyse_expense_ratio(metadata, cat_benchmark)

    # ── 2. Turnover ──
    turnover = analyse_turnover(metadata, cat_benchmark)

    # ── 3. Fund manager ──
    manager = analyse_fund_manager(metadata)

    # ── 4. AUM ──
    aum = analyse_aum(metadata, cat_benchmark)

    # ── 5. Exit load ──
    exit_load = parse_exit_load(metadata)

    # ── 6. Fund house ──
    fund_house = analyse_fund_house(metadata)

    # ── 7. Score ──
    score, grade = _compute_structural_score(expense, turnover, manager, aum, fund_house)

    # ── 8. Interpretation ──
    interpretation = _interpret_structural(
        expense, turnover, manager, aum, exit_load, fund_house, score, grade
    )

    return StructuralReport(
        scheme_name=metadata.get("scheme_name", "Unknown"),
        scheme_category=category,
        as_of_date=dt.date.today(),
        expense_analysis=expense,
        turnover_analysis=turnover,
        manager_analysis=manager,
        aum_analysis=aum,
        exit_load=exit_load,
        fund_house=fund_house,
        structural_score=score,
        structural_grade=grade,
        interpretation=interpretation,
    )