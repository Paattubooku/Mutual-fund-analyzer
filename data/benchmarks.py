"""
data/benchmarks.py
──────────────────
Maps SEBI mutual-fund categories to benchmark index-fund
scheme codes. Expanded to cover debt, hybrid, and solution-
oriented categories with explicit fallback and warnings.
"""

from __future__ import annotations

from typing import Optional

from utils.logger import get_logger

log = get_logger(__name__)


_BENCHMARK_MAP: dict[str, int] = {
    "large cap": 120716,
    "large & mid cap": 120716,
    "flexi cap": 120716,
    "multi cap": 120716,
    "mid cap": 120720,
    "small cap": 120720,
    "elss": 120716,
    "value": 120716,
    "focused": 120716,
    "contra": 120716,
    "dividend yield": 120716,
    "sectoral": 120716,
    "thematic": 120716,
    "aggressive hybrid": 120716,
    "balanced advantage": 120716,
    "conservative hybrid": 120716,
    "equity savings": 120716,
    "multi asset": 120716,
    "arbitrage": 120716,
    "liquid": 119551,
    "overnight": 119551,
    "ultra short": 119551,
    "low duration": 119551,
    "short duration": 119551,
    "medium duration": 119551,
    "medium to long": 119551,
    "long duration": 119551,
    "dynamic bond": 119551,
    "corporate bond": 119551,
    "credit risk": 119551,
    "banking and psu": 119551,
    "gilt": 119551,
    "10 year": 119551,
    "floater": 119551,
    "retirement": 120716,
    "children": 120716,
    "index": 120716,
    "fund of funds": 120716,
}


def get_benchmark_code(category: str) -> Optional[int]:
    """Return the default benchmark scheme code for a category."""
    if not category:
        log.warning("Empty category string — cannot determine benchmark")
        return None

    cat_lower = category.lower()
    for key, code in _BENCHMARK_MAP.items():
        if key in cat_lower:
            return code

    for signal in ["equity", "stock", "share", "growth", "capital"]:
        if signal in cat_lower:
            log.warning(
                "No specific benchmark for category '%s' — falling back to Nifty 50 proxy (scheme 120716)",
                category,
            )
            return 120716

    for signal in ["debt", "income", "bond", "money market", "fixed"]:
        if signal in cat_lower:
            log.warning(
                "No specific benchmark for category '%s' — falling back to Liquid fund proxy (scheme 119551)",
                category,
            )
            return 119551

    log.warning("Category '%s' has no benchmark mapping — comparison metrics unavailable", category)
    return None


def register_benchmark(category_fragment: str, scheme_code: int) -> None:
    """Let users add or override benchmark mappings at runtime."""
    _BENCHMARK_MAP[category_fragment.lower()] = scheme_code
    log.info("Registered benchmark %d for category '%s'", scheme_code, category_fragment)
