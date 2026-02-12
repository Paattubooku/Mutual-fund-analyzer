"""
data/models.py
──────────────
Immutable data-classes that flow through the entire pipeline.
Using dataclasses keeps the code type-safe, serialisable,
and easy to inspect at any breakpoint.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional, List, Dict

import pandas as pd


# ───────────────── Scheme metadata ─────────────────

@dataclass(frozen=True)
class SchemeInfo:
    """Static metadata returned by the MFAPI /mf/{code} endpoint."""
    scheme_code: int
    scheme_name: str
    fund_house: str
    scheme_type: str
    scheme_category: str


# ───────────────── NAV time-series wrapper ─────────────────

@dataclass
class NAVData:
    """
    Wraps a scheme's NAV history.

    Attributes
    ----------
    scheme_info : SchemeInfo
    nav_series  : pd.Series
        Index  = pd.DatetimeIndex (sorted ascending, tz-naive)
        Values = float NAV
    """
    scheme_info: SchemeInfo
    nav_series: pd.Series            # DatetimeIndex → float

    # ── convenience properties ──

    @property
    def inception_date(self) -> dt.date:
        return self.nav_series.index.min().date()

    @property
    def latest_date(self) -> dt.date:
        return self.nav_series.index.max().date()

    @property
    def latest_nav(self) -> float:
        return float(self.nav_series.iloc[-1])

    @property
    def first_nav(self) -> float:
        return float(self.nav_series.iloc[0])

    @property
    def total_trading_days(self) -> int:
        return len(self.nav_series)

    @property
    def history_years(self) -> float:
        days = (self.latest_date - self.inception_date).days
        return round(days / 365.25, 2)

    def __repr__(self) -> str:
        return (
            f"NAVData({self.scheme_info.scheme_name!r}, "
            f"inception={self.inception_date}, "
            f"latest={self.latest_date}, "
            f"points={self.total_trading_days})"
        )


# ───────────────── Trailing return result ─────────────────

@dataclass
class TrailingReturn:
    """Result of a single trailing-return calculation."""
    period_label: str
    start_date: dt.date
    end_date: dt.date
    start_nav: float
    end_nav: float
    absolute_return_pct: float        # (end/start − 1) × 100
    cagr_pct: Optional[float]        # annualised; None if period < 1 yr
    period_years: float               # exact fractional years
    is_annualized: bool               # whether primary metric is CAGR

    @property
    def primary_return_pct(self) -> float:
        """The headline number: CAGR if annualised, else absolute."""
        return self.cagr_pct if self.is_annualized and self.cagr_pct is not None else self.absolute_return_pct


# ───────────────── Benchmark comparison ─────────────────

@dataclass
class TrailingReturnComparison:
    """Side-by-side fund vs benchmark for one period."""
    period_label: str
    fund_return: TrailingReturn
    benchmark_return: Optional[TrailingReturn]
    excess_return_pct: Optional[float]          # fund − benchmark (primary)
    beat_benchmark: Optional[bool]


# ───────────────── Full report ─────────────────

@dataclass
class TrailingReturnReport:
    """Complete trailing-return analysis output."""
    scheme_info: SchemeInfo
    benchmark_info: Optional[SchemeInfo]
    as_of_date: dt.date
    comparisons: List[TrailingReturnComparison]
    interpretation: List[str] = field(default_factory=list)

# ─────────────────────────────────────────────────────────
# ADDITIONS FOR SECTION 1.2 — ROLLING RETURNS
# ─────────────────────────────────────────────────────────

@dataclass
class RollingReturnDistribution:
    """
    Statistical summary of a single rolling-window distribution.

    Example: 3-Year Rolling Returns computed daily across 10 years
    of history produces ~1,750 individual CAGR observations.
    This class summarises that entire distribution.
    """
    window_label: str                    # e.g. "3 Years"
    window_years: float                  # e.g. 3.0
    num_observations: int                # how many rolling windows computed
    start_coverage_date: dt.date         # earliest window start date
    end_coverage_date: dt.date           # latest window end date

    # ── Core distribution statistics ──
    mean_return_pct: float               # average of all rolling CAGRs
    median_return_pct: float             # 50th percentile
    min_return_pct: float                # worst-case rolling return
    max_return_pct: float                # best-case rolling return
    std_dev_pct: float                   # volatility of rolling returns

    # ── Percentile breakpoints ──
    percentile_10_pct: float             # 10th percentile (near-worst)
    percentile_25_pct: float             # 25th percentile (Q1)
    percentile_75_pct: float             # 75th percentile (Q3)
    percentile_90_pct: float             # 90th percentile (near-best)

    # ── Probability metrics ──
    positive_return_pct: float           # % of windows with return > 0
    above_risk_free_pct: float           # % of windows beating risk-free rate

    # ── Benchmark comparison (None if no benchmark) ──
    win_rate_vs_benchmark_pct: Optional[float] = None
    avg_excess_return_pct: Optional[float] = None
    median_excess_return_pct: Optional[float] = None

    # ── Min/Max date stamps ──
    min_return_start_date: Optional[dt.date] = None
    min_return_end_date: Optional[dt.date] = None
    max_return_start_date: Optional[dt.date] = None
    max_return_end_date: Optional[dt.date] = None


@dataclass
class RollingReturnTimeSeries:
    """
    The raw rolling return time-series data.
    Useful for plotting / further analysis downstream.
    """
    window_label: str
    window_years: float
    dates: List                          # end dates of each window
    fund_returns: List[float]            # CAGR for each window
    benchmark_returns: Optional[List[float]] = None   # benchmark CAGR per window
    excess_returns: Optional[List[float]] = None      # fund − benchmark per window


@dataclass
class RollingReturnReport:
    """Complete rolling return analysis output."""
    scheme_info: SchemeInfo
    benchmark_info: Optional[SchemeInfo]
    as_of_date: dt.date
    distributions: List[RollingReturnDistribution]
    time_series: List[RollingReturnTimeSeries]
    interpretation: List[str] = field(default_factory=list)

# ─────────────────────────────────────────────────────────
# ADDITIONS FOR SECTION 1.3 — CONSISTENCY OF OUTPERFORMANCE
# ─────────────────────────────────────────────────────────

@dataclass
class CalendarYearReturn:
    """Fund vs benchmark return for a single calendar year."""
    year: int
    fund_return_pct: float
    benchmark_return_pct: Optional[float]
    excess_return_pct: Optional[float]
    beat_benchmark: Optional[bool]


@dataclass
class CalendarYearAnalysis:
    """Complete calendar year comparison across all available years."""
    yearly_returns: List[CalendarYearReturn]
    total_years: int
    years_beat_benchmark: int
    consistency_pct: float                    # % of years beating benchmark
    consistency_grade: str                    # EXCEPTIONAL / STRONG / GOOD / etc.
    avg_annual_excess_pct: float              # mean alpha across years
    median_annual_excess_pct: float
    best_year: Optional[CalendarYearReturn]
    worst_year: Optional[CalendarYearReturn]
    best_outperformance_year: Optional[CalendarYearReturn]
    worst_underperformance_year: Optional[CalendarYearReturn]


@dataclass
class MonthlyReturnData:
    """Monthly returns for fund and benchmark aligned on common months."""
    months: List[str]                         # "2020-03", "2020-04", ...
    fund_returns_pct: List[float]
    benchmark_returns_pct: List[float]


@dataclass
class CaptureRatios:
    """Up-market and down-market capture ratio analysis."""
    # Core capture ratios
    up_capture_ratio: float                   # > 100 = captures more upside
    down_capture_ratio: float                 # < 100 = loses less in downside
    capture_ratio: float                      # up / down — higher is better

    # Supporting detail
    num_up_months: int
    num_down_months: int
    total_months: int

    # Average monthly returns in up/down markets
    avg_fund_up_month_pct: float
    avg_bench_up_month_pct: float
    avg_fund_down_month_pct: float
    avg_bench_down_month_pct: float

    # Batting averages (% of months beating benchmark)
    up_month_batting_avg_pct: float           # % of up months where fund > bench
    down_month_batting_avg_pct: float         # % of down months where fund > bench


@dataclass
class ConsistencyReport:
    """Complete consistency of outperformance analysis."""
    scheme_info: SchemeInfo
    benchmark_info: Optional[SchemeInfo]
    as_of_date: dt.date
    calendar_year_analysis: Optional[CalendarYearAnalysis]
    capture_ratios: Optional[CaptureRatios]
    monthly_data: Optional[MonthlyReturnData]
    interpretation: List[str] = field(default_factory=list)

# ─────────────────────────────────────────────────────────
# ADDITIONS FOR SECTION 1.4 — SIP RETURNS (XIRR-BASED)
# ─────────────────────────────────────────────────────────

@dataclass
class SIPSimulationResult:
    """Result of a single SIP simulation over a fixed window."""
    period_label: str                        # e.g. "5 Years"
    sip_start_date: dt.date
    sip_end_date: dt.date
    monthly_amount: float                    # e.g. 10000.0
    num_installments: int
    total_invested: float                    # monthly × installments
    final_value: float                       # portfolio value at end
    absolute_return_pct: float               # (final/invested − 1) × 100
    xirr_pct: Optional[float]               # annualised XIRR in %
    wealth_multiple: float                   # final / invested


@dataclass
class LumpSumComparison:
    """SIP vs Lump Sum comparison for the same period."""
    period_label: str
    sip_xirr_pct: Optional[float]
    lumpsum_cagr_pct: Optional[float]
    sip_total_invested: float
    sip_final_value: float
    lumpsum_invested: float                  # same total as SIP
    lumpsum_final_value: float
    sip_advantage_pct: Optional[float]       # sip_xirr − lumpsum_cagr
    winner: str                              # "SIP" or "LUMP SUM" or "TIE"


@dataclass
class RollingSIPDistribution:
    """Distribution of SIP XIRR across all possible start dates."""
    period_label: str
    period_years: float
    num_observations: int
    mean_xirr_pct: float
    median_xirr_pct: float
    min_xirr_pct: float
    max_xirr_pct: float
    std_dev_pct: float
    percentile_10_pct: float
    percentile_25_pct: float
    percentile_75_pct: float
    percentile_90_pct: float
    positive_xirr_pct: float                 # % of windows with XIRR > 0
    above_risk_free_pct: float               # % beating risk-free rate

    # Worst/best SIP start dates
    min_xirr_start_date: Optional[dt.date] = None
    max_xirr_start_date: Optional[dt.date] = None

    # Benchmark comparison (if available)
    benchmark_mean_xirr_pct: Optional[float] = None
    win_rate_vs_benchmark_pct: Optional[float] = None


@dataclass
class SIPDateSensitivity:
    """Analyse if the day-of-month for SIP matters."""
    period_label: str
    day_results: Dict[int, float]            # day_of_month → avg XIRR %
    best_day: int
    worst_day: int
    best_day_xirr_pct: float
    worst_day_xirr_pct: float
    spread_pct: float                        # best − worst


@dataclass
class SIPReturnReport:
    """Complete SIP return analysis output."""
    scheme_info: SchemeInfo
    benchmark_info: Optional[SchemeInfo]
    as_of_date: dt.date

    # Core SIP returns for standard periods
    sip_results: List[SIPSimulationResult]

    # SIP vs Lump Sum
    lumpsum_comparisons: List[LumpSumComparison]

    # Rolling SIP distributions
    rolling_sip: List[RollingSIPDistribution]

    # Date sensitivity
    date_sensitivity: Optional[SIPDateSensitivity]

    interpretation: List[str] = field(default_factory=list)

# ─────────────────────────────────────────────────────────
# ADDITIONS FOR SECTION 2 — RISK-ADJUSTED RETURN RATIOS
# ─────────────────────────────────────────────────────────

@dataclass
class VolatilityMetrics:
    """
    Standard deviation and downside deviation metrics.
    Computed from monthly return data.
    """
    # Total volatility
    monthly_std_dev_pct: float               # σ of monthly returns
    annualised_std_dev_pct: float             # σ_monthly × √12

    # Downside volatility (only considers returns below MAR)
    monthly_downside_dev_pct: float           # downside σ of monthly returns
    annualised_downside_dev_pct: float        # downside σ × √12

    # Return stats used in calculation
    annualised_mean_return_pct: float         # mean monthly × 12
    annualised_median_return_pct: float
    num_months: int
    num_negative_months: int
    pct_negative_months: float               # % of months with return < 0
    worst_month_pct: float
    best_month_pct: float

    # MAR used for downside deviation
    mar_pct: float                           # Minimum Acceptable Return (annualised)


@dataclass
class BetaAnalysis:
    """
    Beta and related regression statistics.
    From regressing fund returns on benchmark returns.
    """
    beta: float                              # slope of regression
    alpha_monthly: float                     # intercept (monthly alpha)
    alpha_annualised_pct: float              # monthly alpha × 12
    r_squared: float                         # R² — how much benchmark explains fund
    correlation: float                       # Pearson correlation
    tracking_error_pct: float                # σ of (fund − benchmark) annualised
    num_months: int

    # Interpretation helpers
    beta_category: str                       # "Aggressive" / "Neutral" / "Defensive"


@dataclass
class RiskAdjustedRatios:
    """
    All seven risk-adjusted ratios computed together.
    """
    # Core inputs
    fund_return_pct: float                   # annualised fund return
    benchmark_return_pct: Optional[float]    # annualised benchmark return
    risk_free_rate_pct: float                # risk-free rate used
    period_years: float                      # analysis period

    # ── The Seven Ratios ──

    # 1. Jensen's Alpha
    jensens_alpha_pct: Optional[float]       # α = Rf − [Rrf + β(Rb − Rrf)]
    alpha_grade: Optional[str]               # EXCELLENT / GOOD / MARGINAL / NEGATIVE

    # 2. Sharpe Ratio
    sharpe_ratio: float                      # (Rf − Rrf) / σ
    sharpe_grade: str

    # 3. Sortino Ratio
    sortino_ratio: float                     # (Rf − Rrf) / σ_downside
    sortino_grade: str

    # 4. Treynor Ratio
    treynor_ratio: Optional[float]           # (Rf − Rrf) / β
    treynor_grade: Optional[str]

    # 5. Information Ratio
    information_ratio: Optional[float]       # (Rf − Rb) / TE
    information_grade: Optional[str]

    # 6. Beta
    beta: Optional[float]

    # 7. Standard Deviation
    std_dev_pct: float


@dataclass
class RiskAdjustedReport:
    """Complete risk-adjusted analysis output."""
    scheme_info: SchemeInfo
    benchmark_info: Optional[SchemeInfo]
    as_of_date: dt.date
    period_description: str                  # e.g. "3 Years (Jan 2022 — Jan 2025)"

    volatility: VolatilityMetrics
    beta_analysis: Optional[BetaAnalysis]
    ratios: RiskAdjustedRatios

    interpretation: List[str] = field(default_factory=list)

# ─────────────────────────────────────────────────────────
# ADDITIONS FOR SECTION 3 — PORTFOLIO-LEVEL ANALYSIS
# ─────────────────────────────────────────────────────────

@dataclass
class StockHolding:
    """A single stock holding in a fund's portfolio."""
    stock_name: str
    isin: Optional[str]
    sector: str
    weight_pct: float                        # % of portfolio
    market_cap_cr: Optional[float]           # market cap in ₹ crores
    market_cap_category: Optional[str]       # "Large Cap" / "Mid Cap" / "Small Cap"
    pe_ratio: Optional[float]
    pb_ratio: Optional[float]
    roe_pct: Optional[float]                 # Return on Equity


