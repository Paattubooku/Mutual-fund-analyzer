"""
metrics/portfolio_analysis.py
─────────────────────────────
SECTION 3 — Portfolio-Level Analysis Parameters

Analyses the CONTENTS of a fund's portfolio:
    3.1  Portfolio P/E and P/B Ratios (valuation orientation)
    3.2  Sector Allocation (overweight/underweight vs benchmark)
    3.3  Concentration of Top Holdings (conviction level)
    3.4  Market Capitalization Bias (large/mid/small tilt)
    3.5  Portfolio Overlap (redundancy between funds)
    3.6  Equity Style Box Mapping (value-blend-growth × size)
    3.7  Active Share (sector-level)

Public API
----------
    analyse_sectors(portfolio, benchmark=None)
    analyse_concentration(portfolio)
    analyse_market_cap(portfolio, benchmark=None)
    calculate_style_box(portfolio)
    calculate_overlap(portfolio_a, portfolio_b)
    generate_portfolio_report(portfolio, benchmark=None, comparison_portfolios=None)
"""

from __future__ import annotations

import datetime as dt
from typing import Optional, List, Tuple, Dict
from collections import defaultdict

import numpy as np

from data.models import (
    PortfolioSnapshot,
    BenchmarkPortfolio,
    StockHolding,
    SectorAllocation,
    SectorAnalysis,
    ConcentrationAnalysis,
    MarketCapBreakdown,
    StyleBoxPosition,
    PortfolioOverlap,
    PortfolioAnalysisReport,
)


# ────────────────────────────────────────────────
# 3.1 & 3.2: SECTOR ALLOCATION ANALYSIS
# ────────────────────────────────────────────────

def analyse_sectors(
    portfolio: PortfolioSnapshot,
    benchmark: Optional[BenchmarkPortfolio] = None,
) -> SectorAnalysis:
    """
    Analyse sector allocation:
      - Fund weight per sector
      - Over/underweight vs benchmark
      - Concentration (top 3, HHI)
      - Sector-level active share

    Parameters
    ----------
    portfolio : PortfolioSnapshot
    benchmark : BenchmarkPortfolio (optional)

    Returns
    -------
    SectorAnalysis
    """
    # ── Aggregate holdings by sector ──
    sector_map: Dict[str, List[StockHolding]] = defaultdict(list)
    for h in portfolio.equity_holdings:
        sector_map[h.sector].append(h)

    # ── Build sector allocations ──
    sector_allocs: List[SectorAllocation] = []
    total_weight = sum(h.weight_pct for h in portfolio.equity_holdings)

    for sector, holdings in sorted(sector_map.items(),
                                   key=lambda x: sum(h.weight_pct for h in x[1]),
                                   reverse=True):
        fund_wt = sum(h.weight_pct for h in holdings)

        bench_wt = None
        overweight = None
        if benchmark is not None:
            bench_wt = benchmark.sector_weights.get(sector, 0.0)
            overweight = round(fund_wt - bench_wt, 2)

        top_stock = max(holdings, key=lambda h: h.weight_pct)

        sector_allocs.append(SectorAllocation(
            sector=sector,
            fund_weight_pct=round(fund_wt, 2),
            benchmark_weight_pct=bench_wt,
            overweight_pct=overweight,
            num_stocks=len(holdings),
            top_stock=top_stock.stock_name,
            top_stock_weight_pct=round(top_stock.weight_pct, 2),
        ))

    # ── Top 3 sector concentration ──
    sorted_weights = sorted(
        [s.fund_weight_pct for s in sector_allocs], reverse=True
    )
    top_3 = sum(sorted_weights[:3]) if len(sorted_weights) >= 3 else sum(sorted_weights)

    # ── HHI (Herfindahl-Hirschman Index) ──
    # Normalise sector weights to sum to 100 for HHI
    hhi = sum((w / total_weight * 100) ** 2 for w in sorted_weights) if total_weight > 0 else 0

    # ── Sector-level Active Share ──
    active_share = None
    if benchmark is not None:
        all_sectors = set(s.sector for s in sector_allocs)
        all_sectors |= set(benchmark.sector_weights.keys())

        active_share_sum = 0.0
        for sector in all_sectors:
            fund_w = next(
                (s.fund_weight_pct for s in sector_allocs if s.sector == sector),
                0.0
            )
            bench_w = benchmark.sector_weights.get(sector, 0.0)
            active_share_sum += abs(fund_w - bench_w)

        active_share = round(active_share_sum / 2.0, 2)

    return SectorAnalysis(
        sectors=sector_allocs,
        top_3_concentration_pct=round(top_3, 2),
        hhi=round(hhi, 2),
        active_share_sector_pct=active_share,
        num_sectors=len(sector_allocs),
    )


