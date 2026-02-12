"""
utils/formatter.py
──────────────────
Pretty-print trailing return reports to the console.
No external dependencies — pure string formatting.
"""

from __future__ import annotations
from data.models import TrailingReturnReport


# ─── Box-drawing constants ───
H = "─"
V = "│"
TL, TR, BL, BR = "┌", "┐", "└", "┘"
LT, RT, TT, BT, CR = "├", "┤", "┬", "┴", "┼"


def _row(cols: list[str], widths: list[int]) -> str:
    """Format one table row with padding."""
    cells = []
    for val, w in zip(cols, widths):
        cells.append(f" {val:<{w}} ")
    return V + V.join(cells) + V


def _separator(widths: list[int], left: str, mid: str, right: str) -> str:
    return left + mid.join(H * (w + 2) for w in widths) + right


def print_trailing_report(report: TrailingReturnReport) -> None:
    """Render the full trailing-return report to stdout."""

    # ── Header ──
    print()
    print("=" * 80)
    print("   TRAILING RETURNS ANALYSIS")
    print(f"   Fund : {report.scheme_info.scheme_name}")
    if report.benchmark_info:
        print(f"   Bench: {report.benchmark_info.scheme_name}")
    print(f"   As of: {report.as_of_date}")
    print("=" * 80)
    print()

    # ── Table ──
    has_bench = report.benchmark_info is not None

    if has_bench:
        headers = ["Period", "Start Date", "Fund Return", "Bench Return", "Excess", "Beat?"]
        widths  = [17,       12,           13,            13,             9,        5]
    else:
        headers = ["Period", "Start Date", "Start NAV", "End NAV", "Return", "Type"]
        widths  = [17,       12,           11,          11,        11,       8]

    print(_separator(widths, TL, TT, TR))
    print(_row(headers, widths))
    print(_separator(widths, LT, CR, RT))

    for c in report.comparisons:
        fr = c.fund_return
        fund_ret_str = f"{fr.primary_return_pct:+.2f}%"
        suffix = "" if fr.is_annualized else " *"
        fund_ret_str += suffix

        if has_bench:
            if c.benchmark_return is not None:
                br = c.benchmark_return
                bench_str = f"{br.primary_return_pct:+.2f}%{suffix}"
                excess_str = f"{c.excess_return_pct:+.2f}%" if c.excess_return_pct is not None else "N/A"
                beat_str = "▲ YES" if c.beat_benchmark else "▼ NO"
            else:
                bench_str = "N/A"
                excess_str = "N/A"
                beat_str = "—"

            cols = [
                fr.period_label,
                str(fr.start_date),
                fund_ret_str,
                bench_str,
                excess_str,
                beat_str,
            ]
        else:
            cols = [
                fr.period_label,
                str(fr.start_date),
                f"₹{fr.start_nav:,.2f}",
                f"₹{fr.end_nav:,.2f}",
                fund_ret_str,
                "CAGR" if fr.is_annualized else "Abs",
            ]

        print(_row(cols, widths))

    print(_separator(widths, BL, BT, BR))

    if not all(c.fund_return.is_annualized for c in report.comparisons):
        print("  * Absolute return (period < 1 year) — not annualised")
    print()

    # ── Interpretation ──
    if report.interpretation:
        print("─" * 80)
        print("   AUTOMATED INTERPRETATION")
        print("─" * 80)
        for line in report.interpretation:
            print(f"   {line}")
        print()

# ─────────────────────────────────────────────────────────
# ADDITIONS FOR SECTION 1.2 — ROLLING RETURNS DISPLAY
# ─────────────────────────────────────────────────────────

from data.models import RollingReturnReport, RollingReturnDistribution


def _fmt(val: float, suffix: str = "%") -> str:
    """Format a float with sign and suffix."""
    return f"{val:+.2f}{suffix}" if val != 0 else f"0.00{suffix}"


def print_rolling_report(report: RollingReturnReport) -> None:
    """Render the full rolling-return report to stdout."""

    # ── Header ──
    print()
    print("=" * 90)
    print("   ROLLING RETURNS ANALYSIS")
    print(f"   Fund : {report.scheme_info.scheme_name}")
    if report.benchmark_info:
        print(f"   Bench: {report.benchmark_info.scheme_name}")
    print(f"   As of: {report.as_of_date}")
    print("=" * 90)
    print()

    # ── Distribution Summary Table ──
    has_bench = report.benchmark_info is not None

    for dist in report.distributions:
        _print_distribution_card(dist, has_bench)

    # ── Interpretation ──
    if report.interpretation:
        print()
        print("=" * 90)
        print("   AUTOMATED INTERPRETATION")
        print("=" * 90)
        for line in report.interpretation:
            print(f"   {line}")
        print()


def _print_distribution_card(dist: RollingReturnDistribution, has_bench: bool) -> None:
    """Print a detailed card for one rolling window distribution."""

    width = 88

    print(f"┌{'─' * width}┐")
    title = f"  {dist.window_label} ROLLING RETURNS  ({dist.num_observations:,} observations)"
    print(f"│{title:<{width}}│")
    print(f"│  Coverage: {dist.start_coverage_date} → {dist.end_coverage_date:<{width - 36}}│")
    print(f"├{'─' * width}┤")

    # ── Core statistics section ──
    print(f"│{'  DISTRIBUTION STATISTICS':<{width}}│")
    print(f"│{'  ' + '─' * 40:<{width}}│")

    stats = [
        ("Mean (Average) CAGR", f"{dist.mean_return_pct:+.2f}%"),
        ("Median (P50) CAGR",   f"{dist.median_return_pct:+.2f}%"),
        ("Minimum (Worst)",     f"{dist.min_return_pct:+.2f}%"),
        ("Maximum (Best)",      f"{dist.max_return_pct:+.2f}%"),
        ("Std Deviation",       f"{dist.std_dev_pct:.2f}%"),
    ]
    for label, value in stats:
        line = f"    {label:<30} {value:>12}"
        print(f"│{line:<{width}}│")

    print(f"│{'  ' + '─' * 40:<{width}}│")

    # ── Percentile distribution ──
    print(f"│{'  PERCENTILE DISTRIBUTION':<{width}}│")
    pct_bar = (
        f"    P10: {dist.percentile_10_pct:+.2f}%  │  "
        f"P25: {dist.percentile_25_pct:+.2f}%  │  "
        f"P50: {dist.median_return_pct:+.2f}%  │  "
        f"P75: {dist.percentile_75_pct:+.2f}%  │  "
        f"P90: {dist.percentile_90_pct:+.2f}%"
    )
    print(f"│{pct_bar:<{width}}│")

    # ── Visual distribution bar ──
    _print_distribution_visual(dist, width)

    print(f"│{'  ' + '─' * 40:<{width}}│")

    # ── Probability metrics ──
    print(f"│{'  PROBABILITY METRICS':<{width}}│")
    prob_lines = [
        ("Positive Return Probability", f"{dist.positive_return_pct:.1f}%"),
        ("Beat Risk-Free Rate",         f"{dist.above_risk_free_pct:.1f}%"),
    ]
    if has_bench and dist.win_rate_vs_benchmark_pct is not None:
        prob_lines.append(
            ("Win Rate vs Benchmark",   f"{dist.win_rate_vs_benchmark_pct:.1f}%")
        )
    for label, value in prob_lines:
        line = f"    {label:<30} {value:>12}"
        print(f"│{line:<{width}}│")

    # ── Benchmark excess returns ──
    if has_bench and dist.avg_excess_return_pct is not None:
        print(f"│{'  ' + '─' * 40:<{width}}│")
        print(f"│{'  BENCHMARK COMPARISON':<{width}}│")
        bench_lines = [
            ("Avg Excess Return",     f"{dist.avg_excess_return_pct:+.2f}%"),
            ("Median Excess Return",  f"{dist.median_excess_return_pct:+.2f}%"),
        ]
        for label, value in bench_lines:
            line = f"    {label:<30} {value:>12}"
            print(f"│{line:<{width}}│")

    # ── Worst/Best period dates ──
    if dist.min_return_start_date:
        print(f"│{'  ' + '─' * 40:<{width}}│")
        worst = f"    Worst period: {dist.min_return_start_date} → {dist.min_return_end_date}  ({dist.min_return_pct:+.2f}%)"
        best  = f"    Best period:  {dist.max_return_start_date} → {dist.max_return_end_date}  ({dist.max_return_pct:+.2f}%)"
        print(f"│{worst:<{width}}│")
        print(f"│{best:<{width}}│")

    print(f"└{'─' * width}┘")
    print()