@dataclass
class PortfolioSnapshot:
    """
    Complete portfolio holdings snapshot at a point in time.

    Data sourced from AMFI factsheets / Value Research / Morningstar.
    The MFAPI does not provide portfolio data, so this must be
    loaded from external sources or entered manually.
    """
    scheme_code: int
    scheme_name: str
    as_of_date: dt.date                      # portfolio date (month-end)

    # Holdings
    equity_holdings: List[StockHolding]
    total_stocks: int

    # Asset allocation
    equity_pct: float                        # % in equities
    debt_pct: float                          # % in debt
    cash_pct: float                          # % in cash/equivalents
    other_pct: float                         # % in others (gold, REITs, etc.)

    # Aggregate valuation (from factsheet)
    portfolio_pe: Optional[float] = None
    portfolio_pb: Optional[float] = None
    portfolio_roe_pct: Optional[float] = None
    portfolio_dividend_yield_pct: Optional[float] = None

    # AUM
    aum_cr: Optional[float] = None           # AUM in ₹ crores

    # Turnover
    turnover_ratio_pct: Optional[float] = None

    # Expense ratio
    expense_ratio_direct_pct: Optional[float] = None
    expense_ratio_regular_pct: Optional[float] = None


@dataclass
class BenchmarkPortfolio:
    """
    Simplified benchmark portfolio for comparison.
    Contains sector weights and market cap distribution.
    """
    name: str
    sector_weights: Dict[str, float]         # sector → weight %
    large_cap_pct: float
    mid_cap_pct: float
    small_cap_pct: float
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None


