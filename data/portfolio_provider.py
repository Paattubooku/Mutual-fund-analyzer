"""
data/portfolio_provider.py
──────────────────────────
Portfolio data abstraction layer.

The MFAPI does not provide portfolio holdings data.
This module provides:
    1. An abstract interface for plugging in real data sources
    2. Sample/demo portfolio data for testing and demonstration
    3. Common benchmark portfolio data (Nifty 50, Nifty 500)

In production, implement PortfolioProvider subclasses
that scrape AMFI factsheets, Value Research API, or
Morningstar data feeds.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional, List, Dict

from data.models import (
    StockHolding,
    PortfolioSnapshot,
    BenchmarkPortfolio,
)


# ────────────────────────────────────────────────
# BENCHMARK PORTFOLIOS (approximate, for demo)
# ────────────────────────────────────────────────

NIFTY_50_BENCHMARK = BenchmarkPortfolio(
    name="Nifty 50",
    sector_weights={
        "Financial Services": 37.2,
        "Information Technology": 13.5,
        "Oil & Gas": 11.8,
        "Consumer Goods": 9.2,
        "Automobile": 7.1,
        "Healthcare": 4.8,
        "Metals & Mining": 3.8,
        "Construction": 3.5,
        "Telecom": 3.2,
        "Power": 2.8,
        "Others": 3.1,
    },
    large_cap_pct=100.0,
    mid_cap_pct=0.0,
    small_cap_pct=0.0,
    pe_ratio=23.5,
    pb_ratio=3.8,
)

NIFTY_500_BENCHMARK = BenchmarkPortfolio(
    name="Nifty 500",
    sector_weights={
        "Financial Services": 32.5,
        "Information Technology": 12.8,
        "Oil & Gas": 9.5,
        "Consumer Goods": 10.1,
        "Automobile": 7.8,
        "Healthcare": 6.2,
        "Metals & Mining": 4.5,
        "Construction": 4.2,
        "Telecom": 2.8,
        "Power": 3.5,
        "Chemicals": 2.5,
        "Others": 3.6,
    },
    large_cap_pct=72.0,
    mid_cap_pct=18.0,
    small_cap_pct=10.0,
    pe_ratio=24.8,
    pb_ratio=3.5,
)


def get_benchmark_portfolio(name: str = "nifty_500") -> BenchmarkPortfolio:
    """Get a standard benchmark portfolio."""
    benchmarks = {
        "nifty_50": NIFTY_50_BENCHMARK,
        "nifty_500": NIFTY_500_BENCHMARK,
    }
    return benchmarks.get(name.lower().replace(" ", "_"), NIFTY_500_BENCHMARK)


# ────────────────────────────────────────────────
# SAMPLE PORTFOLIO DATA (for demonstration)
# ────────────────────────────────────────────────

def get_sample_portfolio_ppfas() -> PortfolioSnapshot:
    """
    Sample portfolio data for Parag Parikh Flexi Cap Fund.
    Approximate data based on publicly available factsheets.
    """
    holdings = [
        StockHolding("HDFC Bank Ltd", "INE040A01034", "Financial Services",
                     7.8, 1250000, "Large Cap", 19.5, 2.8, 16.2),
        StockHolding("ICICI Bank Ltd", "INE090A01021", "Financial Services",
                     5.2, 850000, "Large Cap", 18.2, 3.1, 17.5),
        StockHolding("Bajaj Holdings", "INE118A01012", "Financial Services",
                     4.5, 95000, "Large Cap", 15.8, 2.2, 12.1),
        StockHolding("Power Grid Corp", "INE752E01010", "Power",
                     4.1, 310000, "Large Cap", 14.2, 2.5, 18.5),
        StockHolding("ITC Ltd", "INE154A01025", "Consumer Goods",
                     3.9, 580000, "Large Cap", 27.5, 7.8, 28.5),
        StockHolding("Coal India Ltd", "INE522F01014", "Metals & Mining",
                     3.7, 295000, "Large Cap", 8.5, 3.2, 42.0),
        StockHolding("HCL Technologies", "INE860A01027", "Information Technology",
                     3.5, 420000, "Large Cap", 25.8, 6.5, 24.2),
        StockHolding("Infosys Ltd", "INE009A01021", "Information Technology",
                     3.2, 680000, "Large Cap", 28.2, 8.1, 31.5),
        StockHolding("Maruti Suzuki", "INE585B01010", "Automobile",
                     3.0, 380000, "Large Cap", 32.5, 5.8, 15.8),
        StockHolding("Mahindra & Mahindra", "INE101A01026", "Automobile",
                     2.8, 340000, "Large Cap", 28.8, 4.2, 14.5),
        StockHolding("Persistent Systems", "INE262H01013", "Information Technology",
                     2.5, 52000, "Mid Cap", 62.5, 14.2, 22.8),
        StockHolding("Zydus Lifesciences", "INE010B01027", "Healthcare",
                     2.3, 68000, "Mid Cap", 35.2, 5.5, 18.2),
        StockHolding("Multi Commodity Exch", "INE745G01035", "Financial Services",
                     2.1, 18500, "Mid Cap", 42.5, 11.2, 25.5),
        StockHolding("Balkrishna Industries", "INE787D01026", "Automobile",
                     2.0, 42000, "Mid Cap", 30.8, 5.2, 16.8),
        StockHolding("Motilal Oswal Fin", "INE338I01027", "Financial Services",
                     1.9, 38000, "Mid Cap", 22.5, 4.8, 20.2),
        StockHolding("Cyient Ltd", "INE136B01020", "Information Technology",
                     1.7, 15000, "Small Cap", 22.8, 3.5, 15.8),
        StockHolding("ICICI Lombard", "INE765G01017", "Financial Services",
                     1.6, 85000, "Large Cap", 38.5, 7.2, 18.5),
        StockHolding("SBI Cards", "INE018E01016", "Financial Services",
                     1.5, 72000, "Large Cap", 45.2, 8.5, 19.2),
        StockHolding("RHI Magnesita India", "INE743L01026", "Construction",
                     1.4, 6500, "Small Cap", 25.5, 3.8, 14.5),
        StockHolding("Atul Ltd", "INE100A01010", "Chemicals",
                     1.3, 18500, "Small Cap", 48.2, 5.2, 11.5),
        StockHolding("Alphabet Inc (Google)", None, "Information Technology",
                     5.5, None, "Large Cap", 25.8, 6.2, 28.5),
        StockHolding("Amazon.com Inc", None, "Consumer Goods",
                     3.8, None, "Large Cap", 58.2, 8.5, 15.2),
        StockHolding("Microsoft Corp", None, "Information Technology",
                     3.2, None, "Large Cap", 35.5, 12.5, 38.2),
        StockHolding("Meta Platforms", None, "Information Technology",
                     2.1, None, "Large Cap", 24.5, 7.8, 25.8),
    ]

    return PortfolioSnapshot(
        scheme_code=122639,
        scheme_name="Parag Parikh Flexi Cap Fund - Direct Growth",
        as_of_date=dt.date(2024, 12, 31),
        equity_holdings=holdings,
        total_stocks=28,
        equity_pct=89.5,
        debt_pct=2.5,
        cash_pct=5.8,
        other_pct=2.2,
        portfolio_pe=24.8,
        portfolio_pb=4.5,
        portfolio_roe_pct=18.5,
        portfolio_dividend_yield_pct=1.2,
        aum_cr=72500,
        turnover_ratio_pct=22.0,
        expense_ratio_direct_pct=0.63,
        expense_ratio_regular_pct=1.33,
    )


def get_sample_portfolio_axis_bluechip() -> PortfolioSnapshot:
    """Sample portfolio for Axis Bluechip for overlap comparison."""
    holdings = [
        StockHolding("HDFC Bank Ltd", "INE040A01034", "Financial Services",
                     9.5, 1250000, "Large Cap", 19.5, 2.8, 16.2),
        StockHolding("ICICI Bank Ltd", "INE090A01021", "Financial Services",
                     7.2, 850000, "Large Cap", 18.2, 3.1, 17.5),
        StockHolding("Infosys Ltd", "INE009A01021", "Information Technology",
                     6.8, 680000, "Large Cap", 28.2, 8.1, 31.5),
        StockHolding("TCS Ltd", "INE467B01029", "Information Technology",
                     5.5, 1450000, "Large Cap", 30.5, 12.8, 45.2),
        StockHolding("Reliance Industries", "INE002A01018", "Oil & Gas",
                     5.2, 1850000, "Large Cap", 28.5, 2.8, 9.5),
        StockHolding("Bajaj Finance", "INE296A01024", "Financial Services",
                     4.8, 425000, "Large Cap", 35.2, 6.5, 22.8),
        StockHolding("Maruti Suzuki", "INE585B01010", "Automobile",
                     4.2, 380000, "Large Cap", 32.5, 5.8, 15.8),
        StockHolding("HCL Technologies", "INE860A01027", "Information Technology",
                     3.8, 420000, "Large Cap", 25.8, 6.5, 24.2),
        StockHolding("Kotak Mahindra Bank", "INE237A01028", "Financial Services",
                     3.5, 380000, "Large Cap", 22.5, 3.2, 13.5),
        StockHolding("Bharti Airtel", "INE397D01024", "Telecom",
                     3.2, 780000, "Large Cap", 75.5, 8.2, 12.5),
        StockHolding("Divi's Laboratories", "INE361B01024", "Healthcare",
                     3.0, 95000, "Large Cap", 58.2, 10.5, 18.8),
        StockHolding("Avenue Supermarts", "INE192R01011", "Consumer Goods",
                     2.8, 285000, "Large Cap", 95.2, 14.5, 15.2),
        StockHolding("Asian Paints", "INE021A01026", "Consumer Goods",
                     2.5, 265000, "Large Cap", 55.8, 15.2, 25.5),
        StockHolding("ITC Ltd", "INE154A01025", "Consumer Goods",
                     2.2, 580000, "Large Cap", 27.5, 7.8, 28.5),
        StockHolding("Titan Company", "INE280A01028", "Consumer Goods",
                     2.0, 285000, "Large Cap", 72.5, 18.5, 25.2),
    ]

    return PortfolioSnapshot(
        scheme_code=120503,
        scheme_name="Axis Bluechip Fund - Direct Growth",
        as_of_date=dt.date(2024, 12, 31),
        equity_holdings=holdings,
        total_stocks=32,
        equity_pct=96.5,
        debt_pct=0.0,
        cash_pct=3.5,
        other_pct=0.0,
        portfolio_pe=32.5,
        portfolio_pb=6.8,
        portfolio_roe_pct=22.5,
        portfolio_dividend_yield_pct=0.8,
        aum_cr=35200,
        turnover_ratio_pct=35.0,
        expense_ratio_direct_pct=0.48,
        expense_ratio_regular_pct=1.58,
    )


def get_sample_portfolio_sbi_smallcap() -> PortfolioSnapshot:
    """Sample portfolio for SBI Small Cap for overlap comparison."""
    holdings = [
        StockHolding("IIFL Finance", None, "Financial Services",
                     3.2, 18500, "Small Cap", 15.2, 2.1, 18.5),
        StockHolding("Chalet Hotels", None, "Consumer Goods",
                     2.8, 14200, "Small Cap", 52.5, 6.8, 12.5),
        StockHolding("Finolex Industries", None, "Construction",
                     2.5, 6800, "Small Cap", 18.5, 2.2, 15.8),
        StockHolding("IIFL Securities", None, "Financial Services",
                     2.3, 4500, "Small Cap", 12.5, 2.8, 22.5),
        StockHolding("Blue Star Ltd", None, "Consumer Goods",
                     2.2, 32000, "Mid Cap", 65.2, 12.5, 18.2),
        StockHolding("Ratnamani Metals", None, "Metals & Mining",
                     2.1, 12500, "Small Cap", 32.5, 5.5, 18.5),
        StockHolding("Kalpataru Projects", None, "Construction",
                     2.0, 15800, "Small Cap", 22.5, 3.2, 14.5),
        StockHolding("Persistent Systems", "INE262H01013", "Information Technology",
                     1.9, 52000, "Mid Cap", 62.5, 14.2, 22.8),
        StockHolding("Elgi Equipments", None, "Construction",
                     1.8, 14500, "Small Cap", 48.5, 8.5, 18.2),
        StockHolding("Carborundum Universal", None, "Construction",
                     1.7, 18200, "Small Cap", 38.5, 5.8, 15.5),
    ]

    return PortfolioSnapshot(
        scheme_code=125497,
        scheme_name="SBI Small Cap Fund - Direct Growth",
        as_of_date=dt.date(2024, 12, 31),
        equity_holdings=holdings,
        total_stocks=62,
        equity_pct=92.5,
        debt_pct=0.0,
        cash_pct=7.5,
        other_pct=0.0,
        portfolio_pe=28.5,
        portfolio_pb=4.2,
        portfolio_roe_pct=16.8,
        portfolio_dividend_yield_pct=0.6,
        aum_cr=28500,
        turnover_ratio_pct=18.0,
        expense_ratio_direct_pct=0.62,
        expense_ratio_regular_pct=1.72,
    )