def _print_distribution_visual(dist: RollingReturnDistribution, box_width: int) -> None:
    """
    Print a simple ASCII histogram-style visualisation
    of the rolling return distribution using percentile data.
    """
    # Build a simplified bar showing P10, P25, P50, P75, P90 positions
    # Scale to available width

    bar_width = 60
    margin = 4

    # Determine the range
    range_min = min(dist.percentile_10_pct, 0) - 2
    range_max = dist.percentile_90_pct + 2
    span = range_max - range_min
    if span <= 0:
        return

    def pos(val: float) -> int:
        return int((val - range_min) / span * bar_width)

    # Build the bar character by character
    bar = [' '] * (bar_width + 1)

    # Fill IQR (P25-P75) with block characters
    p25_pos = pos(dist.percentile_25_pct)
    p75_pos = pos(dist.percentile_75_pct)
    for i in range(p25_pos, min(p75_pos + 1, bar_width + 1)):
        bar[i] = '█'

    # P10-P25 and P75-P90 with lighter fill
    p10_pos = pos(dist.percentile_10_pct)
    p90_pos = pos(dist.percentile_90_pct)
    for i in range(p10_pos, p25_pos):
        if 0 <= i <= bar_width:
            bar[i] = '░'
    for i in range(p75_pos + 1, min(p90_pos + 1, bar_width + 1)):
        if 0 <= i <= bar_width:
            bar[i] = '░'

    # Mark median
    p50_pos = pos(dist.median_return_pct)
    if 0 <= p50_pos <= bar_width:
        bar[p50_pos] = '▼'

    # Mark zero line if in range
    if range_min < 0 < range_max:
        zero_pos = pos(0)
        if 0 <= zero_pos <= bar_width and bar[zero_pos] == ' ':
            bar[zero_pos] = '│'

    bar_str = ''.join(bar)
    line = f"{' ' * margin}{bar_str}"
    print(f"│{line:<{box_width}}│")

    # Scale labels
    left_label = f"{range_min:.0f}%"
    right_label = f"{range_max:.0f}%"
    scale = f"{' ' * margin}{left_label}{' ' * (bar_width - len(left_label) - len(right_label) + 1)}{right_label}"
    print(f"│{scale:<{box_width}}│")

    legend = f"{' ' * margin}░ P10-P25/P75-P90  █ IQR (P25-P75)  ▼ Median"
    print(f"│{legend:<{box_width}}│")

# ─────────────────────────────────────────────────────────
# ADDITIONS FOR SECTION 1.3 — CONSISTENCY DISPLAY
# ─────────────────────────────────────────────────────────

from data.models import (
    ConsistencyReport,
    CalendarYearAnalysis,
    CaptureRatios,
)


def print_consistency_report(report: ConsistencyReport) -> None:
    """Render the full consistency-of-outperformance report to stdout."""

    # ── Header ──
    print()
    print("=" * 90)
    print("   CONSISTENCY OF OUTPERFORMANCE ANALYSIS")
    print(f"   Fund : {report.scheme_info.scheme_name}")
    if report.benchmark_info:
        print(f"   Bench: {report.benchmark_info.scheme_name}")
    print(f"   As of: {report.as_of_date}")
    print("=" * 90)

    # ── Calendar Year Table ──
    if report.calendar_year_analysis:
        _print_calendar_year_table(report.calendar_year_analysis)

    # ── Capture Ratio Card ──
    if report.capture_ratios:
        _print_capture_card(report.capture_ratios)

    # ── Interpretation ──
    if report.interpretation:
        print()
        print("=" * 90)
        print("   AUTOMATED INTERPRETATION")
        print("=" * 90)
        for line in report.interpretation:
            print(f"   {line}")
        print()


def _print_calendar_year_table(analysis: CalendarYearAnalysis) -> None:
    """Print the year-by-year comparison table."""

    print()
    print("─" * 90)
    print("   CALENDAR YEAR RETURNS")
    print("─" * 90)
    print()

    has_bench = any(
        y.benchmark_return_pct is not None for y in analysis.yearly_returns
    )

    if has_bench:
        headers = ["Year", "Fund Return", "Benchmark", "Excess", "Beat?", "Visual"]
        widths = [6, 13, 13, 10, 7, 28]
    else:
        headers = ["Year", "Fund Return"]
        widths = [6, 13]

    print(_separator(widths, TL, TT, TR))
    print(_row(headers, widths))
    print(_separator(widths, LT, CR, RT))

    for yr in analysis.yearly_returns:
        fund_str = f"{yr.fund_return_pct:+.2f}%"

        if has_bench:
            bench_str = (
                f"{yr.benchmark_return_pct:+.2f}%"
                if yr.benchmark_return_pct is not None
                else "N/A"
            )
            excess_str = (
                f"{yr.excess_return_pct:+.2f}%"
                if yr.excess_return_pct is not None
                else "N/A"
            )
            beat_str = (
                "▲ YES" if yr.beat_benchmark
                else "▼ NO" if yr.beat_benchmark is not None
                else "—"
            )

            # Visual bar for excess return
            visual = _excess_bar(yr.excess_return_pct)

            cols = [str(yr.year), fund_str, bench_str, excess_str, beat_str, visual]
        else:
            cols = [str(yr.year), fund_str]

        print(_row(cols, widths))

    print(_separator(widths, BL, BT, BR))

    # ── Summary line ──
    if has_bench:
        grade_colors = {
            "EXCEPTIONAL": "🏆",
            "STRONG": "✅",
            "GOOD": "🔶",
            "AVERAGE": "⚠️",
            "POOR": "❌",
        }
        icon = grade_colors.get(analysis.consistency_grade, "")

        print(
            f"\n  {icon} Consistency: "
            f"{analysis.years_beat_benchmark}/{analysis.total_years} years "
            f"({analysis.consistency_pct:.1f}%) — {analysis.consistency_grade}"
        )
        print(
            f"  📊 Avg Annual Alpha: {analysis.avg_annual_excess_pct:+.2f}% | "
            f"Median: {analysis.median_annual_excess_pct:+.2f}%"
        )
    print()


def _excess_bar(excess: Optional[float], max_width: int = 25) -> str:
    """
    Create a visual bar showing excess/deficit vs benchmark.

    Positive excess  → green blocks to the right of center
    Negative excess  → red blocks to the left of center
    """
    if excess is None:
        return " " * max_width

    # Scale: 1 block per 2% excess/deficit, capped at half-width
    half = max_width // 2
    center = half

    # Number of blocks (1 block = 2 percentage points)
    blocks = min(abs(int(excess / 2)), half)

    bar = [' '] * max_width
    bar[center] = '│'

    if excess > 0:
        for i in range(1, blocks + 1):
            pos = center + i
            if pos < max_width:
                bar[pos] = '█'
    elif excess < 0:
        for i in range(1, blocks + 1):
            pos = center - i
            if pos >= 0:
                bar[pos] = '░'

    return ''.join(bar)


def _print_capture_card(capture: CaptureRatios) -> None:
    """Print the capture ratio analysis card."""

    width = 88

    print(f"┌{'─' * width}┐")
    title = "  UP-MARKET / DOWN-MARKET CAPTURE RATIOS"
    print(f"│{title:<{width}}│")
    subtitle = (
        f"  Based on {capture.total_months} months "
        f"({capture.num_up_months} up, {capture.num_down_months} down)"
    )
    print(f"│{subtitle:<{width}}│")
    print(f"├{'─' * width}┤")

    # ── Main ratios ──
    lines = [
        ("Up-Market Capture Ratio", f"{capture.up_capture_ratio:.1f}%",
         "▲" if capture.up_capture_ratio > 100 else "▽"),
        ("Down-Market Capture Ratio", f"{capture.down_capture_ratio:.1f}%",
         "▲" if capture.down_capture_ratio < 100 else "▽"),
        ("Capture Ratio (Up/Down)", f"{capture.capture_ratio:.2f}",
         "★" if capture.capture_ratio > 1.2 else "●" if capture.capture_ratio > 1.0 else "○"),
    ]

    for label, value, icon in lines:
        line = f"    {icon} {label:<35} {value:>12}"
        print(f"│{line:<{width}}│")

    print(f"│{'  ' + '─' * 45:<{width}}│")

    # ── Visual comparison ──
    _print_capture_visual(capture, width)

    print(f"│{'  ' + '─' * 45:<{width}}│")

    # ── Batting averages ──
    bat_lines = [
        ("Up-month batting average",
         f"{capture.up_month_batting_avg_pct:.1f}%"),
        ("Down-month batting average",
         f"{capture.down_month_batting_avg_pct:.1f}%"),
    ]
    for label, value in bat_lines:
        line = f"    {label:<35} {value:>12}"
        print(f"│{line:<{width}}│")

    print(f"│{'  ' + '─' * 45:<{width}}│")

    # ── Monthly return details ──
    detail_lines = [
        ("Avg fund return (up months)",
         f"{capture.avg_fund_up_month_pct:+.2f}%",
         f"(bench: {capture.avg_bench_up_month_pct:+.2f}%)"),
        ("Avg fund return (down months)",
         f"{capture.avg_fund_down_month_pct:+.2f}%",
         f"(bench: {capture.avg_bench_down_month_pct:+.2f}%)"),
    ]
    for label, value, extra in detail_lines:
        line = f"    {label:<35} {value:>8}  {extra}"
        print(f"│{line:<{width}}│")

    print(f"└{'─' * width}┘")
    print()