@dataclass
class SectorAllocation:
    """Sector-level analysis for one sector."""
    sector: str
    fund_weight_pct: float
    benchmark_weight_pct: Optional[float]
    overweight_pct: Optional[float]          # fund − benchmark
    num_stocks: int
    top_stock: Optional[str]
    top_stock_weight_pct: Optional[float]


@dataclass
class SectorAnalysis:
    """Complete sector allocation analysis."""
    sectors: List[SectorAllocation]
    top_3_concentration_pct: float
    hhi: float                               # Herfindahl-Hirschman Index
    active_share_sector_pct: Optional[float] # sector-level active share
    num_sectors: int


@dataclass
class ConcentrationAnalysis:
    """Portfolio concentration metrics."""
    top_5_weight_pct: float
    top_10_weight_pct: float
    top_15_weight_pct: float
    top_20_weight_pct: float
    total_stocks: int
    largest_holding_name: str
    largest_holding_pct: float
    hhi_holdings: float                      # HHI on individual stock weights
    concentration_grade: str                 # "High Conviction" / "Moderate" / "Diversified"


@dataclass
class MarketCapBreakdown:
    """Market capitalization analysis."""
    large_cap_pct: float
    mid_cap_pct: float
    small_cap_pct: float
    weighted_avg_mcap_cr: Optional[float]    # weighted average market cap
    median_mcap_cr: Optional[float]

    # Benchmark comparison
    bench_large_pct: Optional[float] = None
    bench_mid_pct: Optional[float] = None
    bench_small_pct: Optional[float] = None

    # Bias detection
    bias: Optional[str] = None               # "Large Cap Tilted" / "Mid Cap Tilted" etc.


