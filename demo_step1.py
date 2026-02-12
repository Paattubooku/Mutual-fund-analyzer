#!/usr/bin/env python3
"""
demo_step1.py
─────────────
End-to-end demonstration of Step 1:
  • Fetch NAV data for a fund and its benchmark
  • Calculate trailing returns for all standard periods
  • Compare fund vs benchmark
  • Generate and display automated interpretation

Run:
    python demo_step1.py
"""

import sys

from data.fetcher import NAVFetcher, FetchError
from data.benchmarks import get_benchmark_code
from metrics.trailing_returns import generate_trailing_report
from utils.formatter import print_trailing_report


# ────────────────────────────────────────────────
# CONFIGURATION — change these to analyse any fund
# ────────────────────────────────────────────────

FUND_SCHEME_CODE      = 122639   # Parag Parikh Flexi Cap Fund - Direct Growth
BENCHMARK_SCHEME_CODE = None     # None → auto-detect from category


def main():
    fetcher = NAVFetcher()

    # ── 1. Fetch fund NAV data ──
    print("\n[1/4] Fetching fund NAV data...")
    try:
        fund_nav = fetcher.fetch(FUND_SCHEME_CODE)
    except FetchError as e:
        print(f"  ✗ Failed to fetch fund data: {e}")
        sys.exit(1)

    print(f"  ✓ {fund_nav.scheme_info.scheme_name}")
    print(f"    Category : {fund_nav.scheme_info.scheme_category}")
    print(f"    History  : {fund_nav.inception_date} → {fund_nav.latest_date} "
          f"({fund_nav.history_years} years, {fund_nav.total_trading_days} data points)")
    print(f"    Latest NAV: ₹{fund_nav.latest_nav:,.4f}")

    # ── 2. Resolve benchmark ──
    bench_code = BENCHMARK_SCHEME_CODE
    if bench_code is None:
        bench_code = get_benchmark_code(fund_nav.scheme_info.scheme_category)

    benchmark_nav = None
    if bench_code is not None:
        print(f"\n[2/4] Fetching benchmark NAV data (scheme {bench_code})...")
        try:
            benchmark_nav = fetcher.fetch(bench_code)
            print(f"  ✓ {benchmark_nav.scheme_info.scheme_name}")
            print(f"    History  : {benchmark_nav.inception_date} → "
                  f"{benchmark_nav.latest_date}")
        except FetchError as e:
            print(f"  ✗ Benchmark fetch failed: {e}")
            print("    → Proceeding without benchmark comparison.")
    else:
        print("\n[2/4] No benchmark mapping found — skipping comparison.")

    # ── 3. Generate report ──
    print(f"\n[3/4] Calculating trailing returns...")
    report = generate_trailing_report(
        fund_nav=fund_nav,
        benchmark_nav=benchmark_nav,
    )
    print(f"  ✓ {len(report.comparisons)} periods calculated")

    # ── 4. Display ──
    print(f"\n[4/4] Rendering report...\n")
    print_trailing_report(report)

    # ── Bonus: Scheme search demo ──
    print("─" * 80)
    print("   BONUS: Scheme Search Demo")
    print("─" * 80)
    query = "axis small cap direct"
    print(f"   Searching for: '{query}'")
    results = fetcher.search(query)
    for r in results[:5]:
        code = r.get("schemeCode", r.get("scheme_code", "?"))
        name = r.get("schemeName", r.get("scheme_name", "?"))
        print(f"     {code}  →  {name}")
    print()


if __name__ == "__main__":
    main()