import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from tests_catalog.common import TestRunResult
from core.continue_utils import click_continue


class SPCPTNLPlugin:
    exact_code = "spcptnl-2.01-ff"

    exact_codes = {
        "spcptnl-2.01-ff",
        "zn_CN-spcptnl-2.01-ff",
        "zh_CN-spcptnl-2.01-ff",
    }

    MAIN_NUMBER_TRIALS = 5
    MAIN_LETTER_TRIALS = 5

    CONTINUE_SELECTORS = [
        "button.continue-button",
        "button.button.continue-button",
        "button.button.continue-button.center--horizontal",
    ]

    def _press_space(self, ctx, label="space"):
        ctx.logger.info(f"SPCPTNL pressing space: {label}")
        body = ctx.driver.find_element(By.TAG_NAME, "body")
        body.send_keys(Keys.SPACE)

    def _click_continue_required(self, ctx, label, timeout=20):
        click_continue(ctx, label=f"SPCPTNL {label}", timeout=timeout, delay=0.5)

    def _continue_visible(self, ctx):
        for selector in self.CONTINUE_SELECTORS:
            try:
                buttons = ctx.driver.find_elements(By.CSS_SELECTOR, selector)
            except Exception:
                continue

            for button in buttons:
                try:
                    if button.is_displayed() and button.is_enabled():
                        return True
                except Exception:
                    continue

        return False

    def _visible_image_srcs(self, ctx):
        """
        Read visible non-demo image srcs in one JS call so React image swaps do
        not cause stale element references.

        Demo images on instruction pages have class img--demo and must be
        ignored, otherwise the plugin can think practice/test has started early.
        """
        try:
            return ctx.driver.execute_script(
                """
                return Array.from(document.querySelectorAll("img"))
                    .filter(img => {
                        if (img.classList.contains("img--demo")) return false;

                        const rect = img.getBoundingClientRect();
                        const style = window.getComputedStyle(img);

                        return (
                            rect.width > 0 &&
                            rect.height > 0 &&
                            style.visibility !== "hidden" &&
                            style.display !== "none"
                        );
                    })
                    .map(img => img.currentSrc || img.src || "")
                    .filter(src => src.length > 0);
                """
            ) or []
        except Exception:
            return []

    def _visible_image_contains(self, ctx, fragment):
        if not fragment:
            return False

        fragment = fragment.lower()

        for src in self._visible_image_srcs(ctx):
            if fragment in src.lower():
                return True

        return False

    def _wait_for_image_fragment(self, ctx, fragment, timeout=30):
        fragment = fragment.lower()
        deadline = time.time() + timeout
        last_srcs = []

        while time.time() < deadline:
            srcs = self._visible_image_srcs(ctx)
            last_srcs = srcs

            for src in srcs:
                if fragment in src.lower():
                    ctx.logger.info(
                        "SPCPTNL found image fragment %r in src=%s",
                        fragment,
                        src.split("/")[-1],
                    )
                    return src

            time.sleep(0.05)

        raise RuntimeError(
            f"SPCPTNL timed out waiting for image fragment {fragment!r}; "
            f"last visible non-demo image srcs={[src.split('/')[-1] for src in last_srcs]}"
        )

    def _click_continue_until_image(self, ctx, label, image_fragment, max_clicks=4, timeout=20):
        """
        Click continue pages until the expected CPT image appears.

        This avoids assuming a fixed number of instruction pages in every
        language. After a Begin page, there is usually a 5-second countdown, so
        each click waits briefly for the expected image before trying another
        continue.
        """
        image_fragment = image_fragment.lower()

        for click_index in range(max_clicks + 1):
            if self._visible_image_contains(ctx, image_fragment):
                ctx.logger.info(
                    "SPCPTNL %s: image fragment %r already visible",
                    label,
                    image_fragment,
                )
                return

            if click_index >= max_clicks:
                break

            self._click_continue_required(
                ctx,
                f"{label} continue {click_index + 1}",
                timeout=timeout,
            )

            end = time.time() + 7
            while time.time() < end:
                if self._visible_image_contains(ctx, image_fragment):
                    ctx.logger.info(
                        "SPCPTNL %s: image fragment %r visible after click",
                        label,
                        image_fragment,
                    )
                    return
                time.sleep(0.1)

        raise RuntimeError(
            f"SPCPTNL {label}: expected image fragment {image_fragment!r} "
            f"not visible after {max_clicks} continue clicks"
        )

    def _start_number_practice(self, ctx):
        """
        Landing Continue is already clicked by run_battery.

        Observed Chinese flow:
          page 2: number instructions
          page 3: begin number practice
          then 5-second countdown
          then pracNum images
        """
        self._click_continue_required(ctx, "initial instructions", timeout=20)
        self._click_continue_required(ctx, "begin number practice", timeout=20)

        ctx.logger.info("SPCPTNL waiting for number practice image after countdown")
        self._wait_for_image_fragment(ctx, "pracNum", timeout=30)

    def _run_practice(self, ctx, practice_prefix, target_fragment, label, timeout=90):
        """
        Practice is randomized.

        Known correct response rule:
          number practice target: pracNum1
          letter practice target: pracLet1

        Non-target stimuli should receive no response.

        Practice ends when a continue button appears for the next instruction or
        begin page. Feedback/interstitial screens may require space to advance,
        so this presses space only when no practice image is visible.
        """
        ctx.logger.info(f"SPCPTNL starting {label} practice")

        deadline = time.time() + timeout
        target_currently_visible = False
        target_presses = 0
        last_feedback_space = 0

        practice_prefix = practice_prefix.lower()
        target_fragment = target_fragment.lower()

        while time.time() < deadline:
            if self._continue_visible(ctx):
                ctx.logger.info(
                    f"SPCPTNL {label} practice finished; continue button visible; "
                    f"target_presses={target_presses}"
                )
                return

            srcs_lower = [src.lower() for src in self._visible_image_srcs(ctx)]

            practice_image_visible = any(practice_prefix in src for src in srcs_lower)
            target_visible = any(target_fragment in src for src in srcs_lower)

            if target_visible and not target_currently_visible:
                time.sleep(0.05)
                self._press_space(ctx, f"{label} target {target_fragment}")
                target_presses += 1
                target_currently_visible = True

            if not target_visible:
                target_currently_visible = False

            # Feedback/interstitial screens often require spacebar.
            # Avoid doing this while non-target practice stimuli are visible.
            if not practice_image_visible and not self._continue_visible(ctx):
                now = time.time()
                if now - last_feedback_space > 0.8:
                    self._press_space(ctx, f"{label} feedback/interstitial continue")
                    last_feedback_space = now

            time.sleep(0.08)

        raise RuntimeError(
            f"SPCPTNL {label} practice did not finish within {timeout}s; "
            f"target_presses={target_presses}"
        )

    def _start_letter_practice(self, ctx):
        """
        After number practice, language/version builds may differ in whether
        there is a separate letter-instruction page and a separate begin page.

        Do not hard-code the number of continues. Click until pracLet appears.
        """
        self._click_continue_until_image(
            ctx,
            label="letter practice",
            image_fragment="pracLet",
            max_clicks=3,
            timeout=20,
        )

    def _start_main_test(self, ctx):
        """
        After letter practice, language/version builds may differ in number of
        instruction/begin pages. Click until the first real number test image
        appears.
        """
        self._click_continue_until_image(
            ctx,
            label="main number block",
            image_fragment="num",
            max_clicks=4,
            timeout=20,
        )

    def _wait_for_main_trial_image(self, ctx, prefix, seen_srcs, timeout=20):
        prefix = prefix.lower()
        deadline = time.time() + timeout
        last_srcs = []

        while time.time() < deadline:
            srcs = self._visible_image_srcs(ctx)
            last_srcs = srcs

            for src in srcs:
                src_lower = src.lower()

                # Avoid matching practice assets such as pracNum/pracLet.
                if "prac" in src_lower:
                    continue

                if prefix in src_lower and src not in seen_srcs:
                    return src

            time.sleep(0.05)

        raise RuntimeError(
            f"SPCPTNL timed out waiting for new {prefix} trial image; "
            f"last visible non-demo image srcs={[src.split('/')[-1] for src in last_srcs]}"
        )

    def _run_main_cpt_block(self, ctx, prefix, expected_trials, label):
        """
        Main test blocks contain only target category stimuli:
          number block: num*
          letter block: let*

        So press space once for each new visible stimulus.
        """
        ctx.logger.info(f"SPCPTNL starting main {label} block")

        seen_srcs = set()

        for trial_index in range(1, expected_trials + 1):
            src = self._wait_for_main_trial_image(
                ctx,
                prefix=prefix,
                seen_srcs=seen_srcs,
                timeout=20,
            )

            seen_srcs.add(src)

            ctx.logger.info(
                f"SPCPTNL {label} trial {trial_index}/{expected_trials}: "
                f"src={src.split('/')[-1]}"
            )

            time.sleep(0.05)
            self._press_space(ctx, f"{label} trial {trial_index}")

            # Stimulus duration is about 1000 ms, blank about 700 ms.
            # Wait enough to avoid double-pressing the same trial.
            time.sleep(0.9)

        ctx.logger.info(f"SPCPTNL completed main {label} block")

    def _wait_for_letter_block_to_start(self, ctx, timeout=20):
        """
        After the number block, the app shows a brief switch-to-letters screen.
        Do not wait for translated text. Wait for the first real letter image.
        """
        deadline = time.time() + timeout
        last_srcs = []

        while time.time() < deadline:
            srcs = self._visible_image_srcs(ctx)
            last_srcs = srcs

            for src in srcs:
                src_lower = src.lower()

                if "prac" in src_lower:
                    continue

                if "let" in src_lower:
                    ctx.logger.info("SPCPTNL letter block started")
                    return

            time.sleep(0.05)

        raise RuntimeError(
            "SPCPTNL timed out waiting for letter block to start; "
            f"last visible non-demo image srcs={[src.split('/')[-1] for src in last_srcs]}"
        )

    def run(self, ctx, strategy="correct"):
        errors = []

        try:
            ctx.logger.info("SPCPTNL starting")

            self._start_number_practice(ctx)

            self._run_practice(
                ctx,
                practice_prefix="pracNum",
                target_fragment="pracNum1",
                label="number",
                timeout=90,
            )

            self._start_letter_practice(ctx)

            self._run_practice(
                ctx,
                practice_prefix="pracLet",
                target_fragment="pracLet1",
                label="letter",
                timeout=90,
            )

            self._start_main_test(ctx)

            self._run_main_cpt_block(
                ctx,
                prefix="num",
                expected_trials=self.MAIN_NUMBER_TRIALS,
                label="number",
            )

            self._wait_for_letter_block_to_start(ctx, timeout=20)

            self._run_main_cpt_block(
                ctx,
                prefix="let",
                expected_trials=self.MAIN_LETTER_TRIALS,
                label="letter",
            )

            return TestRunResult(status="PASS", errors=errors)

        except Exception as exc:
            errors.append(str(exc))
            ctx.logger.exception("SPCPTNL failed")
            ctx.artifacts.capture_failure(ctx.driver, "spcptnl_failure", {"errors": errors})
            return TestRunResult(status="FAIL", errors=errors)