@dataclass
class StyleBoxPosition:
    """Position on the 3×3 Morningstar-style equity style box."""
    # Value axis (1=Deep Value, 2=Value, 3=Blend, 4=Growth, 5=High Growth)
    value_score: float
    value_label: str                         # "Value" / "Blend" / "Growth"

    # Size axis (1=Small, 2=Mid, 3=Large)
    size_score: float
    size_label: str                          # "Large Cap" / "Mid Cap" / "Small Cap"

    # Combined label
    style_label: str                         # e.g. "Large Cap Growth"


@dataclass
class PortfolioOverlap:
    """Overlap analysis between two funds."""
    fund_a_name: str
    fund_b_name: str
    overlap_pct: float                       # Σ min(w_A_i, w_B_i)
    common_stocks: int
    total_stocks_a: int
    total_stocks_b: int
    top_common_holdings: List[Tuple[str, float, float]]  # (stock, wt_A, wt_B)
    overlap_grade: str                       # "High" / "Moderate" / "Low"


@dataclass
class PortfolioAnalysisReport:
    """Complete portfolio-level analysis output."""
    scheme_name: str
    as_of_date: dt.date
    sector_analysis: Optional[SectorAnalysis]
    concentration: Optional[ConcentrationAnalysis]
    market_cap: Optional[MarketCapBreakdown]
    style_box: Optional[StyleBoxPosition]
    valuation_summary: Optional[Dict[str, Optional[float]]]
    overlaps: Optional[List[PortfolioOverlap]]
    interpretation: List[str] = field(default_factory=list)

