#!/usr/bin/env python3
"""
demo_step4.py
─────────────
End-to-end demonstration of Step 4: SIP Returns (XIRR-Based)

  • XIRR for trailing SIP periods (1Y, 3Y, 5Y, 7Y, 10Y)
  • SIP vs Lump Sum head-to-head comparison
  • Rolling SIP XIRR distribution (start-date independence)
  • SIP date sensitivity (does the day of month matter?)
  • Full automated advisory interpretation

Run:
    python demo_step4.py
"""

import sys
import time

from data.fetcher import NAVFetcher, FetchError
from data.benchmarks import get_benchmark_code
from metrics.sip_returns import generate_sip_report
from utils.formatter import print_sip_report


# ────────────────────────────────────────────────
# CONFIGURATION
# ────────────────────────────────────────────────

FUND_SCHEME_CODE      = 122639   # Parag Parikh Flexi Cap Fund - Direct Growth
BENCHMARK_SCHEME_CODE = None     # None → auto-detect
SIP_AMOUNT            = 10_000   # ₹10,000 monthly
SIP_DAY               = 1       # 1st of every month


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

    # ── 3. Generate SIP report ──
    print(f"\n[3/4] Computing SIP analysis (₹{SIP_AMOUNT:,}/month on {SIP_DAY}th)...")
    t0 = time.time()

    try:
        report = generate_sip_report(
            fund_nav=fund_nav,
            benchmark_nav=benchmark_nav,
            monthly_amount=SIP_AMOUNT,
            sip_day=SIP_DAY,
        )
    except ValueError as e:
        print(f"  ✗ {e}")
        sys.exit(1)

    elapsed = time.time() - t0
    print(f"  ✓ {len(report.sip_results)} trailing SIP periods")
    print(f"  ✓ {len(report.lumpsum_comparisons)} SIP-vs-LumpSum comparisons")
    print(f"  ✓ {len(report.rolling_sip)} rolling SIP distributions")
    if report.date_sensitivity:
        print(f"  ✓ Date sensitivity across {len(report.date_sensitivity.day_results)} days")
    print(f"  ✓ Completed in {elapsed:.1f} seconds")

    # ── 4. Display ──
    print(f"\n[4/4] Rendering report...\n")
    print_sip_report(report)

    # ── Bonus: Single XIRR demo ──
    _xirr_demo()


def _xirr_demo():
    """Demonstrate the raw XIRR calculator with a manual example."""
    from metrics.sip_returns import calculate_xirr
    import datetime as dt

    print("=" * 90)
    print("   BONUS: RAW XIRR CALCULATION DEMO")
    print("=" * 90)
    print()
    print("   Scenario: 12 monthly SIPs of ₹10,000 + final redemption")
    print()

    # Simulate 12 monthly investments + final value
    cashflows = []
    start = dt.date(2023, 1, 1)

    for i in range(12):
        d = start + relativedelta(months=i)
        cashflows.append((d, -10000))   # outflow

    # Final value after 12 months
    final_date = start + relativedelta(months=12)
    final_value = 135000   # ₹1,35,000

    cashflows.append((final_date, final_value))

    print("   Cashflows:")
    for d, amt in cashflows:
        direction = "Invest" if amt < 0 else "Redeem"
        print(f"     {d}  {direction:>7}  ₹{abs(amt):>10,.0f}")

    xirr = calculate_xirr(cashflows)

    print()
    print(f"   Total Invested: ₹{12 * 10000:,.0f}")
    print(f"   Final Value:    ₹{final_value:,.0f}")
    print(f"   Absolute Return: {(final_value / 120000 - 1) * 100:.2f}%")
    print(f"   XIRR:           {xirr * 100:.2f}%" if xirr else "   XIRR: N/A")
    print()
    print("   Note: XIRR > Simple Return because earlier investments")
    print("   compound for longer. This is why XIRR is the correct")
    print("   measure for SIP returns, not simple CAGR.")
    print()


from dateutil.relativedelta import relativedelta

if __name__ == "__main__":
    main()