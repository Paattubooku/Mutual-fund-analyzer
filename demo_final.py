#!/usr/bin/env python3
"""
demo_final.py
─────────────
COMPLETE SYSTEM DEMONSTRATION

This is the final integrated demo showing the entire
Mutual Fund Analysis Framework in action:

  1. Analyse a single fund end-to-end
  2. Compare and rank multiple funds
  3. Test different investment profiles
  4. Display the complete scorecard and ranking

Run:
    python demo_final.py
"""

import os
import sys
import time

import config

from pipeline.master_pipeline import MasterPipeline
from metrics.scoring_engine import get_investment_profile
from utils.formatter import (
    print_master_report,
    print_fund_score,
    print_ranking_table,
    print_trailing_report,
    print_rolling_report,
    print_consistency_report,
    print_risk_adjusted_report,
)


# ── Auto-detect offline mode ──
# Set MF_OFFLINE=1 environment variable to skip all API calls
_OFFLINE_ENV = os.environ.get("MF_OFFLINE", "").strip().lower() in ("1", "true", "yes")
if _OFFLINE_ENV:
    config.OFFLINE_MODE = True
    print("\n   ⚡ OFFLINE MODE — using synthetic fixture data")


# ────────────────────────────────────────────────
# CONFIGURATION
# ────────────────────────────────────────────────

# Funds to analyse
FUND_CODES = {
    "Parag Parikh Flexi Cap":    122639,
    "Mirae Asset Large Cap":     118834,
    "Axis Bluechip":             120503,
    "SBI Small Cap":             125497,
    "Kotak Emerging Equity":     120505,
}

PRIMARY_FUND = 122639          # detailed analysis target
PROFILE = "growth"             # investment profile


if getattr(config, "OFFLINE_MODE", False):
    FUND_CODES = {
        "Fixture Flexi Cap": 100001,
        "Fixture Large Cap": 100002,
        "Fixture Small Cap": 100003,
    }
    PRIMARY_FUND = 100001


def main():
    pipeline = MasterPipeline(offline_mode=getattr(config, 'OFFLINE_MODE', False))

    print("\n" + "█" * 90)
    print("█" + " " * 88 + "█")
    print("█" + "   MUTUAL FUND ANALYSIS FRAMEWORK — COMPLETE SYSTEM DEMO".center(88) + "█")
    print("█" + " " * 88 + "█")
    print("█" * 90)

    # ══════════════════════════════════════════
    # PART 1: Single Fund Deep Dive
    # ══════════════════════════════════════════
    print(f"\n{'═' * 90}")
    print(f"   PART 1: SINGLE FUND DEEP DIVE — Scheme {PRIMARY_FUND}")
    print(f"{'═' * 90}")

    t0 = time.time()

    print(f"\n   Running complete analysis pipeline...")
    try:
        report = pipeline.analyse_fund(
            scheme_code=PRIMARY_FUND,
            profile_name=PROFILE,
        )
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        sys.exit(1)

    elapsed = time.time() - t0
    print(f"   ✓ Complete in {elapsed:.1f} seconds")

    # Display executive summary + scorecard
    print_master_report(report)

    # Display component reports
    if report.trailing_returns:
        print_trailing_report(report.trailing_returns)

    if report.risk_adjusted:
        print_risk_adjusted_report(report.risk_adjusted)

    # ══════════════════════════════════════════
    # PART 2: Multi-Fund Ranking
    # ══════════════════════════════════════════
    print(f"\n{'═' * 90}")
    print(f"   PART 2: MULTI-FUND RANKING — {PROFILE.upper()} PROFILE")
    print(f"{'═' * 90}")

    codes = list(FUND_CODES.values())

    print(f"\n   Analysing {len(codes)} funds...")
    t0 = time.time()

    try:
        ranking = pipeline.compare_funds(
            scheme_codes=codes,
            profile_name=PROFILE,
        )
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        ranking = None

    if ranking:
        elapsed = time.time() - t0
        print(f"   ✓ Ranked {len(ranking.fund_scores)} funds in {elapsed:.1f} seconds")
        print_ranking_table(ranking)

        # Detailed scorecard for #1 fund
        if ranking.top_picks:
            print(f"\n{'═' * 90}")
            print(f"   DETAILED SCORECARD: #{1} RANKED FUND")
            print(f"{'═' * 90}")
            print_fund_score(ranking.top_picks[0])

    # ══════════════════════════════════════════
    # PART 3: Profile Sensitivity
    # ══════════════════════════════════════════
    print(f"\n{'═' * 90}")
    print(f"   PART 3: HOW RANKINGS CHANGE WITH INVESTMENT PROFILE")
    print(f"{'═' * 90}")

    if ranking:
        _profile_sensitivity(pipeline, codes)

    print(f"\n{'█' * 90}")
    print(f"{'█' + '   ANALYSIS COMPLETE'.center(88) + '█'}")
    print(f"{'█' * 90}\n")


def _profile_sensitivity(pipeline, codes):
    """Show how rankings change with different profiles."""
    profiles = ["aggressive", "growth", "balanced", "conservative"]

    # Build metrics once (reuse from ranking)
    fund_entries = []
    for code in codes:
        try:
            entry = pipeline._build_fund_entry(code)
            if entry:
                fund_entries.append(entry)
        except Exception:
            pass

    if not fund_entries:
        return

    print()
    print(f"   How does the #1 pick change with investment profile?")
    print()

    header = f"   {'Profile':<15} │ {'#1 Fund':<40} │ {'Score':>6} │ {'Stars':>7}"
    print(header)
    print("   " + "─" * (len(header) - 3))

    from metrics.scoring_engine import rank_funds

    for pname in profiles:
        profile = get_investment_profile(pname)
        ranking = rank_funds(fund_entries, profile)

        if ranking.top_picks:
            top = ranking.top_picks[0]
            stars = "★" * top.star_rating + "☆" * (5 - top.star_rating)
            name = top.scheme_name[:40]
            print(f"   {pname.capitalize():<15} │ {name:<40} │ {top.final_score:>5.1f} │ {stars:>7}")

    print()
    print(
        "   💡 Notice: The same fund can rank differently depending on\n"
        "      your investment goals. There is no universally 'best' fund —\n"
        "      only the best fund FOR YOUR PROFILE."
    )
    print()

    # Weight comparison table
    print(f"\n   Profile weights used:")
    print(f"   {'Profile':<15} │ {'Perf':>6} │ {'Risk-Adj':>8} │ {'RiskMgmt':>8} │ {'Struct':>6}")
    print("   " + "─" * 55)
    for pname in profiles:
        p = get_investment_profile(pname)
        print(
            f"   {pname.capitalize():<15} │ "
            f"{p.performance_weight:>5.0%} │ "
            f"{p.risk_adjusted_weight:>7.0%} │ "
            f"{p.risk_management_weight:>7.0%} │ "
            f"{p.structural_weight:>5.0%}"
        )
    print()


if __name__ == "__main__":
    main()