# ─────────────────────────────────────────────────────────
# ADDITIONS FOR SECTION 4 — STRUCTURAL & QUALITATIVE
# ─────────────────────────────────────────────────────────

@dataclass
class ExpenseRatioAnalysis:
    """Expense ratio analysis with long-term cost impact."""
    current_direct_pct: Optional[float]
    current_regular_pct: Optional[float]
    category_avg_direct_pct: Optional[float]
    category_avg_regular_pct: Optional[float]

    # Cost vs category
    cheaper_than_category: Optional[bool]
    cost_difference_pct: Optional[float]       # fund − category avg

    # Long-term cost simulation
    cost_simulations: Dict[str, Dict]          # horizon → {invested, cost_drag, final_with, final_without}

    # Grading
    expense_grade: str                         # "EXCELLENT" / "GOOD" / "AVERAGE" / "EXPENSIVE"

    # Alpha break-even
    alpha_breakeven_pct: Optional[float]       # how much alpha needed to justify TER vs index


@dataclass
class TurnoverAnalysis:
    """Portfolio turnover analysis with hidden cost estimation."""
    turnover_ratio_pct: Optional[float]
    category_avg_turnover_pct: Optional[float]
    turnover_grade: str                        # "Buy & Hold" / "Low" / "Moderate" / "High" / "Very High"

    # Hidden cost estimation
    estimated_brokerage_drag_pct: float
    estimated_impact_cost_drag_pct: float
    estimated_stt_drag_pct: float
    total_hidden_cost_pct: float

    # Effective total cost
    effective_total_cost_pct: float             # TER + hidden turnover costs


