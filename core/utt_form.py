from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select

UTT_TEMPLATE_PAGE_1_INPUT_VALUES = [
    {'name': 'age', 'value': 25, 'fill_method': 'text'},
    {'name': 'birth_year', 'value': 2000, 'fill_method': 'text'},
    {'name': 'sex', 'value': 'M', 'fill_method': 'select'},
    {'name': 'handedness', 'value': 'R', 'fill_method': 'click'},
    {'name': 'test_location', 'value': 'PR', 'fill_method': 'click'},
    {'name': 'education', 'value': 10, 'fill_method': 'text'},
    {'name': 'meducation', 'value': 10, 'fill_method': 'text'},
    {'name': 'feducation', 'value': 10, 'fill_method': 'text'},
    {'name': 'primary_language_eng', 'value': 'Y', 'fill_method': 'text'},
]


def fill_utt_form(ctx):
    for val in UTT_TEMPLATE_PAGE_1_INPUT_VALUES:
        try:
            elem = ctx.wait.clickable((By.NAME, val['name']), timeout=10)
            tag = elem.tag_name.lower()
            if val['fill_method'] == 'click':
                elem.click()
            elif val['fill_method'] == 'select' or tag == 'select':
                sel = Select(elem)
                try:
                    sel.select_by_value(str(val['value']))
                except Exception:
                    sel.select_by_visible_text(str(val['value']))
            else:
                elem.clear()
                elem.send_keys(val['value'])
                elem.send_keys(Keys.RETURN)
            ctx.logger.info(f"Filled UTT field: {val['name']} = {val['value']}")
        except Exception as exc:
            ctx.logger.warning(f"Could not fill UTT field {val['name']}: {exc}")
