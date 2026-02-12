"""
data/fund_metadata_provider.py
──────────────────────────────
Provides structural/qualitative metadata for funds.

This data is NOT available from the MFAPI.  In production,
it would come from AMFI factsheets, AMC websites, or
commercial data feeds (Morningstar, Value Research).

This module provides:
    1. Category-level benchmark data (average TER, turnover, etc.)
    2. Sample fund metadata for demonstration
    3. AUM size-strategy compatibility rules
"""

from __future__ import annotations

import datetime as dt
from typing import Optional, Dict, List, Tuple

from data.models import (
    FundManagerInfo,
    ExitLoadInfo,
    FundHouseInfo,
)


# ────────────────────────────────────────────────
# CATEGORY BENCHMARKS (approximate industry data)
# ────────────────────────────────────────────────

CATEGORY_BENCHMARKS: Dict[str, Dict] = {
    "large cap": {
        "avg_ter_direct": 0.75,
        "avg_ter_regular": 1.65,
        "avg_turnover": 45.0,
        "ideal_aum_min": 2000,
        "ideal_aum_max": 50000,
        "concern_aum": 80000,
    },
    "flexi cap": {
        "avg_ter_direct": 0.72,
        "avg_ter_regular": 1.55,
        "avg_turnover": 42.0,
        "ideal_aum_min": 2000,
        "ideal_aum_max": 30000,
        "concern_aum": 50000,
    },
    "mid cap": {
        "avg_ter_direct": 0.68,
        "avg_ter_regular": 1.58,
        "avg_turnover": 40.0,
        "ideal_aum_min": 1000,
        "ideal_aum_max": 15000,
        "concern_aum": 25000,
    },
    "small cap": {
        "avg_ter_direct": 0.72,
        "avg_ter_regular": 1.68,
        "avg_turnover": 35.0,
        "ideal_aum_min": 500,
        "ideal_aum_max": 8000,
        "concern_aum": 15000,
    },
    "elss": {
        "avg_ter_direct": 0.70,
        "avg_ter_regular": 1.60,
        "avg_turnover": 50.0,
        "ideal_aum_min": 1000,
        "ideal_aum_max": 15000,
        "concern_aum": 20000,
    },
    "multi cap": {
        "avg_ter_direct": 0.65,
        "avg_ter_regular": 1.50,
        "avg_turnover": 45.0,
        "ideal_aum_min": 2000,
        "ideal_aum_max": 25000,
        "concern_aum": 40000,
    },
    "value": {
        "avg_ter_direct": 0.78,
        "avg_ter_regular": 1.62,
        "avg_turnover": 38.0,
        "ideal_aum_min": 1000,
        "ideal_aum_max": 15000,
        "concern_aum": 25000,
    },
    "focused": {
        "avg_ter_direct": 0.70,
        "avg_ter_regular": 1.55,
        "avg_turnover": 48.0,
        "ideal_aum_min": 1000,
        "ideal_aum_max": 15000,
        "concern_aum": 25000,
    },
    "index": {
        "avg_ter_direct": 0.15,
        "avg_ter_regular": 0.40,
        "avg_turnover": 10.0,
        "ideal_aum_min": 500,
        "ideal_aum_max": 100000,
        "concern_aum": 200000,
    },
}


def get_category_benchmark(category: str) -> Optional[Dict]:
    """
    Retrieve category-level benchmark data.
    Matches on partial keyword match.
    """
    cat_lower = category.lower()
    for key, data in CATEGORY_BENCHMARKS.items():
        if key in cat_lower:
            return data
    # Default fallback
    return CATEGORY_BENCHMARKS.get("flexi cap")


# ────────────────────────────────────────────────
# SAMPLE FUND METADATA
# ────────────────────────────────────────────────

def get_sample_metadata_ppfas() -> Dict:
    """Sample metadata for Parag Parikh Flexi Cap Fund."""
    return {
        "scheme_code": 122639,
        "scheme_name": "Parag Parikh Flexi Cap Fund - Direct Growth",
        "category": "Equity Scheme - Flexi Cap Fund",
        "expense_ratio_direct": 0.63,
        "expense_ratio_regular": 1.33,
        "turnover_ratio": 22.0,
        "aum_cr": 72500,
        "aum_history": [
            {"date": "2024-12-31", "aum_cr": 72500},
            {"date": "2024-06-30", "aum_cr": 65200},
            {"date": "2023-12-31", "aum_cr": 52800},
            {"date": "2023-06-30", "aum_cr": 44500},
            {"date": "2022-12-31", "aum_cr": 33200},
            {"date": "2022-06-30", "aum_cr": 28500},
            {"date": "2021-12-31", "aum_cr": 27800},
            {"date": "2021-06-30", "aum_cr": 18500},
            {"date": "2020-12-31", "aum_cr": 12500},
            {"date": "2020-06-30", "aum_cr": 7200},
            {"date": "2019-12-31", "aum_cr": 6800},
        ],
        "managers": [
            {
                "name": "Rajeev Thakkar",
                "designation": "CIO & Fund Manager",
                "start_date": "2013-05-28",
                "experience_years": 25,
                "num_funds": 3,
                "qualification": "CA, CFA",
            },
            {
                "name": "Raunak Onkar",
                "designation": "Co-Fund Manager",
                "start_date": "2013-05-28",
                "experience_years": 18,
                "num_funds": 3,
                "qualification": "MBA Finance",
            },
        ],
        "manager_history": [
            {"name": "Rajeev Thakkar", "from": "2013-05-28", "to": "Present", "tenure_years": 11.6},
            {"name": "Raunak Onkar", "from": "2013-05-28", "to": "Present", "tenure_years": 11.6},
        ],
        "exit_load": [
            {"period": "Within 365 days", "load_pct": 2.0},
            {"period": "365-730 days", "load_pct": 1.0},
            {"period": "After 730 days", "load_pct": 0.0},
        ],
        "lock_in_days": None,
        "fund_house": {
            "name": "PPFAS Mutual Fund",
            "aum_cr": 85000,
            "rank": 18,
            "total_schemes": 5,
            "years_in_operation": 11,
        },
    }