def _print_capture_visual(capture: CaptureRatios, box_width: int) -> None:
    """
    Print a 2×2 visual grid showing the fund's capture profile.
    """
    # Determine profile type
    up_high = capture.up_capture_ratio > 100
    down_low = capture.down_capture_ratio < 100

    profiles = {
        (True, True):   "IDEAL      (More upside, less downside)",
        (True, False):  "AGGRESSIVE (More upside, more downside)",
        (False, True):  "DEFENSIVE  (Less upside, less downside)",
        (False, False): "LAGGING    (Less upside, more downside)",
    }

    icons = {
        (True, True):   "🏆",
        (True, False):  "⚠️",
        (False, True):  "🛡️",
        (False, False): "❌",
    }

    profile = profiles.get((up_high, down_low), "UNKNOWN")
    icon = icons.get((up_high, down_low), "")

    line = f"    {icon}  Profile: {profile}"
    print(f"│{line:<{box_width}}│")

    # Simple 2×2 grid
    grid_lines = [
        f"                          Down < 100      Down > 100",
        f"                        ┌──────────────┬──────────────┐",
        f"        Up > 100        │{'  ★ IDEAL   ' if up_high and down_low else '            '}│{'  AGGRESSIVE ' if up_high and not down_low else '            '}│",
        f"                        ├──────────────┼──────────────┤",
        f"        Up < 100        │{'  DEFENSIVE ' if not up_high and down_low else '            '}│{'  ✗ LAGGING ' if not up_high and not down_low else '            '}│",
        f"                        └──────────────┴──────────────┘",
    ]

    for gl in grid_lines:
        print(f"│{gl:<{box_width}}│")

# ─────────────────────────────────────────────────────────
# ADDITIONS FOR SECTION 1.4 — SIP RETURNS DISPLAY
# ─────────────────────────────────────────────────────────

from data.models import (
    SIPReturnReport,
    SIPSimulationResult,
    LumpSumComparison,
    RollingSIPDistribution,
    SIPDateSensitivity,
)


def print_sip_report(report: SIPReturnReport) -> None:
    """Render the full SIP return report to stdout."""

    # ── Header ──
    print()
    print("=" * 90)
    print("   SIP RETURN ANALYSIS (XIRR-Based)")
    print(f"   Fund : {report.scheme_info.scheme_name}")
    if report.benchmark_info:
        print(f"   Bench: {report.benchmark_info.scheme_name}")
    print(f"   As of: {report.as_of_date}")
    print("=" * 90)

    # ── 1. Trailing SIP Returns Table ──
    if report.sip_results:
        _print_sip_trailing_table(report.sip_results)

    # ── 2. SIP vs Lump Sum Table ──
    if report.lumpsum_comparisons:
        _print_lumpsum_comparison(report.lumpsum_comparisons)

    # ── 3. Rolling SIP Summary ──
    if report.rolling_sip:
        _print_rolling_sip_summary(report.rolling_sip)

    # ── 4. Date Sensitivity ──
    if report.date_sensitivity:
        _print_date_sensitivity(report.date_sensitivity)

    # ── 5. Interpretation ──
    if report.interpretation:
        print()
        print("=" * 90)
        print("   AUTOMATED INTERPRETATION")
        print("=" * 90)
        for line in report.interpretation:
            print(f"   {line}")
        print()


def _print_sip_trailing_table(results: List[SIPSimulationResult]) -> None:
    """Print trailing SIP returns in a clean table."""
    print()
    print("─" * 90)
    print("   TRAILING SIP RETURNS")
    print("─" * 90)
    print()

    headers = [
        "Period", "SIP Start", "Invest.",
        "Invested", "Final Value", "XIRR", "Multiple",
    ]
    widths = [10, 12, 5, 14, 14, 9, 9]

    print(_separator(widths, TL, TT, TR))
    print(_row(headers, widths))
    print(_separator(widths, LT, CR, RT))

    for r in results:
        xirr_str = f"{r.xirr_pct:+.2f}%" if r.xirr_pct is not None else "N/A"

        cols = [
            r.period_label,
            str(r.sip_start_date),
            str(r.num_installments),
            f"₹{r.total_invested:>10,.0f}",
            f"₹{r.final_value:>10,.0f}",
            xirr_str,
            f"{r.wealth_multiple:.2f}×",
        ]
        print(_row(cols, widths))

    print(_separator(widths, BL, BT, BR))
    print()


def _print_lumpsum_comparison(comparisons: List[LumpSumComparison]) -> None:
    """Print SIP vs Lump Sum comparison table."""
    print()
    print("─" * 90)
    print("   SIP vs LUMP SUM COMPARISON")
    print("   (Same total amount: invested gradually via SIP vs all-at-once via Lump Sum)")
    print("─" * 90)
    print()

    headers = [
        "Period", "SIP XIRR", "LS CAGR",
        "SIP Final", "LS Final", "Diff", "Winner",
    ]
    widths = [10, 10, 10, 14, 14, 8, 10]

    print(_separator(widths, TL, TT, TR))
    print(_row(headers, widths))
    print(_separator(widths, LT, CR, RT))

    for c in comparisons:
        sip_str = f"{c.sip_xirr_pct:+.2f}%" if c.sip_xirr_pct is not None else "N/A"
        ls_str = f"{c.lumpsum_cagr_pct:+.2f}%" if c.lumpsum_cagr_pct is not None else "N/A"
        diff_str = f"{c.sip_advantage_pct:+.2f}%" if c.sip_advantage_pct is not None else "N/A"

        winner_icon = {
            "SIP": "🟢 SIP",
            "LUMP SUM": "🔵 LS",
            "TIE": "⚪ TIE",
        }.get(c.winner, c.winner)

        cols = [
            c.period_label,
            sip_str,
            ls_str,
            f"₹{c.sip_final_value:>10,.0f}",
            f"₹{c.lumpsum_final_value:>10,.0f}",
            diff_str,
            winner_icon,
        ]
        print(_row(cols, widths))

    print(_separator(widths, BL, BT, BR))
    print()


def _print_rolling_sip_summary(distributions: List[RollingSIPDistribution]) -> None:
    """Print rolling SIP XIRR distribution summary."""
    print()
    print("─" * 90)
    print("   ROLLING SIP XIRR DISTRIBUTION")
    print("   (What XIRR would you get if you started a SIP on ANY month?)")
    print("─" * 90)
    print()

    for dist in distributions:
        width = 88

        print(f"┌{'─' * width}┐")
        title = (
            f"  {dist.period_label} SIP  "
            f"({dist.num_observations} possible start months)"
        )
        print(f"│{title:<{width}}│")
        print(f"├{'─' * width}┤")

        stats = [
            ("Mean XIRR",       f"{dist.mean_xirr_pct:+.2f}%"),
            ("Median XIRR",     f"{dist.median_xirr_pct:+.2f}%"),
            ("Worst Case",      f"{dist.min_xirr_pct:+.2f}%"),
            ("Best Case",       f"{dist.max_xirr_pct:+.2f}%"),
            ("Std Deviation",   f"{dist.std_dev_pct:.2f}%"),
        ]
        for label, value in stats:
            line = f"    {label:<30} {value:>12}"
            print(f"│{line:<{width}}│")

        print(f"│{'  ' + '─' * 45:<{width}}│")

        # Percentiles
        pct_line = (
            f"    P10: {dist.percentile_10_pct:+.2f}%  │  "
            f"P25: {dist.percentile_25_pct:+.2f}%  │  "
            f"P50: {dist.median_xirr_pct:+.2f}%  │  "
            f"P75: {dist.percentile_75_pct:+.2f}%  │  "
            f"P90: {dist.percentile_90_pct:+.2f}%"
        )
        print(f"│{pct_line:<{width}}│")

        print(f"│{'  ' + '─' * 45:<{width}}│")

        # Probabilities
        prob_lines = [
            ("Positive SIP return",   f"{dist.positive_xirr_pct:.1f}%"),
            ("Beat risk-free rate",   f"{dist.above_risk_free_pct:.1f}%"),
        ]
        if dist.win_rate_vs_benchmark_pct is not None:
            prob_lines.append(
                ("Beat benchmark SIP",    f"{dist.win_rate_vs_benchmark_pct:.1f}%")
            )
        for label, value in prob_lines:
            line = f"    {label:<30} {value:>12}"
            print(f"│{line:<{width}}│")

        # Worst/Best start dates
        if dist.min_xirr_start_date:
            print(f"│{'  ' + '─' * 45:<{width}}│")
            worst_line = (
                f"    Worst start: {dist.min_xirr_start_date} "
                f"→ XIRR = {dist.min_xirr_pct:+.2f}%"
            )
            best_line = (
                f"    Best start:  {dist.max_xirr_start_date} "
                f"→ XIRR = {dist.max_xirr_pct:+.2f}%"
            )
            print(f"│{worst_line:<{width}}│")
            print(f"│{best_line:<{width}}│")

        print(f"└{'─' * width}┘")
        print()


