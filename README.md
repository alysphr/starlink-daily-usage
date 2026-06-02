# Starlink Daily Usage Scraper

This project logs into the Starlink account page, extracts daily data usage from the live usage chart, and exports it to CSV. It also provides a Web UI to run the scrape and download results.

## Requirements
- Python 3.11+
- Microsoft Edge (for cookie-based login)

## Install
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install
```

## Run
```bash
python app.py
```
Then open http://127.0.0.1:5055

## Professor Quick Start
1) Install dependencies:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python -m playwright install
   ```
2) Run the app:
   ```bash
   python app.py
   ```
3) Open http://127.0.0.1:5055
4) Log in to Starlink in Edge and export cookies as JSON.
5) Paste cookies JSON + daily usage URL into Live Login and click Log In & Scrape.
6) Download the CSV.

## Live Scrape (Cookie Method)
This is the most reliable method because Starlink blocks automated logins.

1) Log in in Edge at https://starlink.com/auth/login using the provided credentials.
2) Open the daily usage page:
   https://starlink.com/account/service-line/AST-2293597-46342-54?selectedDevice=ut01000000-00000000-0060d786&page=0&limit=5
3) Export cookies as JSON using the Cookie-Editor extension.
4) Open http://127.0.0.1:5055, click Live Login.
5) Paste the daily usage URL.
6) Paste the cookies JSON into the cookies box (required if login is blocked).
7) Click Log In & Scrape.
8) Download the CSV.

## CSV Output
The CSV contains:
- day_index
- date (YYYY-MM-DD, derived from the scrape month)
- day_of_week (Monday, Tuesday, …)
- month (January, February, …)
- usage_gb
- pct_change_prev_day (% change vs. previous day; NaN for Day 1 or when previous day is 0)

## Files
- app.py: Flask app and Web UI
- scraper.py: Parsing and live fetch logic
- templates/index.html: UI template
- static/style.css: UI styles
- requirements.txt: Dependencies
