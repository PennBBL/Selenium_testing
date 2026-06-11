# Selenium Battery Framework - First Pass

## Initial setup

Clone repository.

### Setup virtual environment
% python3 -m venv .venv

% source .venv/bin/activate

### Install requirements:
pip install -r requirements.txt

# Auth
Contains the login function.

# Add account info
In the cnb_selenium_testing folder create a .env file with the following content:
 - adminid=your_cnb_admin_id
 - pwd=your_cnb_password


It is designed for:

- Chrome only
- visible browser mode
- prompted battery code
- order-independent dispatch from `p.test-name`
- default/correct strategies
- 5-second wait before closing the test browser after battery completion
- shared configurable scraper

## Important setup step


You also need your existing `auth/login.py` module available for scraping, because the scraper imports:

```python
from auth.login import selenium_login
```

## Run

From inside this folder:

```bash
python runner.py
```

You will be prompted for:

```text
Subject ID / subid
Battery Code
```

## Where outputs go

```text
output/<timestamp>_<subid>/
  run_*.log
  battery_state.json
  completed_tests.json
  scrape_results.json
  screenshots/
  html/
```

CSV files are currently written in the working directory as:

- `er40_results.csv`
- `cpw_results.csv`
- `vsplot_results.csv`


