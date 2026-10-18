import os

import pytest


appium_url = os.getenv("APPIUM_SERVER_URL")
pytestmark = pytest.mark.skipif(
    not appium_url,
    reason="APPIUM_SERVER_URL is not configured; no mobile execution is claimed",
)


def test_android_guest_deep_link_opens_configured_app():
    from appium import webdriver
    from appium.options.android import UiAutomator2Options

    options = UiAutomator2Options()
    options.platform_name = os.getenv("APPIUM_PLATFORM", "Android")
    options.device_name = os.getenv("APPIUM_DEVICE", "Android Emulator")
    options.automation_name = "UiAutomator2"
    options.no_reset = True
    driver = webdriver.Remote(appium_url, options=options)
    try:
        driver.execute_script(
            "mobile: deepLink",
            {
                "url": os.getenv("ANDROID_DEEP_LINK", "nascon://guest/player"),
                "package": os.environ["ANDROID_APP_PACKAGE"],
            },
        )
        assert driver.current_package == os.environ["ANDROID_APP_PACKAGE"]
    finally:
        driver.quit()