def _print_date_sensitivity(sensitivity: SIPDateSensitivity) -> None:
    """Print SIP date sensitivity analysis."""
    print()
    print("─" * 90)
    print(f"   SIP DATE SENSITIVITY ({sensitivity.period_label} window)")
    print("   Does the day-of-month for your SIP matter?")
    print("─" * 90)
    print()

    # Find the range for bar scaling
    values = list(sensitivity.day_results.values())
    min_val = min(values)
    max_val = max(values)
    spread = max_val - min_val

    for day in sorted(sensitivity.day_results.keys()):
        xirr = sensitivity.day_results[day]

        # Scale bar
        if spread > 0:
            bar_len = int((xirr - min_val) / spread * 30)
        else:
            bar_len = 15

        bar = "█" * bar_len

        # Markers
        if day == sensitivity.best_day:
            marker = " ◄ BEST"
        elif day == sensitivity.worst_day:
            marker = " ◄ WORST"
        else:
            marker = ""

        print(f"   {day:>2}th:  {xirr:>6.2f}%  │{bar}{marker}")

    print()
    print(
        f"   Spread: {sensitivity.spread_pct:.2f}% "
        f"(Best: {sensitivity.best_day}th at {sensitivity.best_day_xirr_pct:.2f}% | "
        f"Worst: {sensitivity.worst_day}th at {sensitivity.worst_day_xirr_pct:.2f}%)"
    )

    if sensitivity.spread_pct < 0.5:
        print("   ✅  Verdict: SIP date does NOT matter. Pick any convenient day.")
    elif sensitivity.spread_pct < 1.5:
        print("   🔶  Verdict: Marginal difference. Don't stress about it.")
    else:
        print(
            f"   ⚠️   Verdict: Noticeable gap. "
            f"The {sensitivity.best_day}th tends to perform slightly better."
        )
    print()

# ─────────────────────────────────────────────────────────
# ADDITIONS FOR SECTION 2 — RISK-ADJUSTED DISPLAY
# ─────────────────────────────────────────────────────────

from data.models import (
    RiskAdjustedReport,
    VolatilityMetrics,
    BetaAnalysis,
    RiskAdjustedRatios,
)


def print_risk_adjusted_report(report: RiskAdjustedReport) -> None:
    """Render the full risk-adjusted report to stdout."""

    # ── Header ──
    print()
    print("=" * 90)
    print("   RISK-ADJUSTED RETURN ANALYSIS")
    print(f"   Fund : {report.scheme_info.scheme_name}")
    if report.benchmark_info:
        print(f"   Bench: {report.benchmark_info.scheme_name}")
    print(f"   Period: {report.period_description}")
    print(f"   As of: {report.as_of_date}")
    print("=" * 90)

    # ── 1. Volatility Card ──
    _print_volatility_card(report.volatility)

    # ── 2. Beta Card ──
    if report.beta_analysis:
        _print_beta_card(report.beta_analysis)

    # ── 3. Ratios Dashboard ──
    _print_ratios_dashboard(report.ratios)

    # ── 4. Comparison Matrix ──
    _print_ratio_comparison_matrix(report.ratios)

    # ── 5. Interpretation ──
    if report.interpretation:
        print()
        print("=" * 90)
        print("   AUTOMATED INTERPRETATION")
        print("=" * 90)
        for line in report.interpretation:
            print(f"   {line}")
        print()


def _print_volatility_card(vol: VolatilityMetrics) -> None:
    """Print volatility metrics card."""
    width = 88

    print()
    print(f"┌{'─' * width}┐")
    print(f"│{'  VOLATILITY METRICS':<{width}}│")
    print(f"│{'  (Annualised from monthly return data)':<{width}}│")
    print(f"├{'─' * width}┤")

    lines = [
        ("TOTAL RISK", "", ""),
        ("  Annualised Std Deviation (σ)", f"{vol.annualised_std_dev_pct:.2f}%",
         _vol_bar(vol.annualised_std_dev_pct)),
        ("  Monthly Std Deviation", f"{vol.monthly_std_dev_pct:.4f}%", ""),
        ("", "", ""),
        ("DOWNSIDE RISK", "", ""),
        ("  Annualised Downside Dev (σ↓)", f"{vol.annualised_downside_dev_pct:.2f}%",
         _vol_bar(vol.annualised_downside_dev_pct)),
        ("  MAR (Min Acceptable Return)", f"{vol.mar_pct:.2f}%", ""),
        ("", "", ""),
        ("RETURN STATISTICS", "", ""),
        ("  Annualised Mean Return", f"{vol.annualised_mean_return_pct:+.2f}%", ""),
        ("  Negative Months", f"{vol.num_negative_months}/{vol.num_months} ({vol.pct_negative_months:.1f}%)", ""),
        ("  Worst Month", f"{vol.worst_month_pct:+.2f}%", ""),
        ("  Best Month", f"{vol.best_month_pct:+.2f}%", ""),
    ]

    for label, value, extra in lines:
        if label == "":
            print(f"│{'  ' + '─' * 45:<{width}}│")
        else:
            line = f"    {label:<35} {value:>12}  {extra}"
            print(f"│{line:<{width}}│")

    # Downside ratio visual
    total = vol.annualised_std_dev_pct
    down = vol.annualised_downside_dev_pct
    if total > 0:
        ratio = down / total * 100
        up_pct = 100 - ratio
        visual = (
            f"    Downside/Total ratio: {ratio:.0f}% downside │ {up_pct:.0f}% upside"
        )
        print(f"│{'  ' + '─' * 45:<{width}}│")
        print(f"│{visual:<{width}}│")

        bar_width = 50
        down_blocks = int(ratio / 100 * bar_width)
        up_blocks = bar_width - down_blocks
        bar = f"    {'░' * down_blocks}{'█' * up_blocks}"
        print(f"│{bar:<{width}}│")
        legend = f"    ░ Downside  █ Upside"
        print(f"│{legend:<{width}}│")

    print(f"└{'─' * width}┘")
    print()


def _vol_bar(pct: float) -> str:
    """Create a simple volatility bar."""
    blocks = min(int(pct / 2), 20)
    if pct < 12:
        return "▏" + "█" * blocks + " LOW"
    elif pct < 18:
        return "▏" + "█" * blocks + " MOD"
    elif pct < 25:
        return "▏" + "█" * blocks + " HIGH"
    else:
        return "▏" + "█" * blocks + " V.HIGH"


def _print_beta_card(ba: BetaAnalysis) -> None:
    """Print beta analysis card."""
    width = 88

    print(f"┌{'─' * width}┐")
    print(f"│{'  BETA & BENCHMARK REGRESSION ANALYSIS':<{width}}│")
    print(f"│{'  R_fund = α + β × R_benchmark + ε':<{width}}│")
    print(f"├{'─' * width}┤")

    lines = [
        ("Beta (β)", f"{ba.beta:.4f}", f"({ba.beta_category})"),
        ("Regression Alpha (α, annualised)", f"{ba.alpha_annualised_pct:+.2f}%", ""),
        ("R-Squared (R²)", f"{ba.r_squared:.4f}", f"({ba.r_squared * 100:.1f}% explained)"),
        ("Correlation", f"{ba.correlation:.4f}", ""),
        ("Tracking Error (annualised)", f"{ba.tracking_error_pct:.2f}%", ""),
        ("Data Points", f"{ba.num_months} months", ""),
    ]

    for label, value, extra in lines:
        line = f"    {label:<35} {value:>12}  {extra}"
        print(f"│{line:<{width}}│")

    # Beta visual scale
    print(f"│{'  ' + '─' * 45:<{width}}│")
    beta_visual = _beta_scale_visual(ba.beta)
    for bv_line in beta_visual:
        print(f"│{bv_line:<{width}}│")

    print(f"└{'─' * width}┘")
    print()


def _beta_scale_visual(beta: float) -> List[str]:
    """Create a visual beta scale."""
    lines = []

    # Scale from 0.0 to 2.0
    scale_width = 50
    margin = 4

    # Position of beta on the scale
    pos = int(min(max(beta, 0.0), 2.0) / 2.0 * scale_width)

    # Scale line
    scale = [' '] * (scale_width + 1)
    scale[0] = '|'
    bench_pos = int(1.0 / 2.0 * scale_width)
    scale[bench_pos] = '|'
    scale[-1] = '|'

    # Mark beta position
    if 0 <= pos <= scale_width:
        scale[pos] = '▼'

    lines.append(' ' * margin + ''.join(scale))
    lines.append(
        ' ' * margin + '0.0' + ' ' * (bench_pos - 3) + '1.0 (Market)'
        + ' ' * max(0, scale_width - bench_pos - 13) + '2.0'
    )

    # Description
    if beta < 0.8:
        desc = "← Defensive (less volatile than market)"
    elif beta < 1.05:
        desc = "≈ Market-like movement"
    else:
        desc = "→ Aggressive (more volatile than market)"

    lines.append(' ' * margin + desc)

    return lines


