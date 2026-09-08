import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from core.utt_form import fill_utt_form
from core import assessment_link


def _click_element(ctx, el, label="element"):
    ctx.driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
        el,
    )
    time.sleep(0.2)

    try:
        el.click()
    except Exception:
        ctx.driver.execute_script("arguments[0].click();", el)

    ctx.logger.info(f"Clicked {label}")


def _click_if_present(ctx, locator, timeout=10, label="element"):
    try:
        el = ctx.wait.clickable(locator, timeout=timeout)
        _click_element(ctx, el, label=label)
        return True
    except Exception as exc:
        ctx.logger.info(f"{label} not clicked/not present: {exc}")
        return False


def _wait_for_page2_visible(ctx, timeout=20):
    """
    Battery intro has:
      page_1: Continue button
      page_2: hidden section containing input[name='StartTest']
    """
    def page2_is_visible(driver):
        try:
            page2 = driver.find_element(By.ID, "page_2")
            class_name = page2.get_attribute("class") or ""
            return "hidden" not in class_name
        except Exception:
            return False

    return WebDriverWait(ctx.driver, timeout).until(page2_is_visible)


def _click_battery_intro_continue_and_start(ctx):
    """
    Robustly handles the BatteryIntroduction page.

    Firefox was getting stuck here because the StartTest input is inside
    #page_2, which starts hidden and only becomes visible after nextPage().
    """
    # If we are already past this page, do nothing.
    try:
        if ctx.driver.find_elements(By.CSS_SELECTOR, "p.test-name"):
            ctx.logger.info("Already on test landing page; skipping battery intro handler")
            return
    except Exception:
        pass

    # 1. Click intro Continue on page_1.
    continue_clicked = _click_if_present(
        ctx,
        (By.CSS_SELECTOR, "#page_1 button.button-form, button.button-form"),
        timeout=20,
        label="battery intro continue",
    )

    # 2. Wait for page_2 to become visible.
    # If Firefox did not fire the onclick cleanly, call nextPage() directly.
    if continue_clicked:
        try:
            _wait_for_page2_visible(ctx, timeout=5)
        except Exception:
            ctx.logger.info("page_2 did not become visible after click; trying nextPage() directly")
            try:
                ctx.driver.execute_script(
                    "if (typeof nextPage === 'function') { nextPage(); }"
                )
            except Exception:
                pass

    _wait_for_page2_visible(ctx, timeout=20)
    ctx.logger.info("Battery intro page_2 is visible")

    # 3. Click the real StartTest submit input.
    start_selectors = [
        "input[name='StartTest'][type='submit']",
        "input[name='StartTest']",
        "input.button-form[type='submit'][value='Start']",
        "#page_2 input[type='submit']",
    ]

    last_error = None

    for selector in start_selectors:
        try:
            start_el = WebDriverWait(ctx.driver, 10).until(
                lambda d: next(
                    (
                        el for el in d.find_elements(By.CSS_SELECTOR, selector)
                        if el.is_displayed() and el.is_enabled()
                    ),
                    None,
                )
            )

            _click_element(ctx, start_el, label=f"StartTest using {selector}")
            return

        except Exception as exc:
            last_error = exc
            ctx.logger.info(f"StartTest selector failed: {selector}: {exc}")

    # 4. Last resort: submit the form directly.
    try:
        form = ctx.driver.find_element(By.CSS_SELECTOR, "#page_2 form")
        ctx.driver.execute_script("arguments[0].submit();", form)
        ctx.logger.info("Submitted StartTest form directly")
        return
    except Exception as exc:
        last_error = exc

    raise RuntimeError(f"Could not click or submit StartTest form: {last_error}")


def launch_battery(ctx):
    ctx.logger.info(
        f"Generating assessment link for battery_code={ctx.battery_code}, "
        f"subid={ctx.subid}"
    )

    link = assessment_link.generate_link(
        ctx.driver,
        ctx.base_url,
        ctx.battery_code,
        ctx.env_code,
        ctx.subid,
    )

    ctx.driver.get(link)
    ctx.logger.info("Navigated to assessment link")

    fill_utt_form(ctx)
    time.sleep(5)

    # Some flows need this, some do not. Keep optional.
    _click_if_present(
        ctx,
        (By.NAME, "RegisterParticipant"),
        timeout=15,
        label="RegisterParticipant",
    )

    time.sleep(5)

    # Start page after registration.
    _click_if_present(
        ctx,
        (By.XPATH, '//a[normalize-space()="Start"]'),
        timeout=15,
        label="Start link",
    )

    # Battery intro page.
    _click_battery_intro_continue_and_start(ctx)

    time.sleep(2)