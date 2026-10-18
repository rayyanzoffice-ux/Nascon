import os

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


DEFAULT_SELECTORS = (
    "guest-video-player",
    "live-score-banner",
    "pinned-merch-card",
    "add-to-guest-cart-btn",
    "guest-cart-count",
    "chat-message-list",
    "chat-input-field",
    "chat-send-btn",
    "progressive-auth-modal",
)


def _selectors():
    raw = os.getenv("GUEST_REQUIRED_SELECTORS")
    values = tuple(x.strip() for x in raw.split(",") if x.strip()) if raw else DEFAULT_SELECTORS
    if len(values) != 9:
        raise AssertionError("GUEST_REQUIRED_SELECTORS must contain exactly nine selectors")
    return values


@pytest.fixture
def browser(worker_id):
    if worker_id == "gw2":
        options = FirefoxOptions()
        options.add_argument("-headless")
    else:
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Remote(
        command_executor=os.getenv("SELENIUM_GRID_URL", "http://127.0.0.1:4444/wd/hub"),
        options=options,
    )
    try:
        yield driver
    finally:
        driver.quit()


def test_guest_player_exposes_required_controls(browser):
    url = os.getenv("GUEST_WEB_URL", "http://api:8080/q/m1-live")
    browser.get(url)
    WebDriverWait(browser, 15).until(lambda driver: driver.execute_script("return document.readyState") == "complete")
    for selector in _selectors():
        assert browser.find_elements(By.CSS_SELECTOR, f'[data-testid="{selector}"]'), selector


def test_guest_auth_modal_is_progressive(browser):
    browser.get(os.getenv("GUEST_WEB_URL", "http://api:8080/q/m1-live"))
    browser.find_element(By.CSS_SELECTOR, '[data-testid="chat-input-field"]').send_keys("hello")
    browser.find_element(By.CSS_SELECTOR, '[data-testid="chat-send-btn"]').click()
    modal = WebDriverWait(browser, 5).until(
        lambda driver: driver.find_element(By.CSS_SELECTOR, '[data-testid="progressive-auth-modal"]')
    )
    assert modal.is_displayed()


def test_guest_cart_stages_required_variant(browser):
    browser.get(os.getenv("GUEST_WEB_URL", "http://api:8080/q/m1-live"))
    browser.find_element(By.CSS_SELECTOR, '[data-testid="add-to-guest-cart-btn"]').click()
    count = WebDriverWait(browser, 3).until(
        lambda driver: driver.find_element(By.CSS_SELECTOR, '[data-testid="guest-cart-count"]').text
    )
    assert count == "1"
