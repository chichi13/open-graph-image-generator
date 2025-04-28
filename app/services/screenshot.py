import os
import tempfile
import time
from urllib.parse import urlparse

from PIL import Image, ImageOps
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from app.logger import logger

# Configurable Timeouts
PAGE_LOAD_TIMEOUT = 30
WAIT_AFTER_LOAD = 5
HIDE_ELEMENT_TIMEOUT = 2

# Common selectors for consent banners (add more as needed)
CONSENT_BANNER_SELECTORS = [
    ".cookie-consent-banner",
    "#cookie-notice",
    ".cookie-banner",
    ".consent-banner",
    "#onetrust-consent-sdk",
    "#CybotCookiebotDialog",
    "[id*='consent']",
    "[class*='consent']",
    "[aria-label*='consent']",
    "[aria-label*='cookie']",
    # Add more specific selectors based on common frameworks/widgets
]

# JavaScript to hide elements matching the selectors
# Uses try/catch for each selector to avoid errors if one doesn't exist
HIDE_ELEMENTS_JS = """
    const selectors = arguments[0];
    let hiddenCount = 0;
    selectors.forEach(selector => {
        try {
            const elements = document.querySelectorAll(selector);
            elements.forEach(el => {
                if (el.style.display !== 'none') {
                    el.style.display = 'none';
                    hiddenCount++;
                }
            });
        } catch (e) {
            // Ignore errors for selectors that might be invalid or not found
            // console.error(`Error finding/hiding selector '${selector}':`, e);
        }
    });
    return hiddenCount;
"""


def take_screenshot(url: str, width: int = 1200, height: int = 630) -> str:
    """Takes a screenshot, attempting to wait for load and hide consent banners."""
    logger.info(f"Attempting screenshot for {url} at {width}x{height}")
    parsed_url = urlparse(url)
    if not all([parsed_url.scheme in ["http", "https"], parsed_url.netloc]):
        raise ValueError(f"Invalid or unsupported URL scheme: {url}")

    options = ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument(
        "--disable-dev-shm-usage"
    )  # Overcomes limited resource problems
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--hide-scrollbars")
    options.add_argument("--disable-gpu")
    options.add_argument("--force-device-scale-factor=1")

    driver = None
    try:
        # Use webdriver-manager again to automatically handle driver download/update
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)

        logger.debug(f"Navigating to {url}")
        driver.get(url)
        logger.debug(
            f"Initial page load for {url} complete (readyState: "
            f"{driver.execute_script('return document.readyState')}). "
            "Waiting for body visibility..."
        )

        # --- Wait for basic page elements to be ready ---
        wait = WebDriverWait(driver, WAIT_AFTER_LOAD)
        logger.debug(f"Waiting up to {WAIT_AFTER_LOAD}s for body visibility...")
        wait.until(EC.visibility_of_element_located((By.TAG_NAME, "body")))

        logger.debug(
            f"Body visible. Waiting up to {WAIT_AFTER_LOAD}s for document readyState to be 'complete'..."
        )
        wait.until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        logger.info(f"Document readyState is complete for {url}.")
        # -------------------------------------------------

        # --- Attempt to hide consent banners AFTER waiting for readyState ---
        logger.debug(f"Attempting to hide consent banners for {url}")
        try:
            driver.set_script_timeout(HIDE_ELEMENT_TIMEOUT)
            hidden_count = driver.execute_script(
                HIDE_ELEMENTS_JS, CONSENT_BANNER_SELECTORS
            )
            logger.info(
                f"Executed banner hiding script for {url}. Potential banners hidden: {hidden_count}"
            )
        except TimeoutException:
            logger.warning(
                f"JavaScript timeout during banner hiding for {url}. Proceeding anyway."
            )
        except WebDriverException as e:
            logger.warning(
                f"WebDriverException during banner hiding for {url}: {e}. Proceeding anyway."
            )
        # -----------------------------------------

        # Wait for the page to load
        time.sleep(1)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
            initial_screenshot_path = temp_file.name

        logger.debug(
            f"Taking initial screenshot and saving to {initial_screenshot_path}"
        )
        if not driver.save_screenshot(initial_screenshot_path):
            if os.path.exists(initial_screenshot_path):
                os.remove(initial_screenshot_path)
            raise WebDriverException(f"Failed to save initial screenshot for {url}")

        # --- Log initial dimensions ---
        try:
            with Image.open(initial_screenshot_path) as img:
                logger.info(
                    f"Initial screenshot dimensions for {url}: {img.size}"
                )  # Log size BEFORE resize
        except Exception as img_err:
            logger.warning(f"Could not read initial screenshot dimensions: {img_err}")
        # -----------------------------

        # --- Resize the screenshot using Pillow ---
        logger.debug(
            f"Resizing screenshot from {initial_screenshot_path} to {width}x{height} while maintaining aspect ratio"
        )
        try:
            with Image.open(initial_screenshot_path) as img:
                # Use ImageOps.fit to crop to aspect ratio and resize
                # It centers, crops to the requested aspect ratio, and resizes.
                resized_img = ImageOps.fit(
                    img, (width, height), Image.Resampling.LANCZOS
                )
                # Overwrite the original temp file with the resized image
                resized_img.save(initial_screenshot_path, format="PNG")
                logger.info(
                    f"Screenshot successfully cropped/resized and saved to {initial_screenshot_path}"
                )
        except Exception as img_err:
            logger.error(
                f"Failed to resize screenshot {initial_screenshot_path}: {img_err}"
            )
            if os.path.exists(initial_screenshot_path):
                os.remove(initial_screenshot_path)
            raise
        # -----------------------------------------

        return initial_screenshot_path

    except TimeoutException as e:
        # Distinguish between page load timeout and wait timeout
        logger.error(f"Timeout occurred processing {url}: {e}")
        raise TimeoutException(
            f"Timeout waiting for page elements or during navigation for {url}"
        )
    except WebDriverException as e:
        logger.error(f"WebDriverException processing {url}: {e}")
        raise WebDriverException(f"Failed to process {url} with WebDriver: {e}")
    except Exception as e:
        logger.error(
            f"Unexpected error taking screenshot for {url}: {e}", exc_info=True
        )
        raise
    finally:
        if driver:
            logger.debug(f"Quitting WebDriver for {url}")
            driver.quit()
