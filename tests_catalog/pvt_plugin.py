
            # If a numeric PVT counter unexpectedly appears again while we
            # believe practice is finished, surface that explicitly rather
            # than silently treating it as the main test.
            if self._counter_visible(ctx.driver):
                counter = None
                try:
                    counter = ctx.driver.find_element(
                        By.CSS_SELECTOR, self.COUNTER_SELECTOR
                    ).text
                except Exception:
                    pass

                raise RuntimeError(
                    "PVT counter reappeared while waiting for BEGIN TEST "
                    f"after {self.PRACTICE_TRIALS} practice trials "
                    f"(counter={counter!r})."
                )

            time.sleep(0.1)

        feedback = self._read_feedback(ctx)
        body_preview = ""
        try:
            body_preview = (
                ctx.driver.find_element(By.TAG_NAME, "body").text or ""
            ).strip().replace("\n", " | ")[:500]
        except Exception:
            pass

        raise TimeoutException(
            "PVT did not reach BEGIN TEST within "
            f"{timeout}s after practice. "
            f"feedback={feedback!r}; body={body_preview!r}"
        )

    def _delays_for_strategy(self, strategy: str) -> list[int]:
        strategy = (strategy or "perfect_300").strip().lower()

        if strategy == "mixed":
            return list(self.MIXED_DELAYS_MS)

        if strategy not in self.STRATEGY_DELAYS_MS:
            supported = sorted(list(self.STRATEGY_DELAYS_MS.keys()) + ["mixed"])
            raise ValueError(
                f"Unsupported PVT strategy {strategy!r}. "
                f"Supported strategies: {supported}"
            )

        return [
            self.STRATEGY_DELAYS_MS[strategy]
            for _ in range(self.TEST_TRIALS)
        ]

    def _run_main_test(self, ctx, strategy: str) -> list[dict]:
        delays = self._delays_for_strategy(strategy)

        if len(delays) != self.TEST_TRIALS:
            raise RuntimeError(
                f"PVT strategy {strategy!r} produced {len(delays)} responses; "
                f"expected {self.TEST_TRIALS}."
            )

        observations = []

        for trial_index, delay_ms in enumerate(delays, start=1):
            observations.append(
                self._respond_after_onset(
                    ctx,
                    delay_ms=delay_ms,
                    trial_label=f"test_{trial_index}",
                )
            )

        return observations

    def run(self, ctx, strategy: str = "perfect_300") -> TestRunResult:
        errors = []

        try:
            ctx.logger.info(
                "PVT starting test=%s strategy=%s",
                self.exact_code,
                strategy,
            )

            self._enter_practice(ctx)
            practice_observations = self._run_practice(ctx)

            ctx.logger.info(
                "PVT completed %d/%d practice trials.",
                len(practice_observations),
                self.PRACTICE_TRIALS,
            )

            self._enter_main_test(ctx)
            test_observations = self._run_main_test(ctx, strategy=strategy)

            ctx.logger.info(
                "PVT completed %d/%d scored trials.",
                len(test_observations),
                self.TEST_TRIALS,
            )

            ctx.pvt_observations = {
                "strategy": strategy,
                "practice": practice_observations,
                "test": test_observations,
            }

            if len(practice_observations) != self.PRACTICE_TRIALS:
                errors.append("PVT practice trial count mismatch.")

            if len(test_observations) != self.TEST_TRIALS:
                errors.append("PVT scored trial count mismatch.")

        except Exception as exc:
            ctx.logger.exception(
                "PVT plugin failed with strategy=%s",
                strategy,
            )
            errors.append(str(exc))

        if errors:
            return TestRunResult(status="FAIL", errors=errors)

        return TestRunResult(status="PASS", errors=[])
