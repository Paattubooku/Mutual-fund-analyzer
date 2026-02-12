#!/usr/bin/env python3
"""
demo_step5.py
─────────────
End-to-end demonstration of Step 5: Risk-Adjusted Return Ratios

  • Standard Deviation & Downside Deviation
  • Beta, R², Tracking Error (regression analysis)
  • Jensen's Alpha, Sharpe, Sortino, Treynor, Information Ratio
  • Multi-period stability analysis
  • Full automated advisory interpretation

Run:
    python demo_step5.py
"""

import sys
import time

from data.fetcher import NAVFetcher, FetchError
from data.benchmarks import get_benchmark_code
from metrics.risk_adjusted import (
    generate_risk_adjusted_report,
    calculate_multi_period_ratios,
)
from utils.formatter import print_risk_adjusted_report


# ────────────────────────────────────────────────
# CONFIGURATION
# ────────────────────────────────────────────────

FUND_SCHEME_CODE      = 122639   # Parag Parikh Flexi Cap Fund - Direct Growth
BENCHMARK_SCHEME_CODE = None     # None → auto-detect
ANALYSIS_PERIOD       = 3        # Primary analysis: 3 years


def main():
    fetcher = NAVFetcher()

    # ── 1. Fetch fund ──
    print("\n[1/5] Fetching fund NAV data...")
    try:
        fund_nav = fetcher.fetch(FUND_SCHEME_CODE)
    except FetchError as e:
        print(f"  ✗ Failed: {e}")
        sys.exit(1)

    print(f"  ✓ {fund_nav.scheme_info.scheme_name}")
    print(f"    History: {fund_nav.inception_date} → {fund_nav.latest_date} "
          f"({fund_nav.history_years} yrs)")

    # ── 2. Fetch benchmark ──
    bench_code = BENCHMARK_SCHEME_CODE or get_benchmark_code(
        fund_nav.scheme_info.scheme_category
    )

    benchmark_nav = None
    if bench_code:
        print(f"\n[2/5] Fetching benchmark (scheme {bench_code})...")
        try:
            benchmark_nav = fetcher.fetch(bench_code)
            print(f"  ✓ {benchmark_nav.scheme_info.scheme_name}")
        except FetchError as e:
            print(f"  ✗ {e}")

    # ── 3. Primary analysis ──
    print(f"\n[3/5] Computing risk-adjusted analysis ({ANALYSIS_PERIOD}Y window)...")
    t0 = time.time()

    try:
        report = generate_risk_adjusted_report(
            fund_nav=fund_nav,
            benchmark_nav=benchmark_nav,
            period_years=ANALYSIS_PERIOD,
        )
    except ValueError as e:
        print(f"  ✗ {e}")
        sys.exit(1)

    elapsed = time.time() - t0
    print(f"  ✓ Completed in {elapsed:.2f} seconds")

    # ── 4. Display primary report ──
    print(f"\n[4/5] Rendering primary report...\n")
    print_risk_adjusted_report(report)

    # ── 5. Multi-period comparison ──
    print(f"[5/5] Multi-period ratio comparison...\n")
    _print_multi_period(fund_nav, benchmark_nav)

    # ── Bonus: Multi-fund comparison ──
    _multi_fund_comparison(fetcher, benchmark_nav)


