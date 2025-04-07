from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def login_to_brandwatch_retry(email, password, max_retries=3):
    chrome_options = webdriver.ChromeOptions()
    # Ensuring it's NOT headless, for visual debugging:
    # chrome_options.headless = False
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.maximize_window()

    try:
        driver.get(
            "https://login.brandwatch.com/login?client_id=my-brandwatch-prod-client"
            "&interactionUid=4KnWs-oUTHM19K0nJrES4&product_code=mybrandwatch"
        )
        
        wait = WebDriverWait(driver, 15)
        
        for attempt in range(1, max_retries + 1):
            print(f"\n=== Attempt #{attempt} to log in ===")
            
            # Wait for email field
            email_input = wait.until(EC.presence_of_element_located((By.NAME, "email")))
            # Clear it first (in case we're retrying)
            email_input.clear()
            email_input.send_keys(email)
            
            # Wait for password field
            password_input = wait.until(EC.presence_of_element_located((By.NAME, "password")))
            # Clear if retrying
            password_input.clear()
            password_input.send_keys(password)

            # Press ENTER to submit
            password_input.send_keys(Keys.ENTER)
            
            # Wait a few seconds for navigation
            time.sleep(5)

            # Check if we're still on the *exact same sign-in page*
            current_url = driver.current_url
            page_title = driver.title

            # If the page title or URL indicates we've left the sign-in page, break
            # Often the Brandwatch sign in page is titled "Brandwatch | Sign in"
            if "Sign in" not in page_title:
                print("We appear to have left the sign-in page. Stopping retries.")
                break
            else:
                print("Still on the sign-in page; either credentials are incorrect or SSO is required.")
                # If we're not on the last attempt, let's continue to next attempt.
                if attempt < max_retries:
                    print("Retrying login...")
                else:
                    print("Max retries reached. Will stop now.")

        # Debug output after attempts
        print("\n=== DEBUG INFO AFTER LOGIN ATTEMPTS ===")
        print("Current URL:", driver.current_url)
        print("Page Title:", driver.title)

        # Print first 500 characters of the final page source
        page_source = driver.page_source
        print("\nPage Source (first 500 chars):")
        print(page_source[:500])
        print("... [truncated] ...")

        # Optional: look for generic error text
        possible_error_selectors = [
            "//div[contains(text(), 'error')]",
            "//span[contains(text(), 'error')]",
            "//div[contains(text(), 'invalid')]",
            "//span[contains(text(), 'invalid')]",
            "//div[@class='ax-form__error']"
        ]
        
        found_any_error = False
        for selector in possible_error_selectors:
            try:
                error_elem = driver.find_element(By.XPATH, selector)
                if error_elem:
                    print(f"\n**Possible error element found via {selector}:**\n{error_elem.text}")
                    found_any_error = True
            except:
                pass
        
        if not found_any_error:
            print("\nNo obvious error messages found with the guessed selectors.")

        # Save final screenshot
        screenshot_path = "login_debug_retry.png"
        driver.save_screenshot(screenshot_path)
        print(f"\nSaved screenshot to: {screenshot_path}")
        
        # Pause for a bit to visually confirm final page state
        time.sleep(3)

    finally:
        driver.quit()

if __name__ == "__main__":
    login_to_brandwatch_retry(
        email="jordanb@fcas.org",
        password="Jazzmaster12!@#",  # Replace with your real password
        max_retries=3
    )