@dataclass
class FundManagerInfo:
    """Information about a fund manager."""
    name: str
    designation: Optional[str]
    tenure_start_date: Optional[dt.date]
    tenure_years: Optional[float]
    total_experience_years: Optional[float]
    num_funds_managed: Optional[int]
    qualification: Optional[str]


@dataclass
class FundManagerAnalysis:
    """Fund manager analysis with stability assessment."""
    current_managers: List[FundManagerInfo]
    manager_history: List[Dict]                # [{name, from, to, tenure_years}]
    total_manager_changes: int
    avg_manager_tenure_years: Optional[float]
    current_tenure_years: Optional[float]
    stability_grade: str                       # "STABLE" / "MODERATE" / "UNSTABLE"
    tenure_grade: str                          # "EXCELLENT" / "GOOD" / "CONCERN" / "HIGH RISK"


@dataclass
class AUMAnalysis:
    """AUM analysis with size-strategy compatibility."""
    current_aum_cr: Optional[float]
    aum_history: List[Dict]                    # [{date, aum_cr}]
    aum_trend: str                             # "Growing" / "Stable" / "Declining" / "Spiking"
    aum_growth_1y_pct: Optional[float]

    # Size-strategy compatibility
    category: str
    ideal_aum_range_cr: Tuple[float, float]
    size_appropriate: bool
    size_grade: str                            # "OPTIMAL" / "ACCEPTABLE" / "CONCERN" / "CRITICAL"
    size_concern: Optional[str]                # specific concern message


@dataclass
class ExitLoadInfo:
    """Exit load structure."""
    load_structure: List[Dict]                 # [{period, load_pct}]
    lock_in_period_days: Optional[int]         # for ELSS
    sip_consideration: str                     # note about per-instalment clock


@dataclass
class FundHouseInfo:
    """Fund house / AMC quality assessment."""
    amc_name: str
    amc_aum_cr: Optional[float]
    amc_rank: Optional[int]
    total_schemes: Optional[int]
    years_in_operation: Optional[int]
    reputation_grade: str                      # "TOP TIER" / "ESTABLISHED" / "MID TIER" / "SMALL"


