import math
import random
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tests_catalog.common import TestRunResult
from core.continue_utils import click_continue, click_continue_until

VARIABLE_TIMING = True
TIMING_MEAN_MS = 400
TIMING_SIGMA = 0.4
OVERSHOOT_MIN = 1
OVERSHOOT_MAX = 3
RANDOM_SEED = 42

practice_trials = [
    {'trial': 'P1', 'minClicks': 6, 'bestDirection': '+1'},
    {'trial': 'P2', 'minClicks': 7, 'bestDirection': '-1'},
    {'trial': 'P3', 'minClicks': 5, 'bestDirection': '+1'},
]
real_trials = [
    {'trial': 1, 'minClicks': 8, 'bestDirection': '-1'}, {'trial': 2, 'minClicks': 9, 'bestDirection': '+1'},
    {'trial': 3, 'minClicks': 8, 'bestDirection': '+1'}, {'trial': 4, 'minClicks': 7, 'bestDirection': '-1'},
    {'trial': 5, 'minClicks': 12, 'bestDirection': '-1'}, {'trial': 6, 'minClicks': 10, 'bestDirection': '+1'},
    {'trial': 7, 'minClicks': 8, 'bestDirection': '+1'}, {'trial': 8, 'minClicks': 7, 'bestDirection': '-1'},
    {'trial': 9, 'minClicks': 9, 'bestDirection': '+1'}, {'trial': 10, 'minClicks': 11, 'bestDirection': '-1'},
    {'trial': 11, 'minClicks': 13, 'bestDirection': '-1'}, {'trial': 12, 'minClicks': 10, 'bestDirection': '+1'},
    {'trial': 13, 'minClicks': 9, 'bestDirection': '+1'}, {'trial': 14, 'minClicks': 8, 'bestDirection': '-1'},
    {'trial': 15, 'minClicks': 8, 'bestDirection': '+1'}, {'trial': 16, 'minClicks': 10, 'bestDirection': '+1'},
    {'trial': 17, 'minClicks': 7, 'bestDirection': '-1'}, {'trial': 18, 'minClicks': 9, 'bestDirection': '+1'},
    {'trial': 19, 'minClicks': 10, 'bestDirection': '+1'}, {'trial': 20, 'minClicks': 8, 'bestDirection': '+1'},
    {'trial': 21, 'minClicks': 7, 'bestDirection': '-1'}, {'trial': 22, 'minClicks': 13, 'bestDirection': '-1'},
    {'trial': 23, 'minClicks': 11, 'bestDirection': '-1'}, {'trial': 24, 'minClicks': 12, 'bestDirection': '-1'},
]


def inter_click_delay():
    if VARIABLE_TIMING:
        mean_s = TIMING_MEAN_MS / 1000.0
        mu = math.log(mean_s) - 0.5 * TIMING_SIGMA ** 2
        return max(0.1, min(2.0, random.lognormvariate(mu, TIMING_SIGMA)))
    return 0.3


def resolve_trial_clicks(trial_data, strategy, trial_index):
    direction = trial_data['bestDirection']
    n_clicks = trial_data['minClicks']
    correct_sel = "button[value='1']" if direction == '+1' else "button[value='-1']"
    correct_label = 'right' if direction == '+1' else 'left'
    wrong_sel = "button[value='-1']" if direction == '+1' else "button[value='1']"
    wrong_label = 'left' if direction == '+1' else 'right'
    if strategy == 'all_correct' or isinstance(trial_data['trial'], str):
        return [(correct_sel, correct_label)] * n_clicks, True
    if strategy == 'all_incorrect':
        return [(wrong_sel, wrong_label)] * n_clicks, False
    if strategy == 'split_12':
        return ([(correct_sel, correct_label)] * n_clicks, True) if trial_index <= 12 else ([(wrong_sel, wrong_label)] * n_clicks, False)
    if strategy == 'random_50_overshoot':
        is_correct = random.random() < 0.5
        if is_correct:
            extra = random.randint(OVERSHOOT_MIN, OVERSHOOT_MAX)
            return [(correct_sel, correct_label)] * (n_clicks + extra) + [(wrong_sel, wrong_label)] * extra, True
        return [(wrong_sel, wrong_label)] * n_clicks, False
    return [(correct_sel, correct_label)] * n_clicks, True


class VSPLOTPlugin:
    exact_code = 'zn_CN-vsplot24-2.10-ff'

    def _click_continue(self, ctx, label):
        click_continue(ctx, label=f'VSPLOT {label}', timeout=30, delay=2)

    def _practice_ready(self, ctx):
        return (
            bool(ctx.driver.find_elements(By.CSS_SELECTOR, "button[value='1']"))
            and bool(ctx.driver.find_elements(By.CSS_SELECTOR, "button[value='-1']"))
            and bool(ctx.driver.find_elements(By.CSS_SELECTOR, "button[value='FINISHED']"))
        )

    def _run_trial(self, ctx, trial_data, strategy, trial_index):
        clicks, is_correct = resolve_trial_clicks(trial_data, strategy, trial_index)
        ctx.logger.info(f"VSPLOT trial {trial_data['trial']} correct={is_correct} clicks={len(clicks)}")
        for selector, label in clicks:
            btn = WebDriverWait(ctx.driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
            btn.click()
            time.sleep(inter_click_delay())
        finish_btn = WebDriverWait(ctx.driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[value='FINISHED']")))
        finish_btn.click()
        time.sleep(1)

    def run(self, ctx, strategy='all_correct'):
        random.seed(RANDOM_SEED)
        errors = []
        try:
            # The runner has already clicked the exact-code landing-page Continue.
            # Instruction page counts vary by version/language, so click until the
            # first practice trial controls appear, with a conservative cap.
            click_continue_until(
                ctx,
                stop_condition=lambda: self._practice_ready(ctx),
                max_clicks=7,
                label='VSPLOT instruction',
                delay=2,
                timeout=30,
            )
            for idx, trial in enumerate(practice_trials, start=1):
                self._run_trial(ctx, trial, 'all_correct', idx)
            for i in range(2):
                self._click_continue(ctx, f'post-practice {i + 1}/2')
            for idx, trial in enumerate(real_trials, start=1):
                self._run_trial(ctx, trial, strategy, idx)
            return TestRunResult(status='PASS', errors=[])
        except Exception as exc:
            errors.append(str(exc))
            ctx.artifacts.capture_failure(ctx.driver, 'vsplot_failure', {'errors': errors})
            return TestRunResult(status='FAIL', errors=errors)
