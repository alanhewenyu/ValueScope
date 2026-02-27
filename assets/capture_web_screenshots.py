#!/usr/bin/env python3
"""Capture web GUI screenshots from running Streamlit app for README."""

import time
from playwright.sync_api import sync_playwright

URL = "http://localhost:8501"
OUTPUT_DIR = "/Users/Alan/valux/assets"
TICKER = "600519.SS"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.set_default_timeout(30000)

        # Navigate to Streamlit app
        page.goto(URL, wait_until="networkidle")
        time.sleep(3)

        # --- Screenshot 1: Landing page ---
        page.screenshot(path=f"{OUTPUT_DIR}/web-landing.png", full_page=False)
        print("Saved: web-landing.png")

        # Fill in ticker
        ticker_input = page.locator('input[aria-label*="stock symbol"]')
        ticker_input.click()
        ticker_input.fill(TICKER)

        # Click Manual Valuation (first one, in sidebar)
        page.locator('button:has-text("Manual Valuation")').first.click()

        # Wait for data to load
        print("Waiting for data to load...")
        page.wait_for_selector('text=Valuation Parameters', timeout=60000)
        time.sleep(3)

        # Dismiss any tooltips by clicking on empty area
        page.mouse.click(640, 5)
        time.sleep(0.5)

        # --- Screenshot 2: Parameters with sliders (no valuation header yet) ---
        main_area = page.locator('[data-testid="stMain"]')
        main_area.evaluate("el => el.scrollTop = 1050")
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/web-params.png", full_page=False)
        print("Saved: web-params.png")

        # Click Run DCF Valuation
        page.locator('button:has-text("Run DCF Valuation")').click()
        print("Waiting for DCF results...")
        page.wait_for_selector('text=WACC Sensitivity', timeout=30000)
        time.sleep(2)

        # Dismiss any tooltips
        page.mouse.click(640, 5)
        time.sleep(0.5)

        # --- Screenshot 3: Valuation header + interactive sliders (key screenshot) ---
        main_area.evaluate("el => el.scrollTop = 1050")
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/web-valuation.png", full_page=False)
        print("Saved: web-valuation.png")

        # --- Screenshot 4: Sensitivity analysis tables ---
        main_area.evaluate("el => el.scrollTop = 2800")
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/web-sensitivity.png", full_page=False)
        print("Saved: web-sensitivity.png")

        browser.close()
        print("\nAll web screenshots captured!")

if __name__ == "__main__":
    main()