def _print_ratios_dashboard(ratios: RiskAdjustedRatios) -> None:
    """Print the main risk-adjusted ratios dashboard."""
    width = 88

    print(f"┌{'─' * width}┐")
    print(f"│{'  RISK-ADJUSTED RATIOS DASHBOARD':<{width}}│")
    print(f"│{'  Rf=' + str(ratios.risk_free_rate_pct) + '% | Period=' + str(ratios.period_years) + 'Y | Fund Return=' + str(ratios.fund_return_pct) + '%':<{width}}│")

    if ratios.benchmark_return_pct is not None:
        bench_line = f"  Benchmark Return={ratios.benchmark_return_pct}% | β={ratios.beta}"
        print(f"│{bench_line:<{width}}│")
    print(f"├{'─' * width}┤")

    grade_icons = {
        "EXCELLENT": "🏆", "EXCEPTIONAL": "🏆",
        "VERY GOOD": "✅", "GOOD": "✅",
        "ACCEPTABLE": "🔶", "AVERAGE": "🔶",
        "MARGINAL": "⚠️", "POOR": "❌", "NEGATIVE": "❌",
    }

    # Each ratio in a structured row
    ratio_entries = [
        ("Sharpe Ratio", f"{ratios.sharpe_ratio:.4f}",
         ratios.sharpe_grade, "(R − Rf) / σ",
         "Return per unit of TOTAL risk"),
        ("Sortino Ratio", f"{ratios.sortino_ratio:.4f}",
         ratios.sortino_grade, "(R − Rf) / σ↓",
         "Return per unit of DOWNSIDE risk"),
    ]

    if ratios.jensens_alpha_pct is not None:
        ratio_entries.append(
            ("Jensen's Alpha", f"{ratios.jensens_alpha_pct:+.2f}%",
             ratios.alpha_grade, "R − [Rf + β(Rb−Rf)]",
             "Excess return beyond CAPM prediction")
        )

    if ratios.treynor_ratio is not None:
        ratio_entries.append(
            ("Treynor Ratio", f"{ratios.treynor_ratio:.4f}",
             ratios.treynor_grade, "(R − Rf) / β",
             "Return per unit of MARKET risk")
        )

    if ratios.information_ratio is not None:
        ratio_entries.append(
            ("Information Ratio", f"{ratios.information_ratio:.4f}",
             ratios.information_grade, "(R − Rb) / TE",
             "Consistency of outperformance")
        )

    for name, value, grade, formula, desc in ratio_entries:
        icon = grade_icons.get(grade, "")
        line1 = f"  {icon}  {name:<22} {value:>10}    {grade:<12}  {formula}"
        line2 = f"       {desc}"
        print(f"│{line1:<{width}}│")
        print(f"│{line2:<{width}}│")
        print(f"│{'  ' + '─' * 45:<{width}}│")

    print(f"└{'─' * width}┘")
    print()


def _print_ratio_comparison_matrix(ratios: RiskAdjustedRatios) -> None:
    """Print the ratio comparison matrix from Section 2.8."""
    print()
    print("─" * 90)
    print("   RATIO COMPARISON MATRIX — Which Ratio to Use When?")
    print("─" * 90)
    print()

    headers = ["Ratio", "Risk Measure", "Best For", "This Fund"]
    widths = [20, 15, 30, 15]

    print(_separator(widths, TL, TT, TR))
    print(_row(headers, widths))
    print(_separator(widths, LT, CR, RT))

    entries = [
        ("Sharpe", "Std Dev", "Standalone fund comparison",
         f"{ratios.sharpe_ratio:.3f}"),
        ("Sortino", "Downside Dev", "When upside vol is good",
         f"{ratios.sortino_ratio:.3f}"),
    ]

    if ratios.jensens_alpha_pct is not None:
        entries.append(
            ("Jensen's Alpha", "Beta (CAPM)", "Identifying genuine skill",
             f"{ratios.jensens_alpha_pct:+.2f}%")
        )

    if ratios.treynor_ratio is not None:
        entries.append(
            ("Treynor", "Beta", "Fund within portfolio",
             f"{ratios.treynor_ratio:.4f}")
        )

    if ratios.information_ratio is not None:
        entries.append(
            ("Information Ratio", "Tracking Error", "Active vs passive debate",
             f"{ratios.information_ratio:.3f}")
        )

    for name, risk, use, value in entries:
        print(_row([name, risk, use, value], widths))

    print(_separator(widths, BL, BT, BR))
    print()

# ─────────────────────────────────────────────────────────
# ADDITIONS FOR SECTION 3 — PORTFOLIO ANALYSIS DISPLAY
# ─────────────────────────────────────────────────────────

from data.models import (
    PortfolioAnalysisReport,
    SectorAnalysis,
    ConcentrationAnalysis,
    MarketCapBreakdown,
    StyleBoxPosition,
    PortfolioOverlap,
    PortfolioSnapshot,
)


def print_portfolio_report(report: PortfolioAnalysisReport) -> None:
    """Render the full portfolio analysis report to stdout."""

    # ── Header ──
    print()
    print("=" * 90)
    print("   PORTFOLIO-LEVEL ANALYSIS")
    print(f"   Fund : {report.scheme_name}")
    print(f"   As of: {report.as_of_date}")
    print("=" * 90)

    # ── 1. Valuation Summary ──
    if report.valuation_summary:
        _print_valuation_summary(report.valuation_summary)

    # ── 2. Style Box ──
    if report.style_box:
        _print_style_box(report.style_box)

    # ── 3. Market Cap Breakdown ──
    if report.market_cap:
        _print_market_cap(report.market_cap)

    # ── 4. Sector Allocation ──
    if report.sector_analysis:
        _print_sector_table(report.sector_analysis)

    # ── 5. Concentration ──
    if report.concentration:
        _print_concentration(report.concentration)

    # ── 6. Overlap ──
    if report.overlaps:
        _print_overlaps(report.overlaps)

    # ── 7. Interpretation ──
    if report.interpretation:
        print()
        print("=" * 90)
        print("   AUTOMATED INTERPRETATION")
        print("=" * 90)
        for line in report.interpretation:
            print(f"   {line}")
        print()


def _print_valuation_summary(valuation: dict) -> None:
    """Print portfolio valuation metrics."""
    print()
    print("─" * 90)
    print("   PORTFOLIO VALUATION METRICS")
    print("─" * 90)
    print()

    metrics = []
    for label, value in valuation.items():
        if value is not None:
            if label in ("P/E", "P/B"):
                metrics.append(f"  {label}: {value:.1f}")
            else:
                metrics.append(f"  {label}: {value:.1f}%")

    print("   " + "  │  ".join(metrics))
    print()


def _print_style_box(style: StyleBoxPosition) -> None:
    """Print the 3×3 equity style box with current position marked."""
    print()
    print("─" * 90)
    print("   EQUITY STYLE BOX")
    print("─" * 90)
    print()

    # Determine position
    if style.size_score >= 2.5:
        size_row = 0  # large
    elif style.size_score >= 1.5:
        size_row = 1  # mid
    else:
        size_row = 2  # small

    if style.value_score <= 2.0:
        val_col = 0  # value
    elif style.value_score <= 3.5:
        val_col = 1  # blend
    else:
        val_col = 2  # growth

    labels_top = ["VALUE", "BLEND", "GROWTH"]
    labels_side = ["LARGE CAP", "MID CAP  ", "SMALL CAP"]

    print(f"                     {labels_top[0]:^14} {labels_top[1]:^14} {labels_top[2]:^14}")
    print(f"                   ┌──────────────┬──────────────┬──────────────┐")

    for row in range(3):
        cells = []
        for col in range(3):
            if row == size_row and col == val_col:
                cells.append("    ★ HERE   ")
            else:
                cells.append("             ")

        print(
            f"   {labels_side[row]}  │{cells[0]}│{cells[1]}│{cells[2]}│"
        )
        if row < 2:
            print(
                f"                   ├──────────────┼──────────────┼──────────────┤"
            )

    print(f"                   └──────────────┴──────────────┴──────────────┘")
    print(f"\n   📍 Position: {style.style_label}")
    print()


