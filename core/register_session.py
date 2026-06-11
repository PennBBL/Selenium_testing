import argparse
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
import time
import random
import itertools
import os
import uuid

"""

   Helper to fill register a new participant session.
   Customze the `utt_template_page_1_input_values` values.

"""


### Values to use for the UTT template.
utt_template_page_1_input_values = [
{"name" : "age", "value" : 25, "fill_method" : "text"},
{"name" : "birth_year", "value" : 2000, "fill_method" : "text"},
{"name" : "sex", "value" : "M", "fill_method" : "text"},
{"name" : "handedness", "value" : "R", "fill_method" : "click"},
{"name" : "test_location", "value" : "PR", "fill_method" : "click"},
{"name" : "education", "value" : 10, "fill_method" : "text"},
{"name" : "meducation", "value" : 10, "fill_method" : "text"},
{"name" : "feducation", "value" : 10, "fill_method" : "text"},
{"name" : "primary_language_eng", "value" : "Y", "fill_method" : "text"},
]

### Time duration for waiting between the pages.
ACTION_WAIT_TIME = 3

"""

 Fill the UTT template.

"""
def fill_utt_template_page_1(driver):
    for val in utt_template_page_1_input_values:
        elem = driver.find_element(By.NAME, val['name'])

        if val['fill_method'] == 'click':
            elem.click()
        else:
            elem.send_keys(val['value'])
            elem.send_keys(Keys.RETURN)

    time.sleep(ACTION_WAIT_TIME)
    register_elem = driver.find_element(By.NAME, 'RegisterParticipant')
    register_elem.click()


"""

 Click through the battery instructions.

"""
def skim_battery_welcome(driver):
    time.sleep(ACTION_WAIT_TIME)
    driver.find_element(By.XPATH, '//center/div[1]/button').click()
    time.sleep(ACTION_WAIT_TIME)
    driver.find_element(By.NAME, 'StartTest').click()
    time.sleep(ACTION_WAIT_TIME)


"""

Register a participant session.
Fill the UTT template and click through the rest of the pages.

"""
def register_session(driver, link):
    fill_utt_template_page_1(driver)
    time.sleep(ACTION_WAIT_TIME)
    link2 = link.replace("op=Init", "op=BatteryIntroduction")
    driver.get(link2)
    skim_battery_welcome(driver)
    time.sleep(ACTION_WAIT_TIME)
