import random
import time
from selenium.webdriver.common.by import By
from tests_catalog.common import TestRunResult
from core.continue_utils import click_continue, click_continue_until

TARGETS = {
    'NIGHT', 'TOWER', 'RING', 'FLAG', 'UMBRELLA', 'CHEESE', 'CHERRY', 'LAP', 'NURSE', 'HOBBY',
    'BRICK', 'BOX', 'STATION', 'BLOOM', 'VOLUME', 'JOKE', 'POCKET', 'FORK', 'HONEY', 'PACKAGE'
}
BUTTONS = ['DEFINITELY YES', 'PROBABLY YES', 'PROBABLY NO', 'DEFINITELY NO']


def get_response(word, strategy):
    is_target = word.strip().upper() in TARGETS
    if strategy == 'correct':
        return 'DEFINITELY YES' if is_target else 'DEFINITELY NO'
    if strategy == 'lax':
        return 'PROBABLY YES' if is_target else 'PROBABLY NO'
    if strategy == 'all_yes':
        return 'DEFINITELY YES'
    if strategy == 'all_no':
        return 'DEFINITELY NO'
    if strategy == 'random':
        return random.choice(BUTTONS)
    return 'DEFINITELY YES' if is_target else 'DEFINITELY NO'


class CPWPlugin:
    exact_code = 'k-cpw-3.01-ff'

    def _click_continue(self, ctx, label):
        click_continue(ctx, label=f'CPW {label}', timeout=30, delay=1)

    def _presentation_or_test_started(self, ctx):
        page = ctx.driver.page_source
        return (
            'Decide whether you have seen' in page
            or bool(ctx.driver.find_elements(By.CSS_SELECTOR, 'h1.stimulus--cpw'))
        )

    def _wait_for_presentation_end(self, ctx, timeout=140):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if 'Decide whether you have seen' in ctx.driver.page_source:
                return True
            time.sleep(2)
        return False

    def run(self, ctx, strategy='correct'):
        errors = []
        try:
            # The runner has already clicked the exact-code landing-page Continue.
            # Instruction counts can vary, so click continue until the timed
            # presentation/test phase starts, with a conservative cap.
            click_continue_until(
                ctx,
                stop_condition=lambda: self._presentation_or_test_started(ctx),
                max_clicks=7,
                label='CPW instruction/presentation-start',
                delay=1.5,
                timeout=30,
            )
            ctx.logger.info('CPW waiting for presentation to finish')
            if not self._wait_for_presentation_end(ctx):
                raise RuntimeError('Timed out waiting for CPW presentation end')
            self._click_continue(ctx, 'post-presentation instructions')
            time.sleep(1)
            self._click_continue(ctx, 'begin test')
            time.sleep(2)

            trial_count = 0
            max_trials = 40
            while trial_count < max_trials:
                try:
                    stimulus_el = ctx.wait.present((By.CSS_SELECTOR, 'h1.stimulus--cpw'), timeout=10)
                    word = stimulus_el.text.strip().upper()
                except Exception:
                    ctx.logger.info('CPW no stimulus found; ending loop')
                    break
                if not word:
                    continue
                trial_count += 1
                response = get_response(word, strategy)
                ctx.logger.info(f'CPW trial {trial_count:02d}: {word} -> {response}')
                buttons = ctx.driver.find_elements(By.CSS_SELECTOR, 'div.button.memory-button')
                if len(buttons) != 4:
                    errors.append(f'Trial {trial_count}: expected 4 buttons, found {len(buttons)}')
                    continue
                clicked = False
                for btn in buttons:
                    if btn.text.strip().upper() == response:
                        time.sleep(random.uniform(0.3, 1.0))
                        btn.click()
                        clicked = True
                        break
                if not clicked:
                    errors.append(f'Trial {trial_count}: could not click {response}')
            return TestRunResult(status='PASS' if not errors else 'FAIL', errors=errors)
        except Exception as exc:
            errors.append(str(exc))
            ctx.artifacts.capture_failure(ctx.driver, 'cpw_failure', {'errors': errors})
            return TestRunResult(status='FAIL', errors=errors)
