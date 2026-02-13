"""
config.py
─────────
Central configuration for the Mutual Fund Analyzer.
All tuneable constants live here — nothing is hard-coded
inside business-logic modules.
"""

import os
from dateutil.relativedelta import relativedelta

# ──────────────────────────────────────────────
# API
# ──────────────────────────────────────────────
API_BASE_URL = "https://api.mfapi.in/mf"
REQUEST_TIMEOUT = 30          # seconds
MAX_RETRIES = 3
RETRY_BACKOFF = 2             # seconds between retries

# ──────────────────────────────────────────────
# CACHE
# ──────────────────────────────────────────────
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".mf_cache")
CACHE_EXPIRY_HOURS = 12       # re-fetch after this many hours

# ──────────────────────────────────────────────
# RISK-FREE RATE
# ──────────────────────────────────────────────
RISK_FREE_RATE = 0.07         # 7 % — approx 91-day T-Bill yield (India 2024)

# ──────────────────────────────────────────────
# TRAILING RETURN PERIODS
# ──────────────────────────────────────────────
# Each entry: (display_label, relativedelta offset, is_annualized)
#   • offset = None  → "Since Inception"
#   • is_annualized  → True if CAGR should be the primary metric
#                      False for sub-1-year where absolute return is primary

TRAILING_PERIODS = [
    ("1 Month",          relativedelta(months=1),   False),
    ("3 Months",         relativedelta(months=3),   False),
    ("6 Months",         relativedelta(months=6),   False),
    ("1 Year",           relativedelta(years=1),    True),
    ("3 Years",          relativedelta(years=3),    True),
    ("5 Years",          relativedelta(years=5),    True),
    ("7 Years",          relativedelta(years=7),    True),
    ("10 Years",         relativedelta(years=10),   True),
    ("Since Inception",  None,                      True),
]

# ──────────────────────────────────────────────
# NAV DATE LOOKUP
# ──────────────────────────────────────────────
MAX_NAV_LOOKBACK_DAYS = 10    # search window for nearest trading day
# ──────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────
import logging

LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"

# ──────────────────────────────────────────────
# OFFLINE / FIXTURE MODE
# ──────────────────────────────────────────────
OFFLINE_MODE = False               # set True to skip all API calls
FIXTURE_HISTORY_YEARS = 5          # years of synthetic data to generate
FIXTURE_BASE_NAV = 100.0
FIXTURE_ANNUAL_DRIFT = 0.12        # 12% annual drift for synthetic NAV
FIXTURE_ANNUAL_VOL = 0.18          # 18% annualised volatility

# ──────────────────────────────────────────────
# ANALYSIS MINIMUMS
# ──────────────────────────────────────────────
MIN_MONTHS_VOLATILITY = 6
MIN_MONTHS_BETA = 12
MIN_MONTHS_CONSISTENCY = 12
MIN_SIP_INSTALLMENTS = 3
MIN_ROLLING_OBSERVATIONS = 3