def _print_market_cap(mc: MarketCapBreakdown) -> None:
    """Print market cap breakdown with visual bar."""
    print()
    print("─" * 90)
    print("   MARKET CAP BREAKDOWN")
    print("─" * 90)
    print()

    total = mc.large_cap_pct + mc.mid_cap_pct + mc.small_cap_pct
    if total <= 0:
        return

    bar_width = 50

    # Fund bar
    large_blocks = int(mc.large_cap_pct / total * bar_width)
    mid_blocks = int(mc.mid_cap_pct / total * bar_width)
    small_blocks = bar_width - large_blocks - mid_blocks

    fund_bar = "█" * large_blocks + "▓" * mid_blocks + "░" * small_blocks

    print(f"   Fund:      │{fund_bar}│")
    print(
        f"              Large: {mc.large_cap_pct:.1f}%   "
        f"Mid: {mc.mid_cap_pct:.1f}%   "
        f"Small: {mc.small_cap_pct:.1f}%"
    )

    # Benchmark bar (if available)
    if mc.bench_large_pct is not None:
        b_total = mc.bench_large_pct + mc.bench_mid_pct + mc.bench_small_pct
        if b_total > 0:
            b_large = int(mc.bench_large_pct / b_total * bar_width)
            b_mid = int(mc.bench_mid_pct / b_total * bar_width)
            b_small = bar_width - b_large - b_mid
            bench_bar = "█" * b_large + "▓" * b_mid + "░" * b_small

            print(f"\n   Benchmark: │{bench_bar}│")
            print(
                f"              Large: {mc.bench_large_pct:.1f}%   "
                f"Mid: {mc.bench_mid_pct:.1f}%   "
                f"Small: {mc.bench_small_pct:.1f}%"
            )

    print(f"\n   █ Large Cap  ▓ Mid Cap  ░ Small Cap")

    if mc.weighted_avg_mcap_cr:
        print(f"   Weighted Avg Market Cap: ₹{mc.weighted_avg_mcap_cr:,.0f} Cr")
    if mc.bias:
        print(f"   Bias: {mc.bias}")
    print()


def _print_sector_table(sa: SectorAnalysis) -> None:
    """Print sector allocation table."""
    print()
    print("─" * 90)
    print("   SECTOR ALLOCATION")
    print("─" * 90)
    print()

    has_bench = any(s.benchmark_weight_pct is not None for s in sa.sectors)

    if has_bench:
        headers = ["Sector", "Fund %", "Bench %", "Over/Under", "#Stocks", "Visual"]
        widths = [22, 8, 8, 11, 7, 24]
    else:
        headers = ["Sector", "Fund %", "#Stocks", "Top Holding", "Visual"]
        widths = [22, 8, 7, 22, 24]

    print(_separator(widths, TL, TT, TR))
    print(_row(headers, widths))
    print(_separator(widths, LT, CR, RT))

    for s in sa.sectors:
        # Visual bar
        bar_len = min(int(s.fund_weight_pct / 2), 20)
        bar = "█" * bar_len

        if has_bench:
            bench_str = (
                f"{s.benchmark_weight_pct:.1f}%"
                if s.benchmark_weight_pct is not None else "N/A"
            )
            ow_str = (
                f"{s.overweight_pct:+.1f}%"
                if s.overweight_pct is not None else "N/A"
            )
            cols = [
                s.sector,
                f"{s.fund_weight_pct:.1f}%",
                bench_str,
                ow_str,
                str(s.num_stocks),
                bar,
            ]
        else:
            top = f"{s.top_stock}" if s.top_stock else "N/A"
            cols = [
                s.sector,
                f"{s.fund_weight_pct:.1f}%",
                str(s.num_stocks),
                top[:22],
                bar,
            ]

        print(_row(cols, widths))

    print(_separator(widths, BL, BT, BR))

    # Summary line
    print(
        f"\n   Top 3 Sectors: {sa.top_3_concentration_pct:.1f}% | "
        f"HHI: {sa.hhi:.0f} | "
        f"Sectors: {sa.num_sectors}"
    )
    if sa.active_share_sector_pct is not None:
        print(f"   Sector Active Share: {sa.active_share_sector_pct:.1f}%")
    print()


def _print_concentration(con: ConcentrationAnalysis) -> None:
    """Print concentration analysis card."""
    width = 88

    print(f"┌{'─' * width}┐")
    title = f"  PORTFOLIO CONCENTRATION — {con.concentration_grade}"
    print(f"│{title:<{width}}│")
    print(f"├{'─' * width}┤")

    lines = [
        ("Total Stocks", f"{con.total_stocks}"),
        ("Largest Holding", f"{con.largest_holding_name} ({con.largest_holding_pct:.1f}%)"),
        ("Top 5 Holdings", f"{con.top_5_weight_pct:.1f}%"),
        ("Top 10 Holdings", f"{con.top_10_weight_pct:.1f}%"),
        ("Top 15 Holdings", f"{con.top_15_weight_pct:.1f}%"),
        ("Top 20 Holdings", f"{con.top_20_weight_pct:.1f}%"),
        ("HHI (Holdings)", f"{con.hhi_holdings:.0f}"),
    ]

    for label, value in lines:
        line = f"    {label:<30} {value:>20}"
        print(f"│{line:<{width}}│")

    # Concentration visual
    print(f"│{'  ' + '─' * 45:<{width}}│")

    # Show top 10 as percentage bar of total
    bar_width = 50
    top10_blocks = int(con.top_10_weight_pct / 100 * bar_width)
    rest_blocks = bar_width - top10_blocks

    bar_line = f"    Top 10: {'█' * top10_blocks}{'░' * rest_blocks}  {con.top_10_weight_pct:.1f}%"
    print(f"│{bar_line:<{width}}│")
    legend = f"    █ Top 10 holdings  ░ Remaining {con.total_stocks - 10} holdings"
    print(f"│{legend:<{width}}│")

    print(f"└{'─' * width}┘")
    print()


def _print_overlaps(overlaps: List[PortfolioOverlap]) -> None:
    """Print portfolio overlap analysis."""
    print()
    print("─" * 90)
    print("   PORTFOLIO OVERLAP ANALYSIS")
    print("─" * 90)
    print()

    for ovl in overlaps:
        # Overlap bar
        bar_width = 40
        overlap_blocks = int(ovl.overlap_pct / 100 * bar_width)
        unique_blocks = bar_width - overlap_blocks

        if ovl.overlap_pct > 60:
            grade_icon = "❌"
        elif ovl.overlap_pct > 40:
            grade_icon = "⚠️"
        elif ovl.overlap_pct > 20:
            grade_icon = "🔶"
        else:
            grade_icon = "✅"

        print(f"   {grade_icon} vs {ovl.fund_b_name}")
        print(f"      Overlap: {ovl.overlap_pct:.1f}% | Common: {ovl.common_stocks} stocks | Grade: {ovl.overlap_grade}")

        bar = "█" * overlap_blocks + "░" * unique_blocks
        print(f"      │{bar}│ {ovl.overlap_pct:.1f}%")
        print(f"      █ Overlapping  ░ Unique")

        # Top common holdings
        if ovl.top_common_holdings:
            print(f"\n      Top common holdings:")
            for name, wt_a, wt_b in ovl.top_common_holdings[:5]:
                min_w = min(wt_a, wt_b)
                print(
                    f"        {name:<30}  "
                    f"Fund A: {wt_a:.1f}%  Fund B: {wt_b:.1f}%  "
                    f"(overlap: {min_w:.1f}%)"
                )

        print()

# ─────────────────────────────────────────────────────────
# ADDITIONS FOR SECTION 4 — STRUCTURAL ANALYSIS DISPLAY
# ─────────────────────────────────────────────────────────

from data.models import (
    StructuralReport,
    ExpenseRatioAnalysis,
    TurnoverAnalysis,
    FundManagerAnalysis,
    AUMAnalysis,
)


def print_structural_report(report: StructuralReport) -> None:
    """Render the full structural analysis report to stdout."""

    # ── Header ──
    print()
    print("=" * 90)
    print("   STRUCTURAL & QUALITATIVE ANALYSIS")
    print(f"   Fund : {report.scheme_name}")
    print(f"   Category: {report.scheme_category}")
    print(f"   As of: {report.as_of_date}")
    print("=" * 90)

    # ── 1. Expense Ratio Card ──
    if report.expense_analysis:
        _print_expense_card(report.expense_analysis)

    # ── 2. Turnover Card ──
    if report.turnover_analysis:
        _print_turnover_card(report.turnover_analysis)

    # ── 3. Manager Card ──
    if report.manager_analysis:
        _print_manager_card(report.manager_analysis)

    # ── 4. AUM Card ──
    if report.aum_analysis:
        _print_aum_card(report.aum_analysis)

    # ── 5. Overall Score ──
    if report.structural_score is not None:
        _print_structural_score(report.structural_score, report.structural_grade)

    # ── 6. Interpretation ──
    if report.interpretation:
        print()
        print("=" * 90)
        print("   AUTOMATED INTERPRETATION")
        print("=" * 90)
        for line in report.interpretation:
            print(f"   {line}")
        print()