# ────────────────────────────────────────────────
# 3.3: CONCENTRATION OF TOP HOLDINGS
# ────────────────────────────────────────────────

def analyse_concentration(
    portfolio: PortfolioSnapshot,
) -> ConcentrationAnalysis:
    """
    Analyse portfolio concentration:
      - Top 5, 10, 15, 20 holdings concentration
      - Largest single holding
      - HHI on individual holdings
      - Concentration grade

    Parameters
    ----------
    portfolio : PortfolioSnapshot

    Returns
    -------
    ConcentrationAnalysis
    """
    sorted_holdings = sorted(
        portfolio.equity_holdings,
        key=lambda h: h.weight_pct,
        reverse=True,
    )

    weights = [h.weight_pct for h in sorted_holdings]
    n = len(weights)

    top_5 = sum(weights[:5]) if n >= 5 else sum(weights)
    top_10 = sum(weights[:10]) if n >= 10 else sum(weights)
    top_15 = sum(weights[:15]) if n >= 15 else sum(weights)
    top_20 = sum(weights[:20]) if n >= 20 else sum(weights)

    largest = sorted_holdings[0] if sorted_holdings else None
    largest_name = largest.stock_name if largest else "N/A"
    largest_pct = largest.weight_pct if largest else 0.0

    # HHI on individual holdings
    total_w = sum(weights)
    if total_w > 0:
        hhi = sum((w / total_w * 100) ** 2 for w in weights)
    else:
        hhi = 0.0

    # Concentration grade
    if portfolio.total_stocks < 25:
        grade = "High Conviction"
    elif portfolio.total_stocks <= 50:
        if top_10 > 55:
            grade = "Concentrated"
        else:
            grade = "Moderate"
    elif portfolio.total_stocks <= 80:
        grade = "Diversified"
    else:
        grade = "Over-Diversified"

    return ConcentrationAnalysis(
        top_5_weight_pct=round(top_5, 2),
        top_10_weight_pct=round(top_10, 2),
        top_15_weight_pct=round(top_15, 2),
        top_20_weight_pct=round(top_20, 2),
        total_stocks=portfolio.total_stocks,
        largest_holding_name=largest_name,
        largest_holding_pct=round(largest_pct, 2),
        hhi_holdings=round(hhi, 2),
        concentration_grade=grade,
    )


# ────────────────────────────────────────────────
# 3.4: MARKET CAP BREAKDOWN
# ────────────────────────────────────────────────

def analyse_market_cap(
    portfolio: PortfolioSnapshot,
    benchmark: Optional[BenchmarkPortfolio] = None,
) -> MarketCapBreakdown:
    """
    Analyse market capitalization distribution:
      - Large / Mid / Small cap allocation
      - Weighted average market cap
      - Bias detection vs benchmark

    Market Cap Classification (SEBI):
        Large Cap:  Top 100 by market cap
        Mid Cap:    101-250
        Small Cap:  251+

    Parameters
    ----------
    portfolio : PortfolioSnapshot
    benchmark : BenchmarkPortfolio (optional)

    Returns
    -------
    MarketCapBreakdown
    """
    large_wt = 0.0
    mid_wt = 0.0
    small_wt = 0.0
    mcap_values = []
    mcap_weights = []

    for h in portfolio.equity_holdings:
        cat = (h.market_cap_category or "").lower()
        if "large" in cat:
            large_wt += h.weight_pct
        elif "mid" in cat:
            mid_wt += h.weight_pct
        elif "small" in cat:
            small_wt += h.weight_pct

        if h.market_cap_cr is not None and h.market_cap_cr > 0:
            mcap_values.append(h.market_cap_cr)
            mcap_weights.append(h.weight_pct)

    # Weighted average market cap
    wavg_mcap = None
    median_mcap = None
    if mcap_values:
        total_w = sum(mcap_weights)
        if total_w > 0:
            wavg_mcap = sum(
                m * w for m, w in zip(mcap_values, mcap_weights)
            ) / total_w
        median_mcap = float(np.median(mcap_values))

    # Benchmark comparison
    bench_large = benchmark.large_cap_pct if benchmark else None
    bench_mid = benchmark.mid_cap_pct if benchmark else None
    bench_small = benchmark.small_cap_pct if benchmark else None

    # Bias detection
    bias = _detect_mcap_bias(large_wt, mid_wt, small_wt, benchmark)

    return MarketCapBreakdown(
        large_cap_pct=round(large_wt, 2),
        mid_cap_pct=round(mid_wt, 2),
        small_cap_pct=round(small_wt, 2),
        weighted_avg_mcap_cr=round(wavg_mcap, 0) if wavg_mcap else None,
        median_mcap_cr=round(median_mcap, 0) if median_mcap else None,
        bench_large_pct=bench_large,
        bench_mid_pct=bench_mid,
        bench_small_pct=bench_small,
        bias=bias,
    )


