import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

CONTINUE_SELECTORS = [
    "button.continue-button",
    "button.button.continue-button",
    "button.button.continue-button.center--horizontal",
]


def find_continue(driver):
    for selector in CONTINUE_SELECTORS:
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        if elements:
            return elements[0]
    return None


def click_continue(ctx, label="continue", timeout=15, delay=1.0):
    last_error = None
    for selector in CONTINUE_SELECTORS:
        try:
            el = WebDriverWait(ctx.driver, timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            ctx.driver.execute_script("arguments[0].click();", el)
            ctx.logger.info(f"Clicked continue [{label}] using selector: {selector}")
            if delay:
                time.sleep(delay)
            return True
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Could not click continue for {label}: {last_error}")


def click_continue_until(ctx, stop_condition, max_clicks=7, label="instruction", delay=1.5, timeout=10):
    """Click continue pages until stop_condition() becomes True or max_clicks is reached.

    This is intended for tests whose instruction page count differs by version/language.
    The stop condition should detect the first real test/practice page, not rely on text.
    """
    clicks = 0
    while clicks < max_clicks:
        try:
            if stop_condition():
                ctx.logger.info(f"Stop condition reached before {label} continue {clicks + 1}")
                return clicks
        except Exception:
            pass

        if not find_continue(ctx.driver):
            ctx.logger.info(f"No continue button found after {clicks} {label} click(s)")
            return clicks

        click_continue(ctx, f"{label} {clicks + 1}/{max_clicks}", timeout=timeout, delay=delay)
        clicks += 1

        try:
            if stop_condition():
                ctx.logger.info(f"Stop condition reached after {clicks} {label} click(s)")
                return clicks
        except Exception:
            pass

    ctx.logger.info(f"Reached max {label} continues: {max_clicks}")
    return clicks
