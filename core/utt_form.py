from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait


UTT_TEMPLATE_PAGE_1_INPUT_VALUES = [
    {"name": "age", "value": 25, "fill_method": "text"},
    {"name": "birth_year", "value": 2000, "fill_method": "text"},
    {"name": "sex", "value": "M", "fill_method": "select"},
    {"name": "handedness", "value": "R", "fill_method": "radio"},
    {"name": "test_location", "value": "PR", "fill_method": "radio"},
    {"name": "education", "value": 10, "fill_method": "select"},
    {"name": "meducation", "value": 10, "fill_method": "select"},
    {"name": "feducation", "value": 10, "fill_method": "select"},
    {"name": "primary_language_eng", "value": "Y", "fill_method": "select"},
]


def _set_text(ctx, name, value):
    elem = ctx.wait.clickable((By.NAME, name), timeout=10)
    elem.clear()
    elem.send_keys(str(value))


def _set_select(ctx, name, value):
    elem = ctx.wait.clickable((By.NAME, name), timeout=10)
    select = Select(elem)
    select.select_by_value(str(value))


def _set_radio(ctx, name, value):
    selector = f'input[type="radio"][name="{name}"][value="{value}"]'
    elem = ctx.wait.present((By.CSS_SELECTOR, selector), timeout=10)
    ctx.driver.execute_script("arguments[0].click();", elem)


def _fill_field(ctx, field):
    name = field["name"]
    value = field["value"]
    fill_method = field.get("fill_method", "text")

    elem = ctx.wait.present((By.NAME, name), timeout=10)
    tag = elem.tag_name.lower()

    if fill_method in ("radio", "click"):
        _set_radio(ctx, name, value)

    elif fill_method == "select" or tag == "select":
        _set_select(ctx, name, value)

    else:
        _set_text(ctx, name, value)

    ctx.logger.info(f"Filled UTT field: {name} = {value}")


def submit_utt_form(ctx, timeout=10):
    """
    Submit the translated or English UTT registration form without relying
    on visible button text.

    Handles pages where the button is:
      <button type="submit" name="Register" value="Submit">...</button>

    and also keeps fallbacks for older English pages.
    """
    form = ctx.wait.present((By.CSS_SELECTOR, "form#register-form"), timeout=timeout)

    submit_selectors = [
        'button[type="submit"][name="Register"]',
        'input[type="submit"][name="Register"]',
        'button.button-form[type="submit"]',
        'button[type="submit"]',
        'input[type="submit"]',
        '[name="RegisterParticipant"]',
    ]

    last_error = None

    for selector in submit_selectors:
        try:
            submit = form.find_element(By.CSS_SELECTOR, selector)

            ctx.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
                submit,
            )

            old_url = ctx.driver.current_url
            ctx.driver.execute_script("arguments[0].click();", submit)

            ctx.logger.info(f"Submitted UTT registration form using selector: {selector}")

            # Wait briefly for either navigation or document readiness.
            try:
                WebDriverWait(ctx.driver, 10).until(
                    lambda d: d.current_url != old_url
                    or d.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                pass

            return True

        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Could not submit UTT registration form: {last_error}")


def fill_utt_form(ctx, submit=True):
    """
    Backward-compatible main entry point.

    Your runner already calls fill_utt_form(ctx), so this now fills and submits
    by default. That avoids the old broken RegisterParticipant selector path.
    """
    ctx.wait.present((By.CSS_SELECTOR, "form#register-form"), timeout=15)

    for field in UTT_TEMPLATE_PAGE_1_INPUT_VALUES:
        try:
            _fill_field(ctx, field)
        except Exception as exc:
            ctx.logger.warning(f"Could not fill UTT field {field['name']}: {exc}")

    if submit:
        submit_utt_form(ctx)


def complete_utt_form(ctx):
    fill_utt_form(ctx, submit=True)


def fill_and_submit_utt_form(ctx):
    fill_utt_form(ctx, submit=True)