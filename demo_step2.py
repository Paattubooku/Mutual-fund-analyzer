#!/usr/bin/env python3
"""
demo_step2.py
─────────────
End-to-end demonstration of Step 2: Rolling Returns

  • Fetch NAV data for fund + benchmark
  • Calculate rolling returns for 1Y, 3Y, 5Y, 7Y, 10Y windows
  • Compare vs benchmark (win rate, excess return distribution)
  • Generate full distribution statistics
  • Display automated advisory-grade interpretation

Run:
    python demo_step2.py
"""

import sys
import time

from data.fetcher import NAVFetcher, FetchError
from data.benchmarks import get_benchmark_code
from metrics.rolling_returns import generate_rolling_report
from utils.formatter import print_rolling_report


# ────────────────────────────────────────────────
# CONFIGURATION
# ────────────────────────────────────────────────

FUND_SCHEME_CODE      = 122639   # Parag Parikh Flexi Cap Fund - Direct Growth
BENCHMARK_SCHEME_CODE = None     # None → auto-detect from category

# Step size: 1 = daily rolling (most thorough, ~2-3 sec)
#            5 = weekly rolling (faster, still comprehensive)
#           21 = monthly rolling (fastest, fewer observations)
STEP_DAYS = 1


def main():
    fetcher = NAVFetcher()

    # ── 1. Fetch fund data ──
    print("\n[1/4] Fetching fund NAV data...")
    try:
        fund_nav = fetcher.fetch(FUND_SCHEME_CODE)
    except FetchError as e:
        print(f"  ✗ Failed: {e}")
        sys.exit(1)

    print(f"  ✓ {fund_nav.scheme_info.scheme_name}")
    print(f"    History: {fund_nav.inception_date} → {fund_nav.latest_date} "
          f"({fund_nav.history_years} yrs, {fund_nav.total_trading_days} points)")

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

    # ── 3. Generate rolling report ──
    print(f"\n[3/4] Computing rolling returns (step={STEP_DAYS} day(s))...")
    t0 = time.time()

    try:
        report = generate_rolling_report(
            fund_nav=fund_nav,
            benchmark_nav=benchmark_nav,
            step_days=STEP_DAYS,
        )
    except ValueError as e:
        print(f"  ✗ {e}")
        sys.exit(1)

    elapsed = time.time() - t0
    total_obs = sum(d.num_observations for d in report.distributions)

    print(f"  ✓ {len(report.distributions)} windows computed")
    print(f"  ✓ {total_obs:,} total rolling observations")
    print(f"  ✓ Completed in {elapsed:.2f} seconds")

    # ── 4. Display ──
    print(f"\n[4/4] Rendering report...\n")
    print_rolling_report(report)

    # ── Bonus: Quick summary table ──
    _print_quick_summary(report)


def _print_quick_summary(report):
    """Print a compact comparison table across all windows."""

    print("=" * 90)
    print("   QUICK COMPARISON ACROSS ALL ROLLING WINDOWS")
    print("=" * 90)

    has_bench = report.benchmark_info is not None

    # Header
    if has_bench:
        header = (
            f"  {'Window':<12} {'Obs':>6} {'Mean':>8} {'Median':>8} "
            f"{'Min':>8} {'Max':>8} {'StdDev':>8} {'Win%':>7} {'Pos%':>7}"
        )
    else:
        header = (
            f"  {'Window':<12} {'Obs':>6} {'Mean':>8} {'Median':>8} "
            f"{'Min':>8} {'Max':>8} {'StdDev':>8} {'Pos%':>7}"
        )
    print(header)
    print("  " + "─" * (len(header) - 2))

    for d in report.distributions:
        if has_bench:
            line = (
                f"  {d.window_label:<12} {d.num_observations:>6,} "
                f"{d.mean_return_pct:>+7.2f}% {d.median_return_pct:>+7.2f}% "
                f"{d.min_return_pct:>+7.2f}% {d.max_return_pct:>+7.2f}% "
                f"{d.std_dev_pct:>7.2f}% "
                f"{d.win_rate_vs_benchmark_pct:>6.1f}% "
                f"{d.positive_return_pct:>6.1f}%"
            )
        else:
            line = (
                f"  {d.window_label:<12} {d.num_observations:>6,} "
                f"{d.mean_return_pct:>+7.2f}% {d.median_return_pct:>+7.2f}% "
                f"{d.min_return_pct:>+7.2f}% {d.max_return_pct:>+7.2f}% "
                f"{d.std_dev_pct:>7.2f}% "
                f"{d.positive_return_pct:>6.1f}%"
            )
        print(line)

    print()


if __name__ == "__main__":
    main()