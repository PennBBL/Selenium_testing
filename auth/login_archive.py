import argparse
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver import ActionChains
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.mouse_button import MouseButton
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random
import itertools
from dotenv import load_dotenv
import os
import uuid

# Load environment variables from the .env file
load_dotenv()
adminid = os.getenv('adminid')
pwd = os.getenv('pwd')

"""
 Log in to the CNB webpage.
"""
def selenium_login(driver, webpage):
    # Step 1: open the login page
    driver.get(webpage)

    wait = WebDriverWait(driver, 10)

    # Step 2: enter username
    username_element = wait.until(EC.presence_of_element_located((By.NAME, "adminid")))
    username_element.send_keys(adminid)

    # Step 3: enter password
    pwd_element = wait.until(EC.presence_of_element_located((By.NAME, "pwd")))
    pwd_element.send_keys(pwd)

    # Step 4: click login button
    login_btn_element = wait.until(EC.element_to_be_clickable((By.NAME, "Login")))
    login_btn_element.click()

# Example usage
if __name__ == "__main__":
    driver = webdriver.Chrome()
    selenium_login(driver, "https://penncnp-dev.pmacs.upenn.edu/assessments.pl")  # replace with actual CNB login URL
