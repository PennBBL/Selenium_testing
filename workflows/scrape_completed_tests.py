from scraping.results_config import RESULTS_CONFIGS
import scraping.base_scraper as base_scraper


def scrape_completed_tests(ctx, completed_tests):
    """
    Scrape results for known administered tests.

    Preferred behavior:
        Open results page once and scrape all administered known tests.

    Fallback behavior:
        If base_scraper does not provide run_configured_battery_scraper(),
        use run_configured_scraper() once per test.

    CSV output:
        ctx.output_dir / config.csv_file
    """
    records_to_scrape = []
    scrape_results = []

    for record in completed_tests:
        test_name = record["test_name"]
        status = record.get("status", "UNKNOWN")
        should_scrape = record.get("scrape", True)
        skipped = record.get("skipped", False)

        if skipped or not should_scrape:
            ctx.logger.info(
                f"Skipping scrape for {test_name}: "
                f"skipped={skipped}, scrape={should_scrape}"
            )
            scrape_results.append({
                "test_name": test_name,
                "status": status,
                "scrape_status": "SKIPPED",
                "reason": "Test was skipped with Ctrl+. or marked non-scrapable.",
            })
            continue

        if test_name not in RESULTS_CONFIGS:
            ctx.logger.warning(
                f"No scraper config found for known administered test {test_name}. "
                "Skipping scrape instead of crashing."
            )
            scrape_results.append({
                "test_name": test_name,
                "status": status,
                "scrape_status": "SKIPPED",
                "reason": f"No RESULTS_CONFIGS entry for {test_name}",
            })
            continue

        records_to_scrape.append(record)

    if not records_to_scrape:
        ctx.logger.info("No administered known tests to scrape.")
        return scrape_results

    browser = getattr(ctx, "browser", "chrome")
    headless = getattr(ctx, "headless", False)
    strategy = getattr(ctx, "strategy", "battery")
    output_dir = getattr(ctx, "output_dir", None)

    battery_scraper = getattr(base_scraper, "run_configured_battery_scraper", None)

    if callable(battery_scraper):
        ctx.logger.info(
            f"Scraping {len(records_to_scrape)} administered tests from one results session."
        )

        configs = {
            record["test_name"]: RESULTS_CONFIGS[record["test_name"]]
            for record in records_to_scrape
        }

        try:
            result = battery_scraper(
                subid=ctx.subid,
                strategy=strategy,
                test_results=records_to_scrape,
                configs=configs,
                browser=browser,
                headless=headless,
                output_dir=output_dir,
            )

            if isinstance(result, list):
                scrape_results.extend(result)
            else:
                scrape_results.append({
                    "test_name": "battery",
                    "status": "UNKNOWN",
                    "scrape_status": "UNKNOWN_RESULT",
                    "result": result,
                })

        except Exception as exc:
            ctx.logger.exception(f"Battery scraping failed: {exc}")

            for record in records_to_scrape:
                scrape_results.append({
                    "test_name": record["test_name"],
                    "status": record.get("status", "UNKNOWN"),
                    "scrape_status": "FAIL",
                    "errors": [str(exc)],
                })

        return scrape_results

    ctx.logger.info(
        "Battery-level scraper not found. Falling back to one scraper run per test."
    )

    for record in records_to_scrape:
        test_name = record["test_name"]
        status = record.get("status", "UNKNOWN")
        config = RESULTS_CONFIGS[test_name]

        try:
            result = base_scraper.run_configured_scraper(
                subid=ctx.subid,
                strategy=strategy,
                test_result=record,
                config=config,
                browser=browser,
                headless=headless,
                output_dir=output_dir,
            )

            scrape_results.append({
                "test_name": test_name,
                "status": status,
                "scrape_status": "PASS" if result else "FAIL",
                "result": result,
                "csv_file": str(output_dir / config.csv_file) if output_dir else config.csv_file,
            })

        except Exception as exc:
            ctx.logger.exception(f"Scraping failed for {test_name}: {exc}")

            scrape_results.append({
                "test_name": test_name,
                "status": status,
                "scrape_status": "FAIL",
                "errors": [str(exc)],
                "csv_file": str(output_dir / config.csv_file) if output_dir else config.csv_file,
            })

    return scrape_results