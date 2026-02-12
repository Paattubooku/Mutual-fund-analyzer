#!/usr/bin/env python3
"""
demo_step7.py
─────────────
End-to-end demonstration of Step 7: Structural & Qualitative Analysis

  • Expense Ratio with 20-year cost simulation
  • Portfolio Turnover with hidden cost estimation
  • Fund Manager tenure and stability assessment
  • AUM size-strategy compatibility with trend
  • Exit load structure
  • Fund house pedigree
  • Overall structural quality score

Run:
    python demo_step7.py
"""

import sys

from data.fund_metadata_provider import (
    get_fund_metadata,
    get_sample_metadata_ppfas,
    get_sample_metadata_axis_bluechip,
    get_sample_metadata_sbi_smallcap,
)
from metrics.structural_analysis import generate_structural_report
from utils.formatter import print_structural_report


# ────────────────────────────────────────────────
# CONFIGURATION
# ────────────────────────────────────────────────

FUND_CODES = [122639, 120503, 125497]


def main():
    print("\n" + "=" * 90)
    print("   STRUCTURAL & QUALITATIVE ANALYSIS — MULTI-FUND DEMO")
    print("=" * 90)

    reports = []

    for code in FUND_CODES:
        metadata = get_fund_metadata(code)
        if metadata is None:
            print(f"\n  ⚠️  No metadata available for scheme {code}")
            continue

        print(f"\n[{len(reports) + 1}] Analysing: {metadata['scheme_name']}...")
        report = generate_structural_report(metadata)
        reports.append(report)

        print(f"  ✓ Score: {report.structural_score:.1f}/100 — {report.structural_grade}")

    # ── Display detailed report for primary fund ──
    if reports:
        print(f"\n{'=' * 90}")
        print(f"   DETAILED REPORT: {reports[0].scheme_name}")
        print(f"{'=' * 90}")
        print_structural_report(reports[0])

    # ── Multi-fund comparison table ──
    if len(reports) >= 2:
        _print_multi_fund_structural(reports)

    # ── Cost comparison ──
    if reports:
        _print_cost_comparison(reports)


def _print_multi_fund_structural(reports):
    """Print multi-fund structural comparison table."""
    print("=" * 90)
    print("   MULTI-FUND STRUCTURAL COMPARISON")
    print("=" * 90)
    print()

    header = (
        f"  {'Fund':<35} │ {'TER':>6} │ {'Turn.':>6} │ "
        f"{'Mgr Tenure':>10} │ {'AUM (Cr)':>10} │ {'Score':>6} │ {'Grade':<10}"
    )
    print(header)
    print("  " + "─" * (len(header) - 2))

    for r in reports:
        name = r.scheme_name[:35]

        ter = f"{r.expense_analysis.current_direct_pct:.2f}%" if r.expense_analysis and r.expense_analysis.current_direct_pct else "N/A"
        turnover = f"{r.turnover_analysis.turnover_ratio_pct:.0f}%" if r.turnover_analysis else "N/A"
        tenure = f"{r.manager_analysis.current_tenure_years:.1f}y" if r.manager_analysis and r.manager_analysis.current_tenure_years else "N/A"
        aum = f"₹{r.aum_analysis.current_aum_cr:,.0f}" if r.aum_analysis and r.aum_analysis.current_aum_cr else "N/A"
        score = f"{r.structural_score:.1f}" if r.structural_score else "N/A"
        grade = r.structural_grade or "N/A"

        print(
            f"  {name:<35} │ "
            f"{ter:>6} │ "
            f"{turnover:>6} │ "
            f"{tenure:>10} │ "
            f"{aum:>10} │ "
            f"{score:>6} │ "
            f"{grade:<10}"
        )

    # Best/worst
    best = max(reports, key=lambda r: r.structural_score or 0)
    worst = min(reports, key=lambda r: r.structural_score or 100)

    print()
    print(f"  🏆 Best Structural Quality: {best.scheme_name[:40]} ({best.structural_score:.1f})")
    if worst != best:
        print(f"  ⚠️  Weakest Structure: {worst.scheme_name[:40]} ({worst.structural_score:.1f})")
    print()


def _print_cost_comparison(reports):
    """Compare long-term costs across funds."""
    print("=" * 90)
    print("   20-YEAR COST COMPARISON ON ₹10 LAKH INVESTMENT")
    print("   (Assuming 14% gross return)")
    print("=" * 90)
    print()

    header = f"  {'Fund':<35} │ {'TER':>6} │ {'Net Ret':>8} │ {'Final Value':>14} │ {'Cost Drag':>12}"
    print(header)
    print("  " + "─" * (len(header) - 2))

    for r in reports:
        if r.expense_analysis and r.expense_analysis.cost_simulations:
            sim = r.expense_analysis.cost_simulations.get("20Y", {})
            direct = sim.get("Direct Plan", {})

            name = r.scheme_name[:35]
            ter = r.expense_analysis.current_direct_pct or 0
            net_ret = direct.get("net_return_pct", 0)
            final = direct.get("final_value", 0)
            drag = direct.get("cost_drag", 0)

            print(
                f"  {name:<35} │ "
                f"{ter:>5.2f}% │ "
                f"{net_ret:>7.2f}% │ "
                f"₹{final:>11,.0f} │ "
                f"₹{drag:>9,.0f}"
            )

    # Index fund reference
    print(
        f"  {'Index Fund (Reference)':<35} │ "
        f"{'0.15':>5}% │ "
        f"{'13.85':>7}% │ "
        f"₹{10_00_000 * (1.1385 ** 20):>11,.0f} │ "
        f"₹{10_00_000 * (1.14 ** 20) - 10_00_000 * (1.1385 ** 20):>9,.0f}"
    )

    print()
    print("  💡 TIP: The difference between a 0.5% and 1.5% TER fund over 20 years")
    print("     on ₹10 lakh is approximately ₹12-15 LAKHS in lost wealth.")
    print("     Always prefer Direct plans. Always question high TER.")
    print()


if __name__ == "__main__":
    main()