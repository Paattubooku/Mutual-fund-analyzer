"""
data/fetcher.py
───────────────
Fetches NAV data from https://api.mfapi.in with:
  • Disk caching (pickle) with configurable expiry
  • Retry with exponential back-off
  • Structured logging (not silent swallowing)
  • Offline fixture fallback when API unreachable
  • Explicit error context on all failure paths
"""

from __future__ import annotations

import os
import pickle
import time
from datetime import datetime
from typing import List, Optional, Dict

import pandas as pd
import requests

import config
from data.models import SchemeInfo, NAVData
from utils.logger import get_logger

log = get_logger(__name__)


class FetchError(Exception):
    """Raised when NAV data cannot be retrieved."""


class NAVFetcher:
    """NAV data retriever with caching and offline fallback."""

    def __init__(
        self,
        cache_dir: str = config.CACHE_DIR,
        cache_expiry_hours: float = config.CACHE_EXPIRY_HOURS,
        offline_mode: bool = config.OFFLINE_MODE,
    ):
        self.cache_dir = cache_dir
        self.cache_expiry_seconds = cache_expiry_hours * 3600
        self.offline_mode = offline_mode
        os.makedirs(self.cache_dir, exist_ok=True)

    def fetch(self, scheme_code: int, force_refresh: bool = False) -> NAVData:
        """Return NAVData for the given AMFI scheme code."""
        from data.fixtures import is_fixture_code, generate_synthetic_nav

        if is_fixture_code(scheme_code):
            log.info("Fixture code %d → generating synthetic NAV", scheme_code)
            return generate_synthetic_nav(scheme_code)

        if not force_refresh:
            cached = self._cache_get(scheme_code, stale_ok=False)
            if cached is not None:
                log.info("Cache HIT (fresh) for scheme %d", scheme_code)
                return cached

        if not self.offline_mode:
            try:
                raw = self._api_get(f"{config.API_BASE_URL}/{scheme_code}")
                nav_data = self._parse_response(raw, scheme_code)
                self._cache_set(scheme_code, nav_data)
                log.info(
                    "API fetch OK for scheme %d: %d data points, %s → %s",
                    scheme_code,
                    nav_data.total_trading_days,
                    nav_data.inception_date,
                    nav_data.latest_date,
                )
                return nav_data
            except FetchError as exc:
                log.warning("API fetch FAILED for scheme %d: %s", scheme_code, exc)
                stale = self._cache_get(scheme_code, stale_ok=True)
                if stale is not None:
                    log.warning("Falling back to STALE cache for scheme %d", scheme_code)
                    return stale

        log.warning("All sources exhausted for scheme %d — generating offline fixture", scheme_code)
        return generate_synthetic_nav(scheme_code)

    def search(self, query: str) -> List[Dict]:
        """Search AMFI scheme directory by name fragment."""
        if self.offline_mode:
            log.info("Offline mode: search skipped for '%s'", query)
            return []

        url = f"{config.API_BASE_URL}/search?q={query}"
        try:
            resp = requests.get(url, timeout=config.REQUEST_TIMEOUT)
            resp.raise_for_status()
            results = resp.json()
            return results if isinstance(results, list) else []
        except Exception as exc:
            log.warning("Search failed for '%s': %s", query, exc)
            return []

    def _api_get(self, url: str) -> dict:
        """GET with retries and back-off."""
        last_exc = None
        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                log.debug("API GET %s (attempt %d/%d)", url, attempt, config.MAX_RETRIES)
                resp = requests.get(url, timeout=config.REQUEST_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") == "SUCCESS":
                    return data
                raise FetchError(f"API returned non-SUCCESS status: {data.get('status')}")
            except requests.ConnectionError as exc:
                last_exc = exc
                log.warning("Connection error (attempt %d): %s", attempt, exc)
            except requests.Timeout as exc:
                last_exc = exc
                log.warning("Timeout (attempt %d): %s", attempt, exc)
            except requests.HTTPError as exc:
                last_exc = exc
                log.warning("HTTP error (attempt %d): %s", attempt, exc)
            except FetchError:
                raise
            except Exception as exc:
                last_exc = exc
                log.warning("Unexpected error (attempt %d): %s", attempt, exc)

            if attempt < config.MAX_RETRIES:
                wait = config.RETRY_BACKOFF * attempt
                log.debug("Waiting %.1fs before retry", wait)
                time.sleep(wait)

        raise FetchError(f"Failed after {config.MAX_RETRIES} attempts. Last error: {last_exc}")

    @staticmethod
    def _parse_response(raw: dict, scheme_code: int) -> NAVData:
        """Convert raw JSON to NAVData with a clean pd.Series."""
        meta = raw.get("meta", {})
        scheme_info = SchemeInfo(
            scheme_code=int(meta.get("scheme_code", scheme_code)),
            scheme_name=meta.get("scheme_name", "Unknown"),
            fund_house=meta.get("fund_house", "Unknown"),
            scheme_type=meta.get("scheme_type", ""),
            scheme_category=meta.get("scheme_category", ""),
        )

        records = raw.get("data", [])
        if not records:
            raise FetchError(f"No NAV data returned for scheme {scheme_code}")

        dates, navs, skipped = [], [], 0
        for rec in records:
            try:
                d = datetime.strptime(rec["date"], "%d-%m-%Y")
                n = float(rec["nav"])
                if n <= 0:
                    skipped += 1
                    continue
                dates.append(d)
                navs.append(n)
            except (ValueError, KeyError, TypeError):
                skipped += 1
                continue

        if skipped > 0:
            log.info("Scheme %d: skipped %d malformed/invalid records during parsing", scheme_code, skipped)

        if not dates:
            raise FetchError(f"All records unparseable for scheme {scheme_code}")

        series = pd.Series(data=navs, index=pd.DatetimeIndex(dates), name="nav", dtype=float)
        series = series.sort_index()
        series = series[~series.index.duplicated(keep="last")]

        return NAVData(scheme_info=scheme_info, nav_series=series)

    def _cache_path(self, scheme_code: int) -> str:
        return os.path.join(self.cache_dir, f"nav_{scheme_code}.pkl")

    def _cache_get(self, scheme_code: int, stale_ok: bool = False) -> Optional[NAVData]:
        """Read from disk cache."""
        path = self._cache_path(scheme_code)
        if not os.path.exists(path):
            return None

        age = time.time() - os.path.getmtime(path)
        if not stale_ok and age > self.cache_expiry_seconds:
            log.debug("Cache expired for scheme %d (age=%.0fs)", scheme_code, age)
            return None

        try:
            with open(path, "rb") as fh:
                data = pickle.load(fh)
                log.debug("Cache read OK for scheme %d (age=%.0fs)", scheme_code, age)
                return data
        except Exception as exc:
            log.warning("Cache read FAILED for scheme %d: %s (%s)", scheme_code, type(exc).__name__, exc)
            return None

    def _cache_set(self, scheme_code: int, nav_data: NAVData) -> None:
        path = self._cache_path(scheme_code)
        try:
            with open(path, "wb") as fh:
                pickle.dump(nav_data, fh, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as exc:
            log.warning("Cache write FAILED for scheme %d: %s (%s)", scheme_code, type(exc).__name__, exc)
