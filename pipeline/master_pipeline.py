"""
pipeline/master_pipeline.py
───────────────────────────
The one-call master pipeline with:
  • Structured warning collection (not silent swallowing)
  • Category validation for multi-fund comparison
  • Offline fixture fallback
  • Graceful degradation with diagnostics
"""

from __future__ import annotations

from typing import Optional, List, Dict

from data.fetcher import NAVFetcher, FetchError
from data.benchmarks import get_benchmark_code
from data.models import MasterReport, AnalysisWarning

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
    FundScore,
    RankingTable,
)

from utils.logger import get_logger

log = get_logger(__name__)


class MasterPipeline:
    """Orchestrates the complete analysis pipeline."""

    def __init__(self, offline_mode: bool = False):
        self.fetcher = NAVFetcher(offline_mode=offline_mode)

    def analyse_fund(
        self,
        scheme_code: int,
        benchmark_code: Optional[int] = None,
        profile_name: str = "growth",
        sip_amount: float = 10000,
    ) -> MasterReport:
        """Run the complete analysis pipeline for a single fund."""
        profile = get_investment_profile(profile_name)
        warnings: List[AnalysisWarning] = []

        fund_nav = self.fetcher.fetch(scheme_code)

        benchmark_nav = None
        if benchmark_code is None:
            benchmark_code = get_benchmark_code(fund_nav.scheme_info.scheme_category)
        if benchmark_code:
            try:
                benchmark_nav = self.fetcher.fetch(benchmark_code)
            except FetchError as e:
                warnings.append(AnalysisWarning(
                    section="Benchmark Fetch",
                    severity="WARNING",
                    message=f"Could not fetch benchmark (scheme {benchmark_code})",
                    exception_type=type(e).__name__,
                    exception_detail=str(e),
                ))
        else:
            warnings.append(AnalysisWarning(
                section="Benchmark Mapping",
                severity="INFO",
                message=(
                    f"No benchmark mapping for category '{fund_nav.scheme_info.scheme_category}'. "
                    f"Comparison metrics will be unavailable."
                ),
            ))

        trailing = self._safe_run("Trailing Returns", warnings,
            lambda: generate_trailing_report(fund_nav, benchmark_nav))
        rolling = self._safe_run("Rolling Returns", warnings,
            lambda: generate_rolling_report(fund_nav, benchmark_nav, step_days=5))
        consistency = self._safe_run("Consistency", warnings,
            lambda: generate_consistency_report(fund_nav, benchmark_nav))
        sip = self._safe_run("SIP Returns", warnings,
            lambda: generate_sip_report(fund_nav, benchmark_nav, sip_amount))
        risk_adj = self._safe_run("Risk-Adjusted", warnings,
            lambda: generate_risk_adjusted_report(fund_nav, benchmark_nav, period_years=3))

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

        summary = self._build_summary(fund_nav, fund_score, warnings)

        return MasterReport(
            scheme_info=fund_nav.scheme_info,
            as_of_date=fund_nav.latest_date,
            trailing_returns=trailing,
            rolling_returns=rolling,
            consistency=consistency,
            sip_returns=sip,
            risk_adjusted=risk_adj,
            fund_score=fund_score,
            warnings=warnings,
            summary=summary,
        )

    def compare_funds(
        self,
        scheme_codes: List[int],
        profile_name: str = "growth",
        benchmark_code: Optional[int] = None,
    ) -> RankingTable:
        """Analyse and rank multiple funds with peer-relative scoring."""
        profile = get_investment_profile(profile_name)
        fund_entries = []
        categories_seen: Dict[str, int] = {}

        for code in scheme_codes:
            try:
                entry = self._build_fund_entry(code, benchmark_code)
                if entry:
                    fund_entries.append(entry)
                    cat = entry.get("scheme_category", "Unknown")
                    categories_seen[cat] = categories_seen.get(cat, 0) + 1
            except Exception as e:
                log.warning("Scheme %d skipped: %s", code, e)

        if not fund_entries:
            raise ValueError("No funds could be analysed.")

        if len(categories_seen) > 1:
            cat_summary = ", ".join(f"{cat} ({n})" for cat, n in categories_seen.items())
            log.warning(
                "MIXED CATEGORIES detected in comparison: %s. Peer-relative scoring may be less meaningful. For best results, compare funds within the same category.",
                cat_summary,
            )
            primary_category = max(categories_seen, key=categories_seen.get)
        else:
            primary_category = next(iter(categories_seen))

        ranking = rank_funds(fund_entries, profile, primary_category)

        if len(categories_seen) > 1:
            cat_warning = (
                f"⚠️  MIXED CATEGORIES: {', '.join(categories_seen.keys())}. "
                f"Cross-category comparison should be interpreted with caution."
            )
            ranking.interpretation.insert(0, cat_warning)
            ranking.interpretation.insert(1, "")

        return ranking

    def _build_fund_entry(
        self,
        scheme_code: int,
        benchmark_code: Optional[int] = None,
    ) -> Optional[Dict]:
        """Build a fund entry dict for the ranking engine."""
        warnings: List[AnalysisWarning] = []

        fund_nav = self.fetcher.fetch(scheme_code)
        bench_code = benchmark_code or get_benchmark_code(fund_nav.scheme_info.scheme_category)
        benchmark_nav = None
        if bench_code:
            try:
                benchmark_nav = self.fetcher.fetch(bench_code)
            except FetchError:
                pass

        trailing = self._safe_run("Trailing", warnings, lambda: generate_trailing_report(fund_nav, benchmark_nav))
        rolling = self._safe_run("Rolling", warnings, lambda: generate_rolling_report(fund_nav, benchmark_nav, step_days=5))
        consistency = self._safe_run("Consistency", warnings, lambda: generate_consistency_report(fund_nav, benchmark_nav))
        sip = self._safe_run("SIP", warnings, lambda: generate_sip_report(fund_nav, benchmark_nav))
        risk_adj = self._safe_run("Risk", warnings, lambda: generate_risk_adjusted_report(fund_nav, benchmark_nav, 3))

        metrics = extract_metrics_from_reports(trailing, rolling, consistency, sip, risk_adj, fund_nav)

        if warnings:
            log.info("Scheme %d (%s): %d analysis warnings", scheme_code, fund_nav.scheme_info.scheme_name, len(warnings))

        return {
            "scheme_code": scheme_code,
            "scheme_name": fund_nav.scheme_info.scheme_name,
            "scheme_category": fund_nav.scheme_info.scheme_category,
            "metrics": metrics,
            "warnings": warnings,
        }

    @staticmethod
    def _safe_run(label: str, warnings: List[AnalysisWarning], func):
        """Run an analysis function with error collection."""
        try:
            return func()
        except Exception as exc:
            log.warning("%s analysis failed: %s: %s", label, type(exc).__name__, exc)
            warnings.append(AnalysisWarning(
                section=label,
                severity="ERROR",
                message=f"{label} analysis could not be completed",
                exception_type=type(exc).__name__,
                exception_detail=str(exc),
            ))
            return None

    @staticmethod
    def _build_summary(fund_nav, fund_score: FundScore, warnings: List[AnalysisWarning]) -> List[str]:
        """Build a concise executive summary."""
        summary = []
        stars_str = "★" * fund_score.star_rating + "☆" * (5 - fund_score.star_rating)

        summary.append(f"{'═' * 60}")
        summary.append("EXECUTIVE SUMMARY")
        summary.append(f"{'═' * 60}")
        summary.append(f"Fund: {fund_nav.scheme_info.scheme_name}")
        summary.append(f"Rating: {stars_str}  {fund_score.final_score:.1f}/100  —  {fund_score.rating_label}")
        summary.append(f"Profile: {fund_score.profile.profile_name}")
        summary.append(f"History: {fund_nav.history_years} years ({fund_nav.total_trading_days} data points)")
        summary.append("")

        summary.append("CATEGORY SCORES:")
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

        if fund_score.bonuses:
            summary.append("\n✅ STRENGTHS:")
            for b in fund_score.bonuses:
                summary.append(f"   +{b.points} {b.label}: {b.reason}")

        if fund_score.penalties:
            summary.append("\n⚠️  CONCERNS:")
            for p in fund_score.penalties:
                summary.append(f"   {p.points} {p.label}: {p.reason}")

        error_warnings = [w for w in warnings if w.severity == "ERROR"]
        if error_warnings:
            summary.append(f"\n🔧 ANALYSIS GAPS ({len(error_warnings)}):")
            for w in error_warnings:
                summary.append(f"   • {w.section}: {w.exception_detail}")
            summary.append("   Some metrics could not be computed. Score is based on available data only.")

        summary.append(f"\n💡 RECOMMENDATION: {fund_score.recommendation}")
        summary.append(f"{'═' * 60}")
        return summary