@dataclass
class StructuralReport:
    """Complete structural and qualitative analysis."""
    scheme_name: str
    scheme_category: str
    as_of_date: dt.date

    expense_analysis: Optional[ExpenseRatioAnalysis]
    turnover_analysis: Optional[TurnoverAnalysis]
    manager_analysis: Optional[FundManagerAnalysis]
    aum_analysis: Optional[AUMAnalysis]
    exit_load: Optional[ExitLoadInfo]
    fund_house: Optional[FundHouseInfo]

    # Overall structural score (0-100)
    structural_score: Optional[float]
    structural_grade: Optional[str]

    interpretation: List[str] = field(default_factory=list)

    # ─────────────────────────────────────────────────────────
# ADDITIONS FOR SECTION 7 — SCORING & RANKING
# ─────────────────────────────────────────────────────────

@dataclass
class MetricScore:
    """A single normalised metric with its raw value and score."""
    metric_name: str
    raw_value: Optional[float]
    percentile_score: float              # 0-100 within category
    weight: float                        # weight in composite
    weighted_contribution: float         # percentile × weight
    direction: str                       # "higher_better" or "lower_better"
    category_label: str                  # "Performance", "Risk-Adjusted", etc.


@dataclass
class PenaltyBonus:
    """A penalty or bonus applied to the composite score."""
    label: str
    points: float                        # negative = penalty, positive = bonus
    reason: str
    triggered: bool


@dataclass
class InvestmentProfile:
    """Investment goal profile with category weights."""
    profile_name: str                    # "Aggressive", "Growth", etc.
    performance_weight: float
    risk_adjusted_weight: float
    risk_management_weight: float
    structural_weight: float
    description: str


@dataclass
class FundScore:
    """Complete scoring output for a single fund."""
    scheme_code: int
    scheme_name: str
    scheme_category: str
    fund_age_years: float

    # Profile used
    profile: InvestmentProfile

    # Individual metric scores
    metric_scores: List[MetricScore]

    # Category sub-scores (0-100)
    performance_score: float
    risk_adjusted_score: float
    risk_management_score: float
    structural_score: float

    # Adjustments
    penalties: List[PenaltyBonus]
    bonuses: List[PenaltyBonus]
    total_penalty: float
    total_bonus: float

    # Final composite
    raw_composite: float                 # before penalties/bonuses
    final_score: float                   # after adjustments, clamped 0-100
    star_rating: int                     # 1-5 stars
    rating_label: str                    # "EXCEPTIONAL", "VERY GOOD", etc.
    recommendation: str                  # actionable recommendation

    # Hard filter results
    disqualified: bool
    disqualification_reasons: List[str]


@dataclass
class RankingTable:
    """Multi-fund ranking output."""
    profile: InvestmentProfile
    category: str
    as_of_date: dt.date
    fund_scores: List[FundScore]         # sorted by final_score descending
    top_picks: List[FundScore]           # top 3-5
    interpretation: List[str] = field(default_factory=list)


@dataclass
class MasterReport:
    """The complete master analysis report for a single fund."""
    scheme_info: SchemeInfo
    as_of_date: dt.date

    # Component reports (from previous sections)
    trailing_returns: Optional[object]
    rolling_returns: Optional[object]
    consistency: Optional[object]
    sip_returns: Optional[object]
    risk_adjusted: Optional[object]

    # Scoring
    fund_score: Optional[FundScore]

    # Diagnostics
    warnings: List["AnalysisWarning"] = field(default_factory=list)

    # Overall summary
    summary: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────
# ADDITIONS FOR STEP 9 — WARNINGS AND DIAGNOSTICS
# ─────────────────────────────────────────────────────────

@dataclass
class AnalysisWarning:
    """
    A structured warning collected during the analysis pipeline.
    Replaces silent exception swallowing with traceable diagnostics.
    """
    section: str
    severity: str
    message: str
    exception_type: Optional[str] = None
    exception_detail: Optional[str] = None