def _print_multi_period(fund_nav, benchmark_nav):
    """Compare ratios across 1Y, 3Y, 5Y periods."""

    try:
        multi = calculate_multi_period_ratios(
            fund_nav, benchmark_nav, periods=[1.0, 3.0, 5.0]
        )
    except ValueError:
        print("  ✗ Insufficient data for multi-period analysis.")
        return

    if not multi:
        return

    print("=" * 90)
    print("   MULTI-PERIOD RATIO COMPARISON")
    print("=" * 90)
    print()

    # Header
    header = (
        f"  {'Period':>7} │ {'Return':>8} │ {'StdDev':>8} │ "
        f"{'Sharpe':>8} │ {'Sortino':>8} │ "
        f"{'Alpha':>8} │ {'Beta':>6} │ {'IR':>8}"
    )
    print(header)
    print("  " + "─" * (len(header) - 2))

    for period, ratios, beta_a, vol in multi:
        alpha_str = (
            f"{ratios.jensens_alpha_pct:+.2f}%"
            if ratios.jensens_alpha_pct is not None
            else "N/A"
        )
        beta_str = (
            f"{ratios.beta:.2f}" if ratios.beta is not None else "N/A"
        )
        ir_str = (
            f"{ratios.information_ratio:.3f}"
            if ratios.information_ratio is not None
            else "N/A"
        )

        print(
            f"  {period:>5.0f}Y  │ "
            f"{ratios.fund_return_pct:>+7.2f}% │ "
            f"{ratios.std_dev_pct:>7.2f}% │ "
            f"{ratios.sharpe_ratio:>8.4f} │ "
            f"{ratios.sortino_ratio:>8.4f} │ "
            f"{alpha_str:>8} │ "
            f"{beta_str:>6} │ "
            f"{ir_str:>8}"
        )

    print()

    # Trend analysis
    if len(multi) >= 2:
        sharpe_vals = [r.sharpe_ratio for _, r, _, _ in multi]
        if sharpe_vals[-1] > sharpe_vals[0]:
            print("  ✅  Sharpe Ratio IMPROVING over longer periods — good sign.")
        elif sharpe_vals[-1] < sharpe_vals[0] * 0.7:
            print("  ⚠️   Sharpe Ratio DECLINING over longer periods — recent performance weaker.")
        else:
            print("  📊  Sharpe Ratio relatively STABLE across periods.")
    print()


def _multi_fund_comparison(fetcher, benchmark_nav):
    """Compare risk-adjusted ratios across multiple funds."""
    from metrics.risk_adjusted import calculate_risk_adjusted_ratios, calculate_beta

    print("=" * 90)
    print("   BONUS: MULTI-FUND RISK-ADJUSTED COMPARISON (3Y)")
    print("=" * 90)
    print()

    fund_codes = {
        "Parag Parikh Flexi Cap":    122639,
        "Axis Bluechip":             120503,
        "Mirae Asset Large Cap":     118834,
        "SBI Small Cap":             125497,
    }

    if benchmark_nav is None:
        print("  (Skipped — no benchmark available)")
        return

    results = []

    for name, code in fund_codes.items():
        try:
            nav = fetcher.fetch(code)
            ratios = calculate_risk_adjusted_ratios(nav, benchmark_nav, 3)
            results.append((name, ratios))
        except Exception as e:
            print(f"  ⚠️  {name}: {e}")

    if not results:
        return

    # Header
    header = (
        f"  {'Fund':<28} │ {'Return':>8} │ {'σ':>7} │ "
        f"{'Sharpe':>7} │ {'Sortino':>8} │ "
        f"{'Alpha':>8} │ {'β':>5} │ {'IR':>7} │ {'Grade':<12}"
    )
    print(header)
    print("  " + "─" * (len(header) - 2))

    for name, r in results:
        alpha_str = (
            f"{r.jensens_alpha_pct:+.2f}%"
            if r.jensens_alpha_pct is not None else "N/A"
        )
        beta_str = f"{r.beta:.2f}" if r.beta is not None else "N/A"
        ir_str = (
            f"{r.information_ratio:.3f}"
            if r.information_ratio is not None else "N/A"
        )

        # Overall grade from Sharpe
        grade = r.sharpe_grade

        print(
            f"  {name:<28} │ "
            f"{r.fund_return_pct:>+7.2f}% │ "
            f"{r.std_dev_pct:>6.2f}% │ "
            f"{r.sharpe_ratio:>7.3f} │ "
            f"{r.sortino_ratio:>8.3f} │ "
            f"{alpha_str:>8} │ "
            f"{beta_str:>5} │ "
            f"{ir_str:>7} │ "
            f"{grade:<12}"
        )

    # Find the best
    best_sharpe = max(results, key=lambda x: x[1].sharpe_ratio)
    best_sortino = max(results, key=lambda x: x[1].sortino_ratio)

    print()
    print(f"  🏆  Best Sharpe:  {best_sharpe[0]} ({best_sharpe[1].sharpe_ratio:.3f})")
    print(f"  🏆  Best Sortino: {best_sortino[0]} ({best_sortino[1].sortino_ratio:.3f})")

    if best_sharpe[0] != best_sortino[0]:
        print(
            f"\n  📊  Sharpe and Sortino disagree! "
            f"{best_sortino[0]} has better downside management, "
            f"while {best_sharpe[0]} has better overall risk-return."
        )
    print()


if __name__ == "__main__":
    main()