def _print_expense_card(exp: ExpenseRatioAnalysis) -> None:
    """Print expense ratio analysis card."""
    width = 88

    print()
    print(f"┌{'─' * width}┐")
    print(f"│{'  EXPENSE RATIO (TER) ANALYSIS — ' + exp.expense_grade:<{width}}│")
    print(f"├{'─' * width}┤")

    # Current TER
    if exp.current_direct_pct is not None:
        line = f"    Direct Plan TER:              {exp.current_direct_pct:.2f}%"
        print(f"│{line:<{width}}│")
    if exp.current_regular_pct is not None:
        line = f"    Regular Plan TER:             {exp.current_regular_pct:.2f}%"
        print(f"│{line:<{width}}│")
        diff = exp.current_regular_pct - (exp.current_direct_pct or 0)
        line = f"    Commission Drag:              {diff:.2f}%"
        print(f"│{line:<{width}}│")

    if exp.category_avg_direct_pct is not None:
        print(f"│{'  ' + '─' * 45:<{width}}│")
        line = f"    Category Avg (Direct):        {exp.category_avg_direct_pct:.2f}%"
        print(f"│{line:<{width}}│")
        if exp.cost_difference_pct is not None:
            if exp.cost_difference_pct < 0:
                line = f"    ✅ {abs(exp.cost_difference_pct):.2f}% CHEAPER than category"
            else:
                line = f"    ⚠️  {exp.cost_difference_pct:.2f}% ABOVE category average"
            print(f"│{line:<{width}}│")

    # Cost simulation table
    if exp.cost_simulations:
        print(f"│{'  ' + '─' * 45:<{width}}│")
        print(f"│{'  LONG-TERM COST IMPACT (₹10 Lakh at 14% gross return)':<{width}}│")
        print(f"│{'  ' + '─' * 45:<{width}}│")

        # Header
        sim_header = f"    {'Horizon':<10} {'Direct':>14} {'Regular':>14} {'Index':>14} {'Cost Drag':>14}"
        print(f"│{sim_header:<{width}}│")

        for horizon, plans in exp.cost_simulations.items():
            direct_final = plans.get("Direct Plan", {}).get("final_value", 0)
            regular_final = plans.get("Regular Plan", {}).get("final_value", 0)
            index_final = plans.get("Index Fund (0.15%)", {}).get("final_value", 0)
            cost_drag = plans.get("Direct Plan", {}).get("cost_drag", 0)

            sim_line = (
                f"    {horizon:<10} "
                f"₹{direct_final:>11,.0f} "
                f"₹{regular_final:>11,.0f} "
                f"₹{index_final:>11,.0f} "
                f"₹{cost_drag:>11,.0f}"
            )
            print(f"│{sim_line:<{width}}│")

    if exp.alpha_breakeven_pct is not None:
        print(f"│{'  ' + '─' * 45:<{width}}│")
        line = f"    Alpha Break-Even vs Index: ≥{exp.alpha_breakeven_pct:.2f}% alpha needed"
        print(f"│{line:<{width}}│")

    print(f"└{'─' * width}┘")
    print()


def _print_turnover_card(trn: TurnoverAnalysis) -> None:
    """Print turnover analysis card."""
    width = 88

    print(f"┌{'─' * width}┐")
    print(f"│{'  PORTFOLIO TURNOVER ANALYSIS — ' + trn.turnover_grade:<{width}}│")
    print(f"├{'─' * width}┤")

    line = f"    Portfolio Turnover:          {trn.turnover_ratio_pct:.0f}%"
    print(f"│{line:<{width}}│")

    if trn.category_avg_turnover_pct:
        line = f"    Category Average:            {trn.category_avg_turnover_pct:.0f}%"
        print(f"│{line:<{width}}│")

    # Turnover visual bar
    bar_width = 50
    blocks = min(int(trn.turnover_ratio_pct / 5), bar_width)
    bar_chars = "█" * blocks + "░" * (bar_width - blocks)
    bar_line = f"    │{bar_chars}│"
    print(f"│{bar_line:<{width}}│")
    scale = f"    0%{'':>20}100%{'':>15}200%+"
    print(f"│{scale:<{width}}│")

    print(f"│{'  ' + '─' * 45:<{width}}│")
    print(f"│{'  HIDDEN COST ESTIMATION':<{width}}│")

    costs = [
        ("Brokerage drag",   f"{trn.estimated_brokerage_drag_pct:.3f}%"),
        ("Impact cost drag", f"{trn.estimated_impact_cost_drag_pct:.3f}%"),
        ("STT drag",         f"{trn.estimated_stt_drag_pct:.3f}%"),
    ]
    for label, value in costs:
        line = f"      {label:<25} {value:>10}"
        print(f"│{line:<{width}}│")

    print(f"│{'      ' + '─' * 35:<{width}}│")
    total_line = f"      Total hidden cost:       {trn.total_hidden_cost_pct:.3f}%"
    print(f"│{total_line:<{width}}│")
    eff_line = f"      Effective total (TER+):   {trn.effective_total_cost_pct:.3f}%"
    print(f"│{eff_line:<{width}}│")

    print(f"└{'─' * width}┘")
    print()


def _print_manager_card(mgr: FundManagerAnalysis) -> None:
    """Print fund manager analysis card."""
    width = 88

    print(f"┌{'─' * width}┐")
    title = f"  FUND MANAGER ANALYSIS — Tenure: {mgr.tenure_grade} | Stability: {mgr.stability_grade}"
    print(f"│{title:<{width}}│")
    print(f"├{'─' * width}┤")

    # Current managers
    print(f"│{'  CURRENT MANAGER(S)':<{width}}│")
    for m in mgr.current_managers:
        line1 = f"    👤 {m.name}"
        if m.designation:
            line1 += f" — {m.designation}"
        print(f"│{line1:<{width}}│")

        details = []
        if m.tenure_years is not None:
            details.append(f"Tenure: {m.tenure_years:.1f}y")
        if m.total_experience_years:
            details.append(f"Exp: {m.total_experience_years}y")
        if m.num_funds_managed:
            details.append(f"Funds: {m.num_funds_managed}")
        if m.qualification:
            details.append(f"Qual: {m.qualification}")

        if details:
            detail_line = f"       {' │ '.join(details)}"
            print(f"│{detail_line:<{width}}│")

    # History
    if mgr.manager_history:
        print(f"│{'  ' + '─' * 45:<{width}}│")
        print(f"│{'  MANAGER HISTORY':<{width}}│")

        for h in mgr.manager_history:
            h_line = (
                f"    {h.get('name', '?'):<25} "
                f"{h.get('from', '?'):<12} → {h.get('to', '?'):<12} "
                f"({h.get('tenure_years', '?')}y)"
            )
            print(f"│{h_line:<{width}}│")

    print(f"│{'  ' + '─' * 45:<{width}}│")
    summary = f"    Changes: {mgr.total_manager_changes} | Avg Tenure: {mgr.avg_manager_tenure_years or 'N/A'}y"
    print(f"│{summary:<{width}}│")

    print(f"└{'─' * width}┘")
    print()


def _print_aum_card(aum_a: AUMAnalysis) -> None:
    """Print AUM analysis card."""
    width = 88

    print(f"┌{'─' * width}┐")
    title = f"  AUM ANALYSIS — {aum_a.size_grade}"
    print(f"│{title:<{width}}│")
    print(f"├{'─' * width}┤")

    if aum_a.current_aum_cr:
        line = f"    Current AUM: ₹{aum_a.current_aum_cr:,.0f} Cr"
        print(f"│{line:<{width}}│")

    range_line = (
        f"    Ideal Range: ₹{aum_a.ideal_aum_range_cr[0]:,.0f} — "
        f"₹{aum_a.ideal_aum_range_cr[1]:,.0f} Cr"
    )
    print(f"│{range_line:<{width}}│")

    if aum_a.aum_trend:
        trend_line = f"    Trend: {aum_a.aum_trend}"
        if aum_a.aum_growth_1y_pct is not None:
            trend_line += f" ({aum_a.aum_growth_1y_pct:+.1f}% 1Y growth)"
        print(f"│{trend_line:<{width}}│")

    # AUM history visual (simple trend line)
    if aum_a.aum_history and len(aum_a.aum_history) >= 3:
        print(f"│{'  ' + '─' * 45:<{width}}│")
        print(f"│{'  AUM TREND (most recent first)':<{width}}│")

        aum_values = [h.get("aum_cr", 0) for h in aum_a.aum_history[:8]]
        max_aum = max(aum_values) if aum_values else 1
        bar_max = 40

        for i, entry in enumerate(aum_a.aum_history[:8]):
            date_str = entry.get("date", "?")
            aum_val = entry.get("aum_cr", 0)
            bar_len = int(aum_val / max_aum * bar_max) if max_aum > 0 else 0
            bar = "█" * bar_len

            bar_line = f"    {date_str:<12} ₹{aum_val:>8,.0f} Cr │{bar}"
            print(f"│{bar_line:<{width}}│")

    if aum_a.size_concern:
        print(f"│{'  ' + '─' * 45:<{width}}│")
        concern_line = f"    ⚠️  {aum_a.size_concern}"
        # Wrap long lines
        while len(concern_line) > width:
            print(f"│{concern_line[:width]}│")
            concern_line = "    " + concern_line[width:]
        print(f"│{concern_line:<{width}}│")

    print(f"└{'─' * width}┘")
    print()


