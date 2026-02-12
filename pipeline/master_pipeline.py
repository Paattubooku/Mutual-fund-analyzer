"""
pipeline/master_pipeline.py
───────────────────────────
The one-call master pipeline that orchestrates the entire
analysis flow: fetch → analyse → score → rank → display.

Public API
----------
    analyse_fund(scheme_code, benchmark_code=None, profile="growth")
    compare_funds(scheme_codes, profile="growth")
"""

from __future__ import annotations

import datetime as dt
import time
from typing import Optional, List, Dict

from data.fetcher import NAVFetcher, FetchError
from data.benchmarks import get_benchmark_code
from data.models import NAVData, MasterReport

from metrics.trailing_returns import generate_trailing_report
from metrics.rolling_returns import generate_rolling_report
from metrics.consistency import generate_consistency_report
from metrics.sip_returns import generate_sip_report
from metrics.risk_adjusted import generate_risk_adjusted_report

from metrics.scoring_engine import (
    extract_metrics_from_reports,
    score_fund,
    rank_funds,
    get_investment_profile,
    InvestmentProfile,
    FundScore,
    RankingTable,
    _calculate_max_drawdown,
)


class MasterPipeline:
    """
    Orchestrates the complete analysis pipeline.

    Usage
    -----
        pipeline = MasterPipeline()
        report = pipeline.analyse_fund(122639)
        ranking = pipeline.compare_funds([122639, 120503, 125497])
    """

    def __init__(self):
        self.fetcher = NAVFetcher()

    # ────────────────────────────────────────
    # PUBLIC: Analyse a single fund
    # ────────────────────────────────────────

    def analyse_fund(
        self,
        scheme_code: int,
        benchmark_code: Optional[int] = None,
        profile_name: str = "growth",
        sip_amount: float = 10000,
    ) -> MasterReport:
        """
        Run the COMPLETE analysis pipeline for a single fund.

        Steps:
            1. Fetch NAV data (fund + benchmark)
            2. Trailing returns (Section 1.1)
            3. Rolling returns (Section 1.2)
            4. Consistency & capture ratios (Section 1.3)
            5. SIP returns (Section 1.4)
            6. Risk-adjusted ratios (Section 2)
            7. Score (Section 7)

        Parameters
        ----------
        scheme_code    : AMFI scheme code
        benchmark_code : benchmark scheme code (None = auto-detect)
        profile_name   : investment profile ("aggressive"/"growth"/"balanced"/"conservative")
        sip_amount     : monthly SIP amount for SIP analysis

        Returns
        -------
        MasterReport
        """
        profile = get_investment_profile(profile_name)

        # ── 1. Fetch data ──
        fund_nav = self.fetcher.fetch(scheme_code)

        benchmark_nav = None
        if benchmark_code is None:
            benchmark_code = get_benchmark_code(fund_nav.scheme_info.scheme_category)
        if benchmark_code:
            try:
                benchmark_nav = self.fetcher.fetch(benchmark_code)
            except FetchError:
                pass

        # ── 2. Run all analyses (with graceful error handling) ──
        trailing = self._safe_run("Trailing Returns",
            lambda: generate_trailing_report(fund_nav, benchmark_nav))

        rolling = self._safe_run("Rolling Returns",
            lambda: generate_rolling_report(fund_nav, benchmark_nav, step_days=5))

        consistency = self._safe_run("Consistency",
            lambda: generate_consistency_report(fund_nav, benchmark_nav))

        sip = self._safe_run("SIP Returns",
            lambda: generate_sip_report(fund_nav, benchmark_nav, sip_amount))

        risk_adj = self._safe_run("Risk-Adjusted",
            lambda: generate_risk_adjusted_report(fund_nav, benchmark_nav, period_years=3))

        # ── 3. Extract metrics and score ──
        metrics = extract_metrics_from_reports(
            trailing_report=trailing,
            rolling_report=rolling,
            consistency_report=consistency,
            sip_report=sip,
            risk_report=risk_adj,
            nav_data=fund_nav,
        )

        fund_score = score_fund(
            fund_metrics=metrics,
            profile=profile,
            scheme_code=scheme_code,
            scheme_name=fund_nav.scheme_info.scheme_name,
            scheme_category=fund_nav.scheme_info.scheme_category,
        )

        # ── 4. Build summary ──
        summary = self._build_summary(fund_nav, fund_score, trailing, rolling, risk_adj)

        return MasterReport(
            scheme_info=fund_nav.scheme_info,
            as_of_date=fund_nav.latest_date,
            trailing_returns=trailing,
            rolling_returns=rolling,
            consistency=consistency,
            sip_returns=sip,
            risk_adjusted=risk_adj,
            fund_score=fund_score,
            summary=summary,
        )

    # ────────────────────────────────────────
    # PUBLIC: Compare and rank multiple funds
    # ────────────────────────────────────────

    def compare_funds(
        self,
        scheme_codes: List[int],
        profile_name: str = "growth",
        benchmark_code: Optional[int] = None,
    ) -> RankingTable:
        """
        Analyse and rank multiple funds with peer-relative scoring.

        Parameters
        ----------
        scheme_codes   : list of AMFI scheme codes
        profile_name   : investment profile
        benchmark_code : common benchmark (None = auto-detect per fund)

        Returns
        -------
        RankingTable
        """
        profile = get_investment_profile(profile_name)
        fund_entries = []

        for code in scheme_codes:
            try:
                entry = self._build_fund_entry(code, benchmark_code)
                if entry:
                    fund_entries.append(entry)
            except Exception as e:
                print(f"  ⚠️  Scheme {code}: {e}")

        if not fund_entries:
            raise ValueError("No funds could be analysed.")

        category = fund_entries[0].get("scheme_category", "Equity")
        return rank_funds(fund_entries, profile, category)

    # ────────────────────────────────────────
    # INTERNAL HELPERS
    # ────────────────────────────────────────

    def _build_fund_entry(
        self,
        scheme_code: int,
        benchmark_code: Optional[int] = None,
    ) -> Optional[Dict]:
        """Build a fund entry dict for the ranking engine."""
        fund_nav = self.fetcher.fetch(scheme_code)

        bench_code = benchmark_code or get_benchmark_code(
            fund_nav.scheme_info.scheme_category
        )
        benchmark_nav = None
        if bench_code:
            try:
                benchmark_nav = self.fetcher.fetch(bench_code)
            except FetchError:
                pass

        # Run analyses
        trailing = self._safe_run("Trailing", lambda: generate_trailing_report(fund_nav, benchmark_nav))
        rolling = self._safe_run("Rolling", lambda: generate_rolling_report(fund_nav, benchmark_nav, step_days=5))
        consistency = self._safe_run("Consistency", lambda: generate_consistency_report(fund_nav, benchmark_nav))
        sip = self._safe_run("SIP", lambda: generate_sip_report(fund_nav, benchmark_nav))
        risk_adj = self._safe_run("Risk", lambda: generate_risk_adjusted_report(fund_nav, benchmark_nav, 3))

        metrics = extract_metrics_from_reports(
            trailing, rolling, consistency, sip, risk_adj, fund_nav
        )

        return {
            "scheme_code": scheme_code,
            "scheme_name": fund_nav.scheme_info.scheme_name,
            "scheme_category": fund_nav.scheme_info.scheme_category,
            "metrics": metrics,
        }

    @staticmethod
    def _safe_run(label: str, func):
        """Run an analysis function with error handling."""
        try:
            return func()
        except Exception:
            return None

    @staticmethod
    def _build_summary(fund_nav, fund_score, trailing, rolling, risk_adj) -> List[str]:
        """Build a concise executive summary."""
        summary = []

        stars_str = "★" * fund_score.star_rating + "☆" * (5 - fund_score.star_rating)

        summary.append(f"{'═' * 60}")
        summary.append(f"EXECUTIVE SUMMARY")
        summary.append(f"{'═' * 60}")
        summary.append(f"Fund: {fund_nav.scheme_info.scheme_name}")
        summary.append(f"Rating: {stars_str}  {fund_score.final_score:.1f}/100  —  {fund_score.rating_label}")
        summary.append(f"Profile: {fund_score.profile.profile_name}")
        summary.append(f"History: {fund_nav.history_years} years ({fund_nav.total_trading_days} data points)")
        summary.append(f"")

        # Sub-scores
        summary.append(f"CATEGORY SCORES:")
        scores = [
            ("Performance", fund_score.performance_score),
            ("Risk-Adjusted", fund_score.risk_adjusted_score),
            ("Risk Management", fund_score.risk_management_score),
            ("Structural", fund_score.structural_score),
        ]
        for label, score in scores:
            bar_len = int(score / 100 * 30)
            bar = "█" * bar_len + "░" * (30 - bar_len)
            summary.append(f"  {label:<20} │{bar}│ {score:.1f}")

        # Penalties and bonuses
        if fund_score.bonuses:
            summary.append(f"\n✅ STRENGTHS:")
            for b in fund_score.bonuses:
                summary.append(f"   +{b.points} {b.label}: {b.reason}")

        if fund_score.penalties:
            summary.append(f"\n⚠️  CONCERNS:")
            for p in fund_score.penalties:
                summary.append(f"   {p.points} {p.label}: {p.reason}")

        summary.append(f"\n💡 RECOMMENDATION: {fund_score.recommendation}")
        summary.append(f"{'═' * 60}")

        return summary