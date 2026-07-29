# Selenium Battery Framework - First Pass

This is a first-pass integration scaffold for a 3-test battery:

- ER40: `k-er40-d-4.60-ff`
- CPW: `k-cpw-3.01-ff`
- VSPLOT: `zn_CN-vsplot24-2.10-ff`

It is designed for:

- Chrome only
- visible browser mode
- prompted battery code
- order-independent dispatch from `p.test-name`
- default/correct strategies
- 5-second wait before closing the test browser after battery completion
- shared configurable scraper

## Important setup step

Replace `core/assessment_link.py` with your existing `core/assessment_link.py` implementation. The included file is a placeholder because the original function was imported by your existing scripts but not uploaded here.

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

## Expected first adjustments

The framework assumes the runner clicks the exact-code landing page before calling each plugin. If one plugin starts one page too early/late, adjust the number of continue clicks inside that plugin.

The most likely first adjustment is in `tests_catalog/vsplot_plugin.py`:

```python
for i in range(3):
    self._click_continue(ctx, f'instruction {i + 1}/3')
```

Your standalone VSPLOT clicked 4 instruction continues. This framework clicks the landing page first, so the plugin currently clicks 3.