def _detect_mcap_bias(
    large: float, mid: float, small: float,
    benchmark: Optional[BenchmarkPortfolio],
) -> str:
    """Detect market cap bias relative to benchmark or absolute."""
    if benchmark is not None:
        large_diff = large - benchmark.large_cap_pct
        mid_diff = mid - benchmark.mid_cap_pct
        small_diff = small - benchmark.small_cap_pct

        if large_diff > 10:
            return "Large Cap Overweight"
        elif mid_diff > 10:
            return "Mid Cap Tilted"
        elif small_diff > 10:
            return "Small Cap Tilted"
        elif large_diff < -10:
            return "Large Cap Underweight (Mid/Small Tilt)"
        else:
            return "Balanced (Near Benchmark)"
    else:
        if large > 70:
            return "Large Cap Dominant"
        elif mid > 40:
            return "Mid Cap Dominant"
        elif small > 40:
            return "Small Cap Dominant"
        elif large > 50:
            return "Large Cap Tilted"
        else:
            return "Multi-Cap Balanced"


# ────────────────────────────────────────────────
# 3.5: PORTFOLIO OVERLAP
# ────────────────────────────────────────────────

def calculate_overlap(
    portfolio_a: PortfolioSnapshot,
    portfolio_b: PortfolioSnapshot,
) -> PortfolioOverlap:
    """
    Calculate portfolio overlap between two funds.

    Formula:
        Overlap% = Σ min(weight_A_i, weight_B_i) for all common stocks

    Parameters
    ----------
    portfolio_a, portfolio_b : PortfolioSnapshot

    Returns
    -------
    PortfolioOverlap
    """
    # Build lookup by stock name (ISIN would be better but may be None)
    def _key(h: StockHolding) -> str:
        return h.isin if h.isin else h.stock_name.lower().strip()

    map_a = {}
    for h in portfolio_a.equity_holdings:
        k = _key(h)
        map_a[k] = (h.stock_name, h.weight_pct)

    map_b = {}
    for h in portfolio_b.equity_holdings:
        k = _key(h)
        map_b[k] = (h.stock_name, h.weight_pct)

    # Find common stocks
    common_keys = set(map_a.keys()) & set(map_b.keys())
    common_stocks = len(common_keys)

    overlap_total = 0.0
    common_detail: List[Tuple[str, float, float]] = []

    for k in common_keys:
        name_a, wt_a = map_a[k]
        name_b, wt_b = map_b[k]
        overlap_contrib = min(wt_a, wt_b)
        overlap_total += overlap_contrib
        common_detail.append((name_a, wt_a, wt_b))

    # Sort by overlap contribution (min weight)
    common_detail.sort(key=lambda x: min(x[1], x[2]), reverse=True)
    top_common = common_detail[:10]

    # Grade
    if overlap_total > 60:
        grade = "Very High (Redundant)"
    elif overlap_total > 40:
        grade = "High"
    elif overlap_total > 20:
        grade = "Moderate"
    else:
        grade = "Low (Good Diversification)"

    return PortfolioOverlap(
        fund_a_name=portfolio_a.scheme_name,
        fund_b_name=portfolio_b.scheme_name,
        overlap_pct=round(overlap_total, 2),
        common_stocks=common_stocks,
        total_stocks_a=portfolio_a.total_stocks,
        total_stocks_b=portfolio_b.total_stocks,
        top_common_holdings=top_common,
        overlap_grade=grade,
    )


