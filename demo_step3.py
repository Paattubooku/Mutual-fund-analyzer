#!/usr/bin/env python3
"""
demo_step3.py
─────────────
End-to-end demonstration of Step 3: Consistency of Outperformance

  • Calendar year returns (fund vs benchmark, every year)
  • Consistency score with grading
  • Up-Market / Down-Market Capture Ratios
  • Capture profile identification (Ideal/Aggressive/Defensive/Lagging)
  • Streak analysis (winning/losing streaks)
  • Full automated advisory-grade interpretation

Run:
    python demo_step3.py
"""

import sys

from data.fetcher import NAVFetcher, FetchError
from data.benchmarks import get_benchmark_code
from metrics.consistency import generate_consistency_report
from utils.formatter import print_consistency_report


# ────────────────────────────────────────────────
# CONFIGURATION
# ────────────────────────────────────────────────

FUND_SCHEME_CODE      = 122639   # Parag Parikh Flexi Cap Fund - Direct Growth
BENCHMARK_SCHEME_CODE = None     # None → auto-detect


def main():
    fetcher = NAVFetcher()

    # ── 1. Fetch fund ──
    print("\n[1/4] Fetching fund NAV data...")
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
        print(f"\n[2/4] Fetching benchmark (scheme {bench_code})...")
        try:
            benchmark_nav = fetcher.fetch(bench_code)
            print(f"  ✓ {benchmark_nav.scheme_info.scheme_name}")
        except FetchError as e:
            print(f"  ✗ {e} — proceeding without benchmark.")
    else:
        print("\n[2/4] No benchmark mapping found.")

    # ── 3. Generate report ──
    print(f"\n[3/4] Computing consistency analysis...")
    try:
        report = generate_consistency_report(
            fund_nav=fund_nav,
            benchmark_nav=benchmark_nav,
        )
    except ValueError as e:
        print(f"  ✗ {e}")
        sys.exit(1)

    summary_parts = []
    if report.calendar_year_analysis:
        cy = report.calendar_year_analysis
        summary_parts.append(
            f"{cy.total_years} calendar years analysed"
        )
    if report.capture_ratios:
        cr = report.capture_ratios
        summary_parts.append(
            f"Capture ratios from {cr.total_months} months"
        )
    print(f"  ✓ {' | '.join(summary_parts)}")

    # ── 4. Display ──
    print(f"\n[4/4] Rendering report...\n")
    print_consistency_report(report)

    # ── Bonus: Multi-fund comparison ──
    _multi_fund_demo(fetcher, benchmark_nav)


def _multi_fund_demo(fetcher: NAVFetcher, benchmark_nav):
    """Compare capture ratios across multiple funds."""

    print("=" * 90)
    print("   BONUS: CAPTURE RATIO COMPARISON ACROSS FUNDS")
    print("=" * 90)

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
            from metrics.consistency import calculate_capture_ratios
            cr = calculate_capture_ratios(nav, benchmark_nav, months=36)
            results.append((name, cr))
        except Exception as e:
            print(f"  ⚠️  {name}: {e}")

    if not results:
        return

    # ── Print comparison table ──
    print()
    header = (
        f"  {'Fund':<30} {'Up Cap':>8} {'Down Cap':>9} "
        f"{'CR':>6} {'Up Bat%':>8} {'Dn Bat%':>8} {'Profile':<12}"
    )
    print(header)
    print("  " + "─" * (len(header) - 2))

    for name, cr in results:
        up_high = cr.up_capture_ratio > 100
        down_low = cr.down_capture_ratio < 100
        profile_map = {
            (True, True): "★ IDEAL",
            (True, False): "AGGRESSIVE",
            (False, True): "DEFENSIVE",
            (False, False): "✗ LAGGING",
        }
        profile = profile_map.get((up_high, down_low), "?")

        print(
            f"  {name:<30} "
            f"{cr.up_capture_ratio:>7.1f}% "
            f"{cr.down_capture_ratio:>8.1f}% "
            f"{cr.capture_ratio:>5.2f} "
            f"{cr.up_month_batting_avg_pct:>7.1f}% "
            f"{cr.down_month_batting_avg_pct:>7.1f}% "
            f"{profile:<12}"
        )

    print()


if __name__ == "__main__":
    main()