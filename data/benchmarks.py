"""
data/benchmarks.py
──────────────────
Maps SEBI mutual-fund categories to benchmark index-fund
scheme codes (Direct-Growth plans used as proxy).

We use *index funds* rather than raw index values because:
  1.  They come from the same MFAPI data source.
  2.  They reflect real investable returns (incl. tracking error).
  3.  They make comparison fair (both are NAV-based).

Users may override any mapping by passing their own benchmark
scheme code to the analysis functions.
"""

from __future__ import annotations
from typing import Optional

# ─────────────────────────────────────────────────────
# CATEGORY → BENCHMARK SCHEME CODE
# ─────────────────────────────────────────────────────
# Scheme codes sourced from https://api.mfapi.in
# All are Direct-Growth plans of major index funds.
#
# NOTE:  Some index funds launched recently and may not
#        have 10-year history.  The analysis engine
#        gracefully handles shorter benchmark histories.
# ─────────────────────────────────────────────────────

_BENCHMARK_MAP: dict[str, int] = {
    # ── Equity ──
    "large cap":              120716,   # UTI Nifty 50 Index Fund - Direct
    "large & mid cap":        120716,   # Nifty 50 proxy (no perfect match)
    "flexi cap":              120716,   # Nifty 50 (broad market proxy)
    "multi cap":              120716,   # Nifty 50
    "mid cap":                120720,   # UTI Nifty Next 50 Index Fund - Direct
    "small cap":              120720,   # Nifty Next 50 proxy
    "elss":                   120716,   # Nifty 50
    "value":                  120716,   # Nifty 50
    "focused":                120716,   # Nifty 50
    "contra":                 120716,   # Nifty 50
    "dividend yield":         120716,   # Nifty 50
    "sectoral/thematic":      120716,   # Nifty 50 (generic fallback)
}


def get_benchmark_code(category: str) -> Optional[int]:
    """
    Return the default benchmark scheme code for a category.

    Parameters
    ----------
    category : str
        The scheme_category string from SchemeInfo
        (e.g. "Equity Scheme - Flexi Cap Fund").

    Returns
    -------
    int or None
        Scheme code of the benchmark index fund, or None
        if no mapping is found.
    """
    cat_lower = category.lower()
    for key, code in _BENCHMARK_MAP.items():
        if key in cat_lower:
            return code
    return None


def register_benchmark(category_fragment: str, scheme_code: int) -> None:
    """
    Let users add or override benchmark mappings at runtime.

    >>> register_benchmark("small cap", 145123)
    """
    _BENCHMARK_MAP[category_fragment.lower()] = scheme_code