# ────────────────────────────────────────────────
# 3.6: EQUITY STYLE BOX
# ────────────────────────────────────────────────

def calculate_style_box(
    portfolio: PortfolioSnapshot,
    benchmark: Optional[BenchmarkPortfolio] = None,
) -> StyleBoxPosition:
    """
    Map the portfolio to the 3×3 equity style box.

    Value Axis (based on P/E and P/B vs market):
        Value:  P/E significantly below market
        Blend:  P/E near market average
        Growth: P/E significantly above market

    Size Axis (based on weighted avg market cap):
        Large Cap:  Avg Mkt Cap > ₹50,000 Cr
        Mid Cap:    ₹10,000 - 50,000 Cr
        Small Cap:  < ₹10,000 Cr

    Parameters
    ----------
    portfolio : PortfolioSnapshot
    benchmark : BenchmarkPortfolio (optional, for value axis calibration)

    Returns
    -------
    StyleBoxPosition
    """
    # ── SIZE axis ──
    mcap = analyse_market_cap(portfolio, benchmark)

    if mcap.weighted_avg_mcap_cr is not None:
        avg_mcap = mcap.weighted_avg_mcap_cr
        if avg_mcap > 50000:
            size_score = 3.0
            size_label = "Large Cap"
        elif avg_mcap > 10000:
            size_score = 2.0
            size_label = "Mid Cap"
        else:
            size_score = 1.0
            size_label = "Small Cap"
    else:
        # Fallback: use market cap allocation percentages
        if mcap.large_cap_pct > 60:
            size_score = 3.0
            size_label = "Large Cap"
        elif mcap.mid_cap_pct > 40 or mcap.large_cap_pct < 30:
            size_score = 1.5
            size_label = "Mid/Small Cap"
        else:
            size_score = 2.0
            size_label = "Mid Cap"

    # ── VALUE axis ──
    bench_pe = benchmark.pe_ratio if benchmark and benchmark.pe_ratio else 24.0
    bench_pb = benchmark.pb_ratio if benchmark and benchmark.pb_ratio else 3.5

    fund_pe = portfolio.portfolio_pe
    fund_pb = portfolio.portfolio_pb

    if fund_pe is not None and fund_pb is not None:
        # Score based on relative P/E and P/B
        pe_ratio = fund_pe / bench_pe if bench_pe > 0 else 1.0
        pb_ratio = fund_pb / bench_pb if bench_pb > 0 else 1.0

        # Combined valuation score (weighted avg of PE and PB ratios)
        val_ratio = 0.6 * pe_ratio + 0.4 * pb_ratio

        if val_ratio < 0.8:
            value_score = 1.0
            value_label = "Value"
        elif val_ratio < 0.95:
            value_score = 2.0
            value_label = "Blend"
        elif val_ratio < 1.15:
            value_score = 3.0
            value_label = "Blend"
        elif val_ratio < 1.3:
            value_score = 4.0
            value_label = "Growth"
        else:
            value_score = 5.0
            value_label = "Growth"
    else:
        value_score = 3.0
        value_label = "Blend"

    style_label = f"{size_label} {value_label}"

    return StyleBoxPosition(
        value_score=round(value_score, 1),
        value_label=value_label,
        size_score=round(size_score, 1),
        size_label=size_label,
        style_label=style_label,
    )


# ────────────────────────────────────────────────
# INTERPRETATION ENGINE
# ────────────────────────────────────────────────