def _print_structural_score(score: float, grade: str) -> None:
    """Print overall structural quality score."""
    print()
    print("─" * 90)
    print("   OVERALL STRUCTURAL QUALITY SCORE")
    print("─" * 90)

    grade_icons = {
        "EXCELLENT": "🏆", "GOOD": "✅", "AVERAGE": "🔶",
        "BELOW AVERAGE": "⚠️", "POOR": "❌",
    }
    icon = grade_icons.get(grade, "")

    print(f"\n   {icon}  {score:.1f} / 100  —  {grade}")

    # Score bar
    bar_width = 50
    filled = int(score / 100 * bar_width)

    # Colour coding segments
    segments = [
        (20, "░"),   # 0-20: Poor
        (15, "▒"),   # 20-35: Below Average
        (15, "▓"),   # 35-50: Average
        (15, "█"),   # 50-65: Good
        (35, "█"),   # 65-100: Excellent
    ]

    bar = ""
    remaining = filled
    for seg_width, char in segments:
        seg_blocks = min(int(seg_width / 100 * bar_width), remaining)
        bar += char * seg_blocks
        remaining -= seg_blocks
        if remaining <= 0:
            break

    bar += "░" * (bar_width - len(bar))

    print(f"   │{bar}│")
    print(f"   0    20   35   50   65   80   100")
    print(f"   POOR  B.AVG AVG  GOOD  EXCELLENT")
    print()

    # ─────────────────────────────────────────────────────────
# ADDITIONS FOR SECTION 7 — SCORING & RANKING DISPLAY
# ─────────────────────────────────────────────────────────

from data.models import FundScore, RankingTable, MasterReport


def print_fund_score(score: FundScore) -> None:
    """Render a single fund's score card."""
    width = 88

    stars = "★" * score.star_rating + "☆" * (5 - score.star_rating)

    print()
    print(f"┌{'─' * width}┐")
    title = f"  {stars}  FUND SCORECARD  —  {score.rating_label}"
    print(f"│{title:<{width}}│")
    print(f"│{'  ' + score.scheme_name:<{width}}│")
    print(f"│{'  Profile: ' + score.profile.profile_name + ' │ Age: ' + str(score.fund_age_years) + 'y':<{width}}│")
    print(f"├{'─' * width}┤")

    # ── Final Score ──
    score_line = f"  FINAL SCORE: {score.final_score:.1f} / 100"
    print(f"│{score_line:<{width}}│")

    bar_width = 50
    filled = int(score.final_score / 100 * bar_width)
    bar = "█" * filled + "░" * (bar_width - filled)
    bar_line = f"  │{bar}│"
    print(f"│{bar_line:<{width}}│")

    print(f"│{'  ' + '─' * 50:<{width}}│")

    # ── Category sub-scores ──
    print(f"│{'  CATEGORY BREAKDOWN':<{width}}│")

    categories = [
        ("Performance", score.performance_score, score.profile.performance_weight),
        ("Risk-Adjusted", score.risk_adjusted_score, score.profile.risk_adjusted_weight),
        ("Risk Management", score.risk_management_score, score.profile.risk_management_weight),
        ("Structural", score.structural_score, score.profile.structural_weight),
    ]

    for label, sc, wt in categories:
        bar_len = int(sc / 100 * 25)
        bar = "█" * bar_len + "░" * (25 - bar_len)
        cat_line = f"    {label:<18} │{bar}│ {sc:>5.1f}  (wt: {wt:.0%})"
        print(f"│{cat_line:<{width}}│")

    # ── Raw vs Final ──
    print(f"│{'  ' + '─' * 50:<{width}}│")
    raw_line = f"  Raw Composite: {score.raw_composite:.1f}  │  Penalties: {score.total_penalty:+.0f}  │  Bonuses: {score.total_bonus:+.0f}"
    print(f"│{raw_line:<{width}}│")

    # ── Bonuses ──
    if score.bonuses:
        print(f"│{'  ' + '─' * 50:<{width}}│")
        print(f"│{'  ✅ STRENGTHS':<{width}}│")
        for b in score.bonuses:
            bonus_line = f"    +{b.points:>2}  {b.label}: {b.reason}"
            # Truncate if too long
            if len(bonus_line) > width:
                bonus_line = bonus_line[:width - 3] + "..."
            print(f"│{bonus_line:<{width}}│")

    # ── Penalties ──
    if score.penalties:
        print(f"│{'  ' + '─' * 50:<{width}}│")
        print(f"│{'  ⚠️  CONCERNS':<{width}}│")
        for p in score.penalties:
            pen_line = f"    {p.points:>3}  {p.label}: {p.reason}"
            if len(pen_line) > width:
                pen_line = pen_line[:width - 3] + "..."
            print(f"│{pen_line:<{width}}│")

    # ── Top metrics ──
    print(f"│{'  ' + '─' * 50:<{width}}│")
    print(f"│{'  TOP METRICS':<{width}}│")

    sorted_metrics = sorted(score.metric_scores, key=lambda m: m.percentile_score, reverse=True)
    for m in sorted_metrics[:6]:
        raw_str = f"{m.raw_value:+.2f}" if m.raw_value is not None else "N/A"
        met_line = f"    {m.metric_name:<22} Raw: {raw_str:>8}  │  Percentile: {m.percentile_score:>5.1f}"
        print(f"│{met_line:<{width}}│")

    # ── Recommendation ──
    print(f"│{'  ' + '─' * 50:<{width}}│")
    rec_line = f"  💡 {score.recommendation}"
    print(f"│{rec_line:<{width}}│")

    print(f"└{'─' * width}┘")
    print()


def print_ranking_table(ranking: RankingTable) -> None:
    """Render the multi-fund ranking table."""

    print()
    print("=" * 90)
    print(f"   FUND RANKING — {ranking.profile.profile_name.upper()} PROFILE")
    print(f"   {ranking.profile.description}")
    print(f"   Category: {ranking.category} | As of: {ranking.as_of_date}")
    print("=" * 90)
    print()

    # ── Ranking table ──
    header = (
        f"  {'#':>3} │ {'Fund':<36} │ {'Score':>6} │ {'Stars':>7} │ "
        f"{'Perf':>5} │ {'Risk':>5} │ {'RiskM':>5} │ {'Str':>5} │ {'Rating':<12}"
    )
    print(header)
    print("  " + "─" * (len(header) - 2))

    for i, fs in enumerate(ranking.fund_scores, 1):
        if fs.disqualified:
            stars_str = "  DQ"
        else:
            stars_str = "★" * fs.star_rating + "☆" * (5 - fs.star_rating)

        name = fs.scheme_name[:36]
        rating = fs.rating_label if not fs.disqualified else "DISQUALIFIED"

        print(
            f"  {i:>3} │ {name:<36} │ "
            f"{fs.final_score:>5.1f} │ "
            f"{stars_str:>7} │ "
            f"{fs.performance_score:>5.1f} │ "
            f"{fs.risk_adjusted_score:>5.1f} │ "
            f"{fs.risk_management_score:>5.1f} │ "
            f"{fs.structural_score:>5.1f} │ "
            f"{rating:<12}"
        )

    print()

    # ── Top Picks Detail ──
    if ranking.top_picks:
        print("─" * 90)
        print("   🏆 TOP PICKS")
        print("─" * 90)

        for i, pick in enumerate(ranking.top_picks, 1):
            stars = "★" * pick.star_rating + "☆" * (5 - pick.star_rating)
            print(f"\n   {i}. {pick.scheme_name}")
            print(f"      {stars}  Score: {pick.final_score:.1f}/100  —  {pick.rating_label}")
            print(f"      {pick.recommendation}")

            # Strengths
            if pick.bonuses:
                strengths = " │ ".join(b.label for b in pick.bonuses[:3])
                print(f"      Strengths: {strengths}")

            # Concerns
            if pick.penalties:
                concerns = " │ ".join(p.label for p in pick.penalties[:2])
                print(f"      Concerns: {concerns}")

        print()

    # ── Interpretation ──
    if ranking.interpretation:
        print("─" * 90)
        print("   ANALYSIS NOTES")
        print("─" * 90)
        for line in ranking.interpretation:
            print(f"   {line}")
        print()


def print_master_report(report: MasterReport) -> None:
    """Render the complete master report."""

    # Summary first
    if report.summary:
        print()
        for line in report.summary:
            print(f"   {line}")

    # Score card
    if report.fund_score:
        print_fund_score(report.fund_score)