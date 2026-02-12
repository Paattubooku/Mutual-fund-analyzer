#!/usr/bin/env python3
"""
demo_step6.py
─────────────
End-to-end demonstration of Step 6: Portfolio-Level Analysis

  • Portfolio valuation (P/E, P/B, ROE)
  • Equity Style Box mapping (3×3 grid)
  • Market cap breakdown with benchmark comparison
  • Sector allocation (overweight/underweight, Active Share)
  • Concentration analysis (Top N holdings, HHI)
  • Portfolio overlap between multiple funds
  • Full automated advisory interpretation

Run:
    python demo_step6.py
"""

from data.portfolio_provider import (
    get_sample_portfolio_ppfas,
    get_sample_portfolio_axis_bluechip,
    get_sample_portfolio_sbi_smallcap,
    get_benchmark_portfolio,
)
from metrics.portfolio_analysis import (
    generate_portfolio_report,
    calculate_overlap,
)
from utils.formatter import print_portfolio_report


def main():
    print("\n[1/4] Loading portfolio data...")

    # ── Load portfolios ──
    ppfas = get_sample_portfolio_ppfas()
    axis = get_sample_portfolio_axis_bluechip()
    sbi_sc = get_sample_portfolio_sbi_smallcap()
    benchmark = get_benchmark_portfolio("nifty_500")

    print(f"  ✓ {ppfas.scheme_name} ({len(ppfas.equity_holdings)} holdings)")
    print(f"  ✓ {axis.scheme_name} ({len(axis.equity_holdings)} holdings)")
    print(f"  ✓ {sbi_sc.scheme_name} ({len(sbi_sc.equity_holdings)} holdings)")
    print(f"  ✓ Benchmark: {benchmark.name}")

    # ── 2. Analyse primary fund ──
    print(f"\n[2/4] Analysing {ppfas.scheme_name}...")

    report = generate_portfolio_report(
        portfolio=ppfas,
        benchmark=benchmark,
        comparison_portfolios=[axis, sbi_sc],
    )

    print(f"  ✓ {report.sector_analysis.num_sectors} sectors analysed")
    print(f"  ✓ Style: {report.style_box.style_label}")
    if report.overlaps:
        print(f"  ✓ {len(report.overlaps)} overlap comparisons")

    # ── 3. Display ──
    print(f"\n[3/4] Rendering report...\n")
    print_portfolio_report(report)

    # ── 4. Multi-fund comparison ──
    print(f"\n[4/4] Multi-fund comparison...\n")
    _multi_fund_comparison([ppfas, axis, sbi_sc], benchmark)

    # ── Bonus: Overlap matrix ──
    _overlap_matrix([ppfas, axis, sbi_sc])


def _multi_fund_comparison(portfolios, benchmark):
    """Compare key portfolio metrics across funds."""
    from metrics.portfolio_analysis import (
        analyse_concentration,
        analyse_market_cap,
        calculate_style_box,
        analyse_sectors,
    )

    print("=" * 90)
    print("   MULTI-FUND PORTFOLIO COMPARISON")
    print("=" * 90)
    print()

    header = (
        f"  {'Fund':<35} │ {'P/E':>5} │ {'P/B':>5} │ "
        f"{'Stocks':>6} │ {'Top10%':>6} │ {'L/M/S':>15} │ {'Style':<18}"
    )
    print(header)
    print("  " + "─" * (len(header) - 2))

    for p in portfolios:
        con = analyse_concentration(p)
        mc = analyse_market_cap(p, benchmark)
        sb = calculate_style_box(p, benchmark)

        pe_str = f"{p.portfolio_pe:.1f}" if p.portfolio_pe else "N/A"
        pb_str = f"{p.portfolio_pb:.1f}" if p.portfolio_pb else "N/A"
        lms = f"{mc.large_cap_pct:.0f}/{mc.mid_cap_pct:.0f}/{mc.small_cap_pct:.0f}"

        name = p.scheme_name[:35]

        print(
            f"  {name:<35} │ "
            f"{pe_str:>5} │ "
            f"{pb_str:>5} │ "
            f"{con.total_stocks:>6} │ "
            f"{con.top_10_weight_pct:>5.1f}% │ "
            f"{lms:>15} │ "
            f"{sb.style_label:<18}"
        )

    print()

    # Structural comparison
    print("  Structural Metrics:")
    print(f"  {'Fund':<35} │ {'TER':>6} │ {'Turnover':>8} │ {'AUM (Cr)':>10}")
    print("  " + "─" * 70)

    for p in portfolios:
        ter = f"{p.expense_ratio_direct_pct:.2f}%" if p.expense_ratio_direct_pct else "N/A"
        turnover = f"{p.turnover_ratio_pct:.0f}%" if p.turnover_ratio_pct else "N/A"
        aum = f"₹{p.aum_cr:,.0f}" if p.aum_cr else "N/A"
        name = p.scheme_name[:35]

        print(f"  {name:<35} │ {ter:>6} │ {turnover:>8} │ {aum:>10}")

    print()


def _overlap_matrix(portfolios):
    """Print an N×N overlap matrix."""
    from metrics.portfolio_analysis import calculate_overlap

    print("=" * 90)
    print("   PORTFOLIO OVERLAP MATRIX")
    print("=" * 90)
    print()

    # Short names
    names = []
    for p in portfolios:
        parts = p.scheme_name.split(" - ")[0].split()
        short = " ".join(parts[:3]) if len(parts) > 3 else " ".join(parts)
        names.append(short[:20])

    # Header
    header = f"  {'':20}"
    for name in names:
        header += f" │ {name:>20}"
    print(header)
    print("  " + "─" * (22 + 23 * len(names)))

    # Matrix
    for i, p_a in enumerate(portfolios):
        row = f"  {names[i]:<20}"
        for j, p_b in enumerate(portfolios):
            if i == j:
                row += f" │ {'—':>20}"
            elif j > i:
                overlap = calculate_overlap(p_a, p_b)
                val = f"{overlap.overlap_pct:.1f}%"
                row += f" │ {val:>20}"
            else:
                overlap = calculate_overlap(p_b, p_a)
                val = f"{overlap.overlap_pct:.1f}%"
                row += f" │ {val:>20}"
        print(row)

    print()
    print("   Overlap > 40% → ⚠️  Limited diversification benefit")
    print("   Overlap < 20% → ✅  Good diversification")
    print()


if __name__ == "__main__":
    main()
    