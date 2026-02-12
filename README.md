# Mutual Fund Analyzer

A comprehensive mutual fund analysis framework for Indian Mutual Funds.

## Features

- **Multi-Fund Analysis**: Evaluate multiple funds across different categories.
- **Scoring Engine**: Rank funds based on performance, risk-adjusted returns, risk management, and structural factors.
- **Investment Profiles**: Compare funds based on your specific profile (Aggressive, Growth, Balanced, Conservative).
- **Data Integration**: Integrated with AMFI and AdvisorKhoj for real-time data scraping.
- **Deep Metrics**: Includes trailing returns, rolling returns, consistency analysis, and risk-adjusted metrics like Sharpe and Sortino ratios.

## Structure

- `demo_final.py`: The main entry point for the system demonstration.
- `mf_scraper.py` / `new_mf_scraper.py`: Web scrapers for fund metadata.
- `pipeline/`: Master pipeline orchestration.
- `metrics/`: Core calculation engine for various financial metrics.
- `data/`: Data providers and models.
- `utils/`: Formatting and utility functions.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the demo:
   ```bash
   python demo_final.py
   ```

## Configuration

All tunable constants are in `config.py`.
