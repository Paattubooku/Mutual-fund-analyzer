"""
data/fetcher.py
───────────────
Fetches NAV data from https://api.mfapi.in and caches
results on disk so repeated runs during development
don't hammer the free API.

Public API
----------
    fetcher = NAVFetcher()
    nav_data = fetcher.fetch(scheme_code=122639)
    results  = fetcher.search("parag parikh flexi")
"""

from __future__ import annotations

import json
import os
import pickle
import time
from datetime import datetime, timedelta
from typing import List, Optional, Dict

import pandas as pd
import requests

from config import (
    API_BASE_URL,
    CACHE_DIR,
    CACHE_EXPIRY_HOURS,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    RETRY_BACKOFF,
)
from data.models import SchemeInfo, NAVData


class FetchError(Exception):
    """Raised when NAV data cannot be retrieved."""


class NAVFetcher:
    """
    Stateless (except cache dir) NAV data retriever.

    Usage
    -----
        fetcher = NAVFetcher()
        ppfas   = fetcher.fetch(122639)
        print(ppfas.nav_series.tail())
    """

    def __init__(self, cache_dir: str = CACHE_DIR,
                 cache_expiry_hours: float = CACHE_EXPIRY_HOURS):
        self.cache_dir = cache_dir
        self.cache_expiry_seconds = cache_expiry_hours * 3600
        os.makedirs(self.cache_dir, exist_ok=True)

    # ────────────────── public methods ──────────────────

    def fetch(self, scheme_code: int, force_refresh: bool = False) -> NAVData:
        """
        Return NAVData for the given AMFI scheme code.

        1. Check disk cache (pickle).
        2. If miss or stale → hit API, parse, cache, return.
        """
        if not force_refresh:
            cached = self._cache_get(scheme_code)
            if cached is not None:
                return cached

        raw = self._api_get(f"{API_BASE_URL}/{scheme_code}")
        nav_data = self._parse_response(raw, scheme_code)
        self._cache_set(scheme_code, nav_data)
        return nav_data

    def search(self, query: str) -> List[Dict]:
        """
        Search AMFI scheme directory by name fragment.
        Returns list of {scheme_code, scheme_name}.
        """
        url = f"{API_BASE_URL}/search?q={query}"
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            results = resp.json()
            if isinstance(results, list):
                return results
            return []
        except Exception as exc:
            print(f"[WARN] Search failed: {exc}")
            return []

    # ────────────────── API layer ──────────────────

    def _api_get(self, url: str) -> dict:
        """GET with retries and back-off."""
        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.get(url, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") == "SUCCESS":
                    return data
                raise FetchError(
                    f"API returned non-SUCCESS status: {data.get('status')}"
                )
            except (requests.RequestException, FetchError) as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF * attempt)
        raise FetchError(
            f"Failed after {MAX_RETRIES} attempts. Last error: {last_exc}"
        )

    # ────────────────── parsing ──────────────────

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

        # Build DataFrame → Series
        dates, navs = [], []
        for rec in records:
            try:
                d = datetime.strptime(rec["date"], "%d-%m-%Y")
                n = float(rec["nav"])
                dates.append(d)
                navs.append(n)
            except (ValueError, KeyError):
                continue                      # skip malformed rows

        if not dates:
            raise FetchError(f"All records unparseable for scheme {scheme_code}")

        series = pd.Series(data=navs, index=pd.DatetimeIndex(dates),
                           name="nav", dtype=float)
        series = series.sort_index()          # oldest → newest
        series = series[~series.index.duplicated(keep="last")]  # deduplicate

        return NAVData(scheme_info=scheme_info, nav_series=series)

    # ────────────────── disk cache ──────────────────

    def _cache_path(self, scheme_code: int) -> str:
        return os.path.join(self.cache_dir, f"nav_{scheme_code}.pkl")

    def _cache_get(self, scheme_code: int) -> Optional[NAVData]:
        path = self._cache_path(scheme_code)
        if not os.path.exists(path):
            return None
        age = time.time() - os.path.getmtime(path)
        if age > self.cache_expiry_seconds:
            return None
        try:
            with open(path, "rb") as fh:
                return pickle.load(fh)
        except Exception:
            return None

    def _cache_set(self, scheme_code: int, nav_data: NAVData) -> None:
        path = self._cache_path(scheme_code)
        try:
            with open(path, "wb") as fh:
                pickle.dump(nav_data, fh, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as exc:
            print(f"[WARN] Cache write failed: {exc}")