def _interpret_portfolio(
    portfolio: PortfolioSnapshot,
    sector_analysis: Optional[SectorAnalysis],
    concentration: Optional[ConcentrationAnalysis],
    market_cap: Optional[MarketCapBreakdown],
    style_box: Optional[StyleBoxPosition],
    overlaps: Optional[List[PortfolioOverlap]],
) -> List[str]:
    """Generate advisory-grade insights from portfolio analysis."""
    insights: List[str] = []

    # ════════════════════════════════════════
    # VALUATION
    # ════════════════════════════════════════
    insights.append("─" * 55)
    insights.append("📊  PORTFOLIO VALUATION")
    insights.append("─" * 55)

    if portfolio.portfolio_pe is not None:
        pe = portfolio.portfolio_pe
        if pe < 18:
            insights.append(f"✅  P/E = {pe:.1f} — Value-oriented portfolio (cheaper than market).")
        elif pe < 25:
            insights.append(f"🔶  P/E = {pe:.1f} — Fairly valued portfolio (near market average).")
        elif pe < 35:
            insights.append(f"⚠️   P/E = {pe:.1f} — Growth-oriented portfolio (premium valuation).")
        else:
            insights.append(f"❌  P/E = {pe:.1f} — Very expensive portfolio (high expectations embedded).")

    if portfolio.portfolio_pb is not None:
        pb = portfolio.portfolio_pb
        if pb < 2.0:
            insights.append(f"✅  P/B = {pb:.1f} — Deep value orientation.")
        elif pb < 4.0:
            insights.append(f"🔶  P/B = {pb:.1f} — Blend orientation.")
        else:
            insights.append(f"📈  P/B = {pb:.1f} — Growth/quality orientation (asset-light businesses).")

    if portfolio.portfolio_roe_pct is not None:
        roe = portfolio.portfolio_roe_pct
        if roe > 20:
            insights.append(f"✅  Weighted ROE = {roe:.1f}% — high quality businesses.")
        elif roe > 12:
            insights.append(f"🔶  Weighted ROE = {roe:.1f}% — moderate quality.")
        else:
            insights.append(f"⚠️   Weighted ROE = {roe:.1f}% — low quality / cyclicals / turnarounds.")

    insights.append("")

    # ════════════════════════════════════════
    # SECTOR ANALYSIS
    # ════════════════════════════════════════
    if sector_analysis:
        sa = sector_analysis
        insights.append("─" * 55)
        insights.append("📊  SECTOR ALLOCATION ANALYSIS")
        insights.append("─" * 55)

        # Top 3 concentration
        if sa.top_3_concentration_pct > 65:
            insights.append(
                f"⚠️   Top 3 sectors = {sa.top_3_concentration_pct:.1f}% — "
                f"HIGHLY concentrated (significant sector risk)."
            )
        elif sa.top_3_concentration_pct > 50:
            insights.append(
                f"🔶  Top 3 sectors = {sa.top_3_concentration_pct:.1f}% — "
                f"moderately concentrated."
            )
        else:
            insights.append(
                f"✅  Top 3 sectors = {sa.top_3_concentration_pct:.1f}% — "
                f"well diversified across sectors."
            )

        # Active share
        if sa.active_share_sector_pct is not None:
            ash = sa.active_share_sector_pct
            if ash > 40:
                insights.append(
                    f"✅  Sector Active Share = {ash:.1f}% — "
                    f"truly active manager with high-conviction sector bets."
                )
            elif ash > 20:
                insights.append(
                    f"🔶  Sector Active Share = {ash:.1f}% — "
                    f"moderately active."
                )
            else:
                insights.append(
                    f"⚠️   Sector Active Share = {ash:.1f}% — "
                    f"potential closet indexer (charging active fees for passive-like allocation)."
                )

        # Major overweights/underweights
        ow_sectors = [
            s for s in sa.sectors
            if s.overweight_pct is not None and s.overweight_pct > 3
        ]
        uw_sectors = [
            s for s in sa.sectors
            if s.overweight_pct is not None and s.overweight_pct < -3
        ]

        if ow_sectors:
            ow_str = ", ".join(
                f"{s.sector} ({s.overweight_pct:+.1f}%)"
                for s in sorted(ow_sectors, key=lambda x: x.overweight_pct, reverse=True)[:3]
            )
            insights.append(f"📈  Key OVERWEIGHTS: {ow_str}")

        if uw_sectors:
            uw_str = ", ".join(
                f"{s.sector} ({s.overweight_pct:+.1f}%)"
                for s in sorted(uw_sectors, key=lambda x: x.overweight_pct)[:3]
            )
            insights.append(f"📉  Key UNDERWEIGHTS: {uw_str}")

        insights.append("")

    # ════════════════════════════════════════
    # CONCENTRATION
    # ════════════════════════════════════════
    if concentration:
        con = concentration
        insights.append("─" * 55)
        insights.append("📊  CONCENTRATION ANALYSIS")
        insights.append("─" * 55)

        insights.append(f"📊  Grade: {con.concentration_grade}")
        insights.append(f"    Largest holding: {con.largest_holding_name} ({con.largest_holding_pct:.1f}%)")
        insights.append(f"    Top 5: {con.top_5_weight_pct:.1f}% | Top 10: {con.top_10_weight_pct:.1f}% | Total: {con.total_stocks} stocks")

        if con.total_stocks < 25:
            insights.append(
                f"✅  Focused portfolio ({con.total_stocks} stocks) — "
                f"manager's best ideas get meaningful allocation."
            )
            insights.append(
                f"⚠️   However, higher stock-specific risk — one bad pick has outsized impact."
            )
        elif con.total_stocks > 60:
            insights.append(
                f"⚠️   Very diversified ({con.total_stocks} stocks) — "
                f"approaches indexing but charges active fees."
            )
            insights.append(
                f"    Hard to beat benchmark meaningfully with this many positions."
            )

        if con.largest_holding_pct > 10:
            insights.append(
                f"⚠️   Largest holding ({con.largest_holding_name}) at {con.largest_holding_pct:.1f}% — "
                f"very high single-stock conviction."
            )

        insights.append("")

    # ════════════════════════════════════════
    # MARKET CAP
    # ════════════════════════════════════════
    if market_cap:
        mc = market_cap
        insights.append("─" * 55)
        insights.append("📊  MARKET CAP ANALYSIS")
        insights.append("─" * 55)

        insights.append(
            f"📊  Allocation: Large {mc.large_cap_pct:.1f}% | "
            f"Mid {mc.mid_cap_pct:.1f}% | Small {mc.small_cap_pct:.1f}%"
        )

        if mc.weighted_avg_mcap_cr:
            insights.append(f"    Weighted Avg Market Cap: ₹{mc.weighted_avg_mcap_cr:,.0f} Cr")

        if mc.bias:
            insights.append(f"    Bias: {mc.bias}")

        if mc.bench_large_pct is not None:
            insights.append(
                f"    vs Benchmark: Large {mc.large_cap_pct - mc.bench_large_pct:+.1f}% | "
                f"Mid {mc.mid_cap_pct - mc.bench_mid_pct:+.1f}% | "
                f"Small {mc.small_cap_pct - mc.bench_small_pct:+.1f}%"
            )

        insights.append("")

    # ════════════════════════════════════════
    # STYLE BOX
    # ════════════════════════════════════════
    if style_box:
        insights.append("─" * 55)
        insights.append("📊  EQUITY STYLE BOX POSITION")
        insights.append("─" * 55)
        insights.append(f"    📍 {style_box.style_label}")
        insights.append(
            f"    Size: {style_box.size_label} (score: {style_box.size_score}) | "
            f"Value/Growth: {style_box.value_label} (score: {style_box.value_score})"
        )
        insights.append("")

    # ════════════════════════════════════════
    # STRUCTURAL QUALITY
    # ════════════════════════════════════════
    insights.append("─" * 55)
    insights.append("📊  STRUCTURAL QUALITY")
    insights.append("─" * 55)

    if portfolio.expense_ratio_direct_pct is not None:
        ter = portfolio.expense_ratio_direct_pct
        if ter < 0.5:
            insights.append(f"🏆  Expense Ratio (Direct): {ter:.2f}% — EXCELLENT (below average).")
        elif ter < 1.0:
            insights.append(f"✅  Expense Ratio (Direct): {ter:.2f}% — reasonable.")
        elif ter < 1.5:
            insights.append(f"🔶  Expense Ratio (Direct): {ter:.2f}% — on the higher side.")
        else:
            insights.append(f"❌  Expense Ratio (Direct): {ter:.2f}% — expensive. Alpha must justify this.")

    if portfolio.turnover_ratio_pct is not None:
        tr = portfolio.turnover_ratio_pct
        if tr < 25:
            insights.append(f"✅  Turnover: {tr:.0f}% — buy-and-hold approach (low hidden costs).")
        elif tr < 50:
            insights.append(f"✅  Turnover: {tr:.0f}% — low turnover, patient investing.")
        elif tr < 100:
            insights.append(f"🔶  Turnover: {tr:.0f}% — moderate activity.")
        else:
            insights.append(f"⚠️   Turnover: {tr:.0f}% — high trading activity (hidden costs add up).")

    if portfolio.aum_cr is not None:
        aum = portfolio.aum_cr
        insights.append(f"    AUM: ₹{aum:,.0f} Cr")
        # Size appropriateness (simplified)
        category = portfolio.scheme_name.lower()
        if "small" in category and aum > 15000:
            insights.append(f"⚠️   AUM may be too large for a small-cap strategy — deployment challenges likely.")
        elif "mid" in category and aum > 25000:
            insights.append(f"🔶  AUM is large for a mid-cap strategy — monitor for large-cap drift.")

    insights.append("")

    # ════════════════════════════════════════
    # OVERLAP
    # ════════════════════════════════════════
    if overlaps:
        insights.append("─" * 55)
        insights.append("📊  PORTFOLIO OVERLAP ANALYSIS")
        insights.append("─" * 55)

        for ovl in overlaps:
            if ovl.overlap_pct > 60:
                icon = "❌"
            elif ovl.overlap_pct > 40:
                icon = "⚠️"
            elif ovl.overlap_pct > 20:
                icon = "🔶"
            else:
                icon = "✅"

            insights.append(
                f"{icon}  vs {ovl.fund_b_name}: "
                f"{ovl.overlap_pct:.1f}% overlap ({ovl.common_stocks} common stocks) "
                f"— {ovl.overlap_grade}"
            )

        high_overlaps = [o for o in overlaps if o.overlap_pct > 40]
        if high_overlaps:
            insights.append(
                f"\n⚡  WARNING: {len(high_overlaps)} fund(s) have >40% overlap. "
                f"Holding both provides LIMITED diversification benefit. "
                f"Consider dropping one."
            )
        insights.append("")

    return insights


