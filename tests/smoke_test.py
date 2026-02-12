#!/usr/bin/env python3
"""
tests/smoke_test.py
───────────────────
Offline smoke test suite that validates every analysis module
using synthetic fixture data.  Zero network dependency.
"""

import sys
import os
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.fixtures import generate_synthetic_nav, get_fixture_benchmark_code


def _header(title: str):
    print(f"\n{'─' * 70}")
    print(f"  {title}")
    print(f"{'─' * 70}")


def _pass(label: str, detail: str = ""):
    extra = f" — {detail}" if detail else ""
    print(f"  ✅ {label}{extra}")


def _fail(label: str, error: Exception):
    print(f"  ❌ {label}")
    print(f"     {type(error).__name__}: {error}")
    return 1


def test_fixtures():
    _header("FIXTURE GENERATION")
    failures = 0

    try:
        nav = generate_synthetic_nav(100001, years=5)
        assert nav.total_trading_days > 1000, f"Expected >1000 points, got {nav.total_trading_days}"
        assert nav.history_years > 4.5, f"Expected >4.5y, got {nav.history_years}"
        _pass("5-year fixture", f"{nav.total_trading_days} points, {nav.history_years}y")
    except Exception as e:
        failures += _fail("5-year fixture", e)

    try:
        nav_short = generate_synthetic_nav(100002, years=0.5)
        assert nav_short.total_trading_days > 100
        _pass("6-month fixture", f"{nav_short.total_trading_days} points")
    except Exception as e:
        failures += _fail("6-month fixture", e)

    try:
        nav_bench = generate_synthetic_nav(get_fixture_benchmark_code(), years=5)
        _pass("Benchmark fixture", f"{nav_bench.total_trading_days} points")
    except Exception as e:
        failures += _fail("Benchmark fixture", e)

    return failures


def test_trailing_returns():
    _header("TRAILING RETURNS (Section 1.1)")
    failures = 0

    from metrics.trailing_returns import generate_trailing_report

    nav = generate_synthetic_nav(100001, years=5)
    bench = generate_synthetic_nav(get_fixture_benchmark_code(), years=5)

    try:
        report = generate_trailing_report(nav)
        assert len(report.comparisons) > 0
        _pass("Fund-only", f"{len(report.comparisons)} periods")
    except Exception as e:
        failures += _fail("Fund-only", e)

    try:
        report = generate_trailing_report(nav, bench)
        beat_count = sum(1 for c in report.comparisons if c.beat_benchmark is not None)
        _pass("With benchmark", f"{beat_count} comparable periods")
    except Exception as e:
        failures += _fail("With benchmark", e)

    try:
        nav_short = generate_synthetic_nav(100002, years=0.5)
        report = generate_trailing_report(nav_short)
        _pass("Short history (6mo)", f"{len(report.comparisons)} periods (sub-year only)")
    except Exception as e:
        failures += _fail("Short history (6mo)", e)

    return failures


def test_rolling_returns():
    _header("ROLLING RETURNS (Section 1.2)")
    failures = 0

    from metrics.rolling_returns import generate_rolling_report

    nav = generate_synthetic_nav(100001, years=5)
    bench = generate_synthetic_nav(get_fixture_benchmark_code(), years=5)

    try:
        report = generate_rolling_report(nav, bench, step_days=5)
        total_obs = sum(d.num_observations for d in report.distributions)
        _pass("5-year data", f"{len(report.distributions)} windows, {total_obs} total obs")
    except Exception as e:
        failures += _fail("5-year data", e)

    try:
        nav_short = generate_synthetic_nav(100002, years=0.5)
        generate_rolling_report(nav_short, step_days=5)
        _fail("0.5y data should have raised", ValueError("Expected failure"))
        failures += 1
    except ValueError as e:
        _pass("Short history raises ValueError", str(e)[:60])
    except Exception as e:
        failures += _fail("Short history unexpected error", e)

    return failures


def test_consistency():
    _header("CONSISTENCY (Section 1.3)")
    failures = 0

    from metrics.consistency import generate_consistency_report

    nav = generate_synthetic_nav(100001, years=5)
    bench = generate_synthetic_nav(get_fixture_benchmark_code(), years=5)

    try:
        report = generate_consistency_report(nav, bench)
        cy = report.calendar_year_analysis
        cr = report.capture_ratios
        details = []
        if cy:
            details.append(f"{cy.total_years} cal years")
        if cr:
            details.append(f"CR={cr.capture_ratio:.2f}")
        _pass("Full analysis", ", ".join(details) if details else "OK")
    except Exception as e:
        failures += _fail("Full analysis", e)

    return failures


def test_sip_returns():
    _header("SIP RETURNS (Section 1.4)")
    failures = 0

    from metrics.sip_returns import generate_sip_report, calculate_xirr

    try:
        cashflows = [
            (dt.date(2023, 1, 1), -10000),
            (dt.date(2023, 2, 1), -10000),
            (dt.date(2023, 3, 1), -10000),
            (dt.date(2023, 4, 1), -10000),
            (dt.date(2023, 5, 1), -10000),
            (dt.date(2023, 6, 1), -10000),
            (dt.date(2023, 7, 1), 62000),
        ]
        xirr = calculate_xirr(cashflows)
        assert xirr is not None, "XIRR returned None"
        _pass("XIRR solver", f"XIRR = {xirr*100:.2f}%")
    except Exception as e:
        failures += _fail("XIRR solver", e)

    nav = generate_synthetic_nav(100001, years=5)

    try:
        report = generate_sip_report(nav, monthly_amount=10000)
        _pass("SIP report (no bench)", f"{len(report.sip_results)} periods")
    except Exception as e:
        failures += _fail("SIP report (no bench)", e)

    return failures


