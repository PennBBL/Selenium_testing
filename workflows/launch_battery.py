import time
from selenium.webdriver.common.by import By
from core.utt_form import fill_utt_form
from core import assessment_link


def _click_if_present(ctx, locator, timeout=10, label='element'):
    try:
        el = ctx.wait.clickable(locator, timeout=timeout)
        ctx.driver.execute_script('arguments[0].click();', el)
        ctx.logger.info(f'Clicked {label}')
        return True
    except Exception as exc:
        ctx.logger.info(f'{label} not clicked/not present: {exc}')
        return False


def launch_battery(ctx):
    ctx.logger.info(f'Generating assessment link for battery_code={ctx.battery_code}, subid={ctx.subid}')
    link = assessment_link.generate_link(ctx.driver, ctx.base_url, ctx.battery_code, ctx.env_code, ctx.subid)
    ctx.driver.get(link)
    ctx.logger.info('Navigated to assessment link')

    fill_utt_form(ctx)
    time.sleep(5)

    _click_if_present(ctx, (By.NAME, 'RegisterParticipant'), timeout=15, label='RegisterParticipant')
    time.sleep(5)

    _click_if_present(ctx, (By.XPATH, '//a[text()="Start"]'), timeout=10, label='Start link')
    _click_if_present(ctx, (By.CSS_SELECTOR, 'button.button-form'), timeout=10, label='battery intro continue')
    _click_if_present(ctx, (By.NAME, 'StartTest'), timeout=10, label='StartTest')
    time.sleep(2)