def get_sample_metadata_axis_bluechip() -> Dict:
    """Sample metadata for Axis Bluechip Fund."""
    return {
        "scheme_code": 120503,
        "scheme_name": "Axis Bluechip Fund - Direct Growth",
        "category": "Equity Scheme - Large Cap Fund",
        "expense_ratio_direct": 0.48,
        "expense_ratio_regular": 1.58,
        "turnover_ratio": 35.0,
        "aum_cr": 35200,
        "aum_history": [
            {"date": "2024-12-31", "aum_cr": 35200},
            {"date": "2024-06-30", "aum_cr": 37500},
            {"date": "2023-12-31", "aum_cr": 38200},
            {"date": "2023-06-30", "aum_cr": 36800},
            {"date": "2022-12-31", "aum_cr": 38500},
            {"date": "2022-06-30", "aum_cr": 35200},
            {"date": "2021-12-31", "aum_cr": 40200},
            {"date": "2021-06-30", "aum_cr": 33500},
            {"date": "2020-12-31", "aum_cr": 28500},
        ],
        "managers": [
            {
                "name": "Shreyash Devalkar",
                "designation": "Fund Manager",
                "start_date": "2022-10-01",
                "experience_years": 18,
                "num_funds": 5,
                "qualification": "MBA, CFA",
            },
        ],
        "manager_history": [
            {"name": "Jinesh Gopani", "from": "2017-01-01", "to": "2022-09-30", "tenure_years": 5.7},
            {"name": "Shreyash Devalkar", "from": "2022-10-01", "to": "Present", "tenure_years": 2.3},
        ],
        "exit_load": [
            {"period": "Within 365 days", "load_pct": 1.0},
            {"period": "After 365 days", "load_pct": 0.0},
        ],
        "lock_in_days": None,
        "fund_house": {
            "name": "Axis Mutual Fund",
            "aum_cr": 265000,
            "rank": 7,
            "total_schemes": 72,
            "years_in_operation": 15,
        },
    }


def get_sample_metadata_sbi_smallcap() -> Dict:
    """Sample metadata for SBI Small Cap Fund."""
    return {
        "scheme_code": 125497,
        "scheme_name": "SBI Small Cap Fund - Direct Growth",
        "category": "Equity Scheme - Small Cap Fund",
        "expense_ratio_direct": 0.62,
        "expense_ratio_regular": 1.72,
        "turnover_ratio": 18.0,
        "aum_cr": 28500,
        "aum_history": [
            {"date": "2024-12-31", "aum_cr": 28500},
            {"date": "2024-06-30", "aum_cr": 26200},
            {"date": "2023-12-31", "aum_cr": 22800},
            {"date": "2023-06-30", "aum_cr": 18500},
            {"date": "2022-12-31", "aum_cr": 15200},
            {"date": "2022-06-30", "aum_cr": 14200},
            {"date": "2021-12-31", "aum_cr": 13800},
        ],
        "managers": [
            {
                "name": "R. Srinivasan",
                "designation": "Fund Manager",
                "start_date": "2013-01-01",
                "experience_years": 28,
                "num_funds": 2,
                "qualification": "PGDM, CFA",
            },
        ],
        "manager_history": [
            {"name": "R. Srinivasan", "from": "2013-01-01", "to": "Present", "tenure_years": 12.0},
        ],
        "exit_load": [
            {"period": "Within 365 days", "load_pct": 1.0},
            {"period": "After 365 days", "load_pct": 0.0},
        ],
        "lock_in_days": None,
        "fund_house": {
            "name": "SBI Mutual Fund",
            "aum_cr": 1050000,
            "rank": 1,
            "total_schemes": 145,
            "years_in_operation": 37,
        },
    }


# ────────────────────────────────────────────────
# SAMPLE REGISTRY (for demo retrieval by code)
# ────────────────────────────────────────────────

_SAMPLE_REGISTRY = {
    122639: get_sample_metadata_ppfas,
    120503: get_sample_metadata_axis_bluechip,
    125497: get_sample_metadata_sbi_smallcap,
}


def get_fund_metadata(scheme_code: int) -> Optional[Dict]:
    """Retrieve fund metadata by scheme code."""
    factory = _SAMPLE_REGISTRY.get(scheme_code)
    if factory:
        return factory()
    return None