def test_risk_adjusted():
    _header("RISK-ADJUSTED RATIOS (Section 2)")
    failures = 0

    from metrics.risk_adjusted import generate_risk_adjusted_report

    nav = generate_synthetic_nav(100001, years=5)
    bench = generate_synthetic_nav(get_fixture_benchmark_code(), years=5)

    try:
        report = generate_risk_adjusted_report(nav, bench, period_years=3)
        r = report.ratios
        _pass("3Y ratios", f"Sharpe={r.sharpe_ratio:.3f}, Sortino={r.sortino_ratio:.3f}, α={r.jensens_alpha_pct}%")
    except Exception as e:
        failures += _fail("3Y ratios", e)

    try:
        nav_short = generate_synthetic_nav(100002, years=0.7)
        report = generate_risk_adjusted_report(nav_short, period_years=None)
        _pass("Short history (auto period)", f"σ={report.volatility.annualised_std_dev_pct:.1f}%")
    except ValueError as e:
        if "months" in str(e).lower():
            _pass("Short history correctly rejected", str(e)[:60])
        else:
            failures += _fail("Short history unexpected rejection", e)
    except Exception as e:
        failures += _fail("Short history", e)

    return failures


def test_scoring():
    _header("SCORING ENGINE (Section 7)")
    failures = 0

    from metrics.scoring_engine import score_fund, rank_funds, get_investment_profile

    try:
        metrics = {
            "cagr_3y": 15.0,
            "sharpe_3y": 0.8,
            "sortino_3y": 1.2,
            "std_dev_3y": 14.0,
            "max_drawdown": -22.0,
            "fund_age_years": 5.0,
        }
        profile = get_investment_profile("growth")
        score = score_fund(metrics, profile, scheme_name="Test Fund")
        assert 0 <= score.final_score <= 100
        _pass("Single fund scoring", f"Score={score.final_score:.1f}, Stars={score.star_rating}")
    except Exception as e:
        failures += _fail("Single fund scoring", e)

    try:
        entries = [
            {"scheme_code": 1, "scheme_name": "Fund A", "scheme_category": "Equity", "metrics": {"cagr_3y": 18, "sharpe_3y": 0.9, "fund_age_years": 8, "max_drawdown": -20}},
            {"scheme_code": 2, "scheme_name": "Fund B", "scheme_category": "Equity", "metrics": {"cagr_3y": 12, "sharpe_3y": 0.5, "fund_age_years": 5, "max_drawdown": -30}},
            {"scheme_code": 3, "scheme_name": "Fund C", "scheme_category": "Equity", "metrics": {"cagr_3y": 20, "sharpe_3y": 0.4, "fund_age_years": 3, "max_drawdown": -45}},
        ]
        profile = get_investment_profile("growth")
        ranking = rank_funds(entries, profile)
        assert len(ranking.fund_scores) == 3
        assert ranking.fund_scores[0].final_score >= ranking.fund_scores[-1].final_score
        _pass("Multi-fund ranking", f"#1: {ranking.fund_scores[0].scheme_name}")
    except Exception as e:
        failures += _fail("Multi-fund ranking", e)

    try:
        score = score_fund({}, get_investment_profile("growth"), scheme_name="Empty Fund")
        _pass("Empty metrics handled", f"Score={score.final_score:.1f}")
    except Exception as e:
        failures += _fail("Empty metrics", e)

    return failures


def test_pipeline():
    _header("MASTER PIPELINE (Offline)")
    failures = 0

    from pipeline.master_pipeline import MasterPipeline

    pipeline = MasterPipeline(offline_mode=True)

    try:
        report = pipeline.analyse_fund(100001)
        error_count = sum(1 for w in report.warnings if w.severity == "ERROR")
        _pass("analyse_fund (fixture)", f"Score={report.fund_score.final_score:.1f}, Warnings={len(report.warnings)} ({error_count} errors)")
    except Exception as e:
        failures += _fail("analyse_fund (fixture)", e)

    try:
        ranking = pipeline.compare_funds([100001, 100002, 100003])
        _pass("compare_funds (3 fixtures)", f"#1: {ranking.fund_scores[0].scheme_name} ({ranking.fund_scores[0].final_score:.1f})")
    except Exception as e:
        failures += _fail("compare_funds (fixtures)", e)

    return failures


def main():
    print()
    print("█" * 70)
    print("█" + "  MUTUAL FUND ANALYZER — OFFLINE SMOKE TEST SUITE".center(68) + "█")
    print("█" * 70)

    total_failures = 0
    tests = [
        test_fixtures,
        test_trailing_returns,
        test_rolling_returns,
        test_consistency,
        test_sip_returns,
        test_risk_adjusted,
        test_scoring,
        test_pipeline,
    ]

    for test_fn in tests:
        try:
            total_failures += test_fn()
        except Exception as e:
            print(f"\n  💥 TEST SUITE CRASHED: {type(e).__name__}: {e}")
            total_failures += 1

    print(f"\n{'═' * 70}")
    if total_failures == 0:
        print("  🏆 ALL TESTS PASSED")
    else:
        print(f"  ❌ {total_failures} FAILURE(S)")
    print(f"{'═' * 70}\n")

    return total_failures


if __name__ == "__main__":
    sys.exit(main())
