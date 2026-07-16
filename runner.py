import json
import time
from datetime import datetime
from pathlib import Path

from core.driver_factory import build_chrome_driver
from core.logging_setup import setup_logging
from core.waits import Waits
from core.artifacts import Artifacts
from core.session_context import SessionContext
from core.subid_registry import SubidRegistry
from workflows.launch_battery import launch_battery
from workflows.run_battery import run_battery
from workflows.scrape_completed_tests import scrape_completed_tests


def prompt_required(label: str) -> str:
    while True:
        value = input(label).strip()
        if value:
            return value
        print('This value is required.')


def main():
    print('=' * 70)
    print('PENN CNB BATTERY RUNNER')
    print('Chrome only, visible mode, default/correct strategies')
    print('=' * 70)

    subid = prompt_required('Enter Subject ID / subid: ')
    battery_code = prompt_required('Enter Battery Code: ')

    run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = Path('output') / f'{run_id}_{subid}'
    logger = setup_logging(output_dir)

    driver = build_chrome_driver()
    wait = Waits(driver)
    artifacts = Artifacts(output_dir)
    registry = SubidRegistry(output_dir / 'battery_state.json')
    registry.register_battery(subid, battery_code)

    ctx = SessionContext(
        driver=driver,
        wait=wait,
        logger=logger,
        artifacts=artifacts,
        subid=subid,
        battery_code=battery_code,
        output_dir=output_dir,
    )
    ctx.registry = registry

    completed_tests = []
    try:
        launch_battery(ctx)
        completed_tests = run_battery(ctx)
        (output_dir / 'completed_tests.json').write_text(
            json.dumps(completed_tests, indent=2), encoding='utf-8'
        )
        logger.info('Battery completed. Waiting 5 seconds before closing test browser...')
        time.sleep(5)
    except Exception as exc:
        logger.exception(f'Battery failed: {exc}')
        artifacts.capture_failure(driver, 'battery_runner_failure', {'error': str(exc)})
        raise
    finally:
        try:
            driver.quit()
            logger.info('Test browser closed.')
        except Exception:
            pass

    logger.info('Starting scraping for completed tests...')
    scrape_results = scrape_completed_tests(ctx, completed_tests)
    (output_dir / 'scrape_results.json').write_text(
        json.dumps(scrape_results, indent=2), encoding='utf-8'
    )
    logger.info(f'Scrape results: {scrape_results}')
    logger.info('All done.')


if __name__ == '__main__':
    main()