# ────────────────────────────────────────────────
# PUBLIC: Full report (one-call convenience)
# ────────────────────────────────────────────────

def generate_portfolio_report(
    portfolio: PortfolioSnapshot,
    benchmark: Optional[BenchmarkPortfolio] = None,
    comparison_portfolios: Optional[List[PortfolioSnapshot]] = None,
) -> PortfolioAnalysisReport:
    """
    End-to-end portfolio analysis:
      1. Sector allocation (overweight/underweight, HHI, active share)
      2. Concentration (top N holdings, conviction level)
      3. Market cap breakdown (large/mid/small bias)
      4. Equity style box mapping
      5. Portfolio overlap (if comparison portfolios provided)
      6. Automated interpretation

    Parameters
    ----------
    portfolio    : PortfolioSnapshot (the fund being analysed)
    benchmark    : BenchmarkPortfolio (optional, for comparison)
    comparison_portfolios : list of PortfolioSnapshot for overlap analysis

    Returns
    -------
    PortfolioAnalysisReport
    """
    # ── 1. Sector analysis ──
    sector_analysis = analyse_sectors(portfolio, benchmark)

    # ── 2. Concentration ──
    concentration = analyse_concentration(portfolio)

    # ── 3. Market cap ──
    market_cap = analyse_market_cap(portfolio, benchmark)

    # ── 4. Style box ──
    style_box = calculate_style_box(portfolio, benchmark)

    # ── 5. Valuation summary ──
    valuation = {
        "P/E": portfolio.portfolio_pe,
        "P/B": portfolio.portfolio_pb,
        "ROE": portfolio.portfolio_roe_pct,
        "Div Yield": portfolio.portfolio_dividend_yield_pct,
    }

    # ── 6. Overlaps ──
    overlaps = None
    if comparison_portfolios:
        overlaps = []
        for comp in comparison_portfolios:
            overlap = calculate_overlap(portfolio, comp)
            overlaps.append(overlap)

    # ── 7. Interpretation ──
    interpretation = _interpret_portfolio(
        portfolio, sector_analysis, concentration,
        market_cap, style_box, overlaps,
    )

    return PortfolioAnalysisReport(
        scheme_name=portfolio.scheme_name,
        as_of_date=portfolio.as_of_date,
        sector_analysis=sector_analysis,
        concentration=concentration,
        market_cap=market_cap,
        style_box=style_box,
        valuation_summary=valuation,
        overlaps=overlaps,
        interpretation=interpretation,
    )