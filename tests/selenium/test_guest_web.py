import os

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


DEFAULT_SELECTORS = (
    "guest-player-shell",
    "guest-player-video",
    "guest-scoreboard",
    "guest-score-home",
    "guest-score-away",
    "guest-cart-items",
    "guest-cart",
    "guest-chat",
    "guest-auth-modal",
)


def _selectors():
    raw = os.getenv("GUEST_REQUIRED_SELECTORS")
    values = tuple(x.strip() for x in raw.split(",") if x.strip()) if raw else DEFAULT_SELECTORS
    if len(values) != 9:
        raise AssertionError("GUEST_REQUIRED_SELECTORS must contain exactly nine selectors")
    return values


@pytest.fixture
def browser():
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
    url = os.getenv("GUEST_WEB_URL", "http://127.0.0.1:8080/web/player")
    browser.get(url)
    WebDriverWait(browser, 15).until(lambda driver: driver.execute_script("return document.readyState") == "complete")
    for selector in _selectors():
        assert browser.find_elements(By.CSS_SELECTOR, f'[data-testid="{selector}"]'), selector


def test_guest_auth_modal_is_progressive(browser):
    browser.get(os.getenv("GUEST_WEB_URL", "http://127.0.0.1:8080/web/player"))
    browser.find_element(By.ID, "chat-open").click()
    modal = WebDriverWait(browser, 5).until(
        lambda driver: driver.find_element(By.CSS_SELECTOR, '[data-testid="guest-auth-modal"]')
    )
    assert modal.is_displayed()
