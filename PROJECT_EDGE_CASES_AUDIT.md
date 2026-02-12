# Project Edge Cases and Known Error Audit

This document summarizes edge cases and known failure modes discovered by a quick end-to-end scan and smoke execution.

## Commands run

- `python -m compileall -q .`
- `python demo_final.py`
- Synthetic smoke test script covering:
  - `generate_trailing_report`
  - `generate_rolling_report`
  - `generate_consistency_report`
  - `generate_sip_report`
  - `generate_risk_adjusted_report`

## Edge cases / known errors

1. **Hard dependency on external API for the demo path**
   - `demo_final.py` fails immediately if MFAPI is unreachable and exits the process.
   - In restricted/proxied environments, this is a common runtime failure mode.

2. **Benchmark mapping is equity-centric; non-equity categories may silently lose benchmark comparison**
   - Benchmark defaults are mapped only for equity-like category fragments.
   - For unmatched categories, benchmark code resolves to `None`; many comparison metrics become unavailable.

3. **Pipeline intentionally suppresses analysis exceptions, which can hide root causes**
   - Multiple calls use `_safe_run(...)->None` and swallow exceptions.
   - This keeps pipeline execution alive but can produce partially-populated reports with little diagnostic context.

4. **`compare_funds` assumes category from the first successful fund entry**
   - Ranking table category is taken from the first fund entry.
   - Mixed-category lists can be mislabeled or compared under an inappropriate category header.

5. **Rolling returns require enough history and fail fast when history is short**
   - With only ~6 months of synthetic data, `generate_rolling_report` raises:
     - "No rolling windows could be computed... Minimum required: 1.0 years."

6. **Risk-adjusted report has strict minimum-month requirement and may reject borderline datasets**
   - With ~6 calendar months of synthetic daily data, `generate_risk_adjusted_report` raised:
     - "Need at least 6 months of data. Found: 5 months."
   - This is likely due to monthly resampling and partial-month coverage.

7. **Fetcher cache read/write/parsing errors are largely non-fatal and can be silent**
   - Cache read errors are swallowed and return `None`.
   - Malformed rows in API payload are skipped silently during parsing.
   - This improves robustness but makes data quality issues harder to detect.

## Suggested hardening (optional next steps)

- Add explicit warning collection into `MasterReport` whenever `_safe_run` catches an exception.
- Validate category homogeneity in `compare_funds` and reject/partition mixed-category lists.
- Add an offline fixture mode to demos/tests (avoids hard API dependency).
- Improve benchmark coverage beyond equity categories.
- Add structured logging around cache parse/read skips to improve debuggability.
