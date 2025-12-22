"""
Selenium Balance Checker - Opens visible Chrome window
User logs in manually, then script reads balance automatically
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SeleniumBalanceChecker:
    """
    Opens Chrome, lets you login, then reads balance
    Saves session for auto-login next time
    """
    
    def __init__(self, profile_dir=None, headless=False):
        self.driver = None
        self.last_balance = None
        if profile_dir is None:
            import os
            import sys
            # Default to a local chrome_profile directory relative to exe/script location
            if getattr(sys, 'frozen', False):
                # Running as compiled exe
                app_dir = os.path.dirname(sys.executable)
            else:
                # Running as script - use script's directory
                app_dir = os.path.dirname(os.path.abspath(__file__))
            self.profile_dir = os.path.join(app_dir, "chrome_profile")
        else:
            self.profile_dir = profile_dir
        self.headless = headless
        
    def start_browser(self):
        """Start Chrome browser (visible or headless) with persistent profile"""
        try:
            import os
            import sys
            import subprocess
            
            chrome_options = Options()
            
            # Use a persistent profile directory to save login session
            chrome_options.add_argument(f"user-data-dir={self.profile_dir}")
            
            if self.headless:
                # Headless mode for background tracking
                chrome_options.add_argument("--headless=new")
                chrome_options.add_argument("--window-size=1920,1080")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-blink-features=AutomationControlled")
                chrome_options.add_argument("--log-level=3")
                chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                
                # Simple service
                from selenium.webdriver.chrome.service import Service
                service = Service(service_args=['--silent'])
                
                # Suppress Python logging
                logging.getLogger('selenium').setLevel(logging.CRITICAL)
                logging.getLogger('urllib3').setLevel(logging.CRITICAL)
                
                logger.info("✓ Chrome browser opened in HEADLESS mode")
            else:
                # Visible mode for login
                chrome_options.add_argument("--start-maximized")
                service = None
                logger.info("✓ Chrome browser opened with persistent profile")
            
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Create driver with service
            if service:
                self.driver = webdriver.Chrome(options=chrome_options, service=service)
            else:
                self.driver = webdriver.Chrome(options=chrome_options)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start browser: {e}")
            return False
    
    def navigate_to_balance_page(self):
        """Navigate to fal.ai balance page"""
        try:
            self.driver.get("https://fal.ai/dashboard/usage-billing/credits")
            logger.info("✓ Navigated to fal.ai balance page")
            return True
        except Exception as e:
            logger.error(f"Failed to navigate: {e}")
            return False
    
    def wait_for_login(self, timeout=60):
        """
        Wait for user to login manually (or check if already logged in)
        Checks if login is complete by looking for balance page elements
        """
        # First check if already logged in
        try:
            page_source = self.driver.page_source.lower()
            if 'sign in' not in page_source and 'login' not in page_source:
                if 'balance' in page_source or 'credit' in page_source or '$' in page_source:
                    logger.info("✓ Already logged in (session saved)!")
                    time.sleep(1)
                    return True
        except:
            pass
        
        print("\n" + "="*70)
        print("PLEASE LOG IN TO FAL.AI IN THE BROWSER WINDOW")
        print("="*70)
        print("\nWaiting for you to complete login...")
        print("(Your session will be saved for next time)")
        print()
        
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            try:
                # Check if we're on the balance page and logged in
                page_source = self.driver.page_source.lower()
                
                # Check if logged in (no sign-in button visible)
                if 'sign in' not in page_source and 'login' not in page_source:
                    # Look for balance indicators
                    if 'balance' in page_source or 'credit' in page_source or '$' in page_source:
                        logger.info("✓ Login detected!")
                        time.sleep(2)  # Wait for page to fully load
                        return True
                
                time.sleep(2)  # Check every 2 seconds
                
            except Exception as e:
                time.sleep(2)
                continue
        
        logger.warning("Timeout waiting for login")
        return False
    
    def get_balance(self):
        """
        Extract balance from the current page
        """
        try:
            # Get page source
            page_source = self.driver.page_source
            
            # Try multiple methods to find balance
            
            # Method 1: Look for specific balance elements
            try:
                # Try to find elements with balance-related text
                elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), '$')]")
                amounts = []
                
                for element in elements:
                    text = element.text
                    # Extract dollar amounts
                    matches = re.findall(r'\$\s*([\d,]+\.?\d*)', text)
                    for match in matches:
                        try:
                            amount = float(match.replace(',', ''))
                            if 0 < amount < 10000:  # Reasonable range
                                amounts.append(amount)
                        except:
                            continue
                
                if amounts:
                    balance = max(amounts)  # Likely the balance is the largest amount
                    self.last_balance = balance
                    logger.info(f"✓ Balance found: ${balance:.2f}")
                    return balance
            except:
                pass
            
            # Method 2: Parse from page source HTML
            amounts = re.findall(r'\$\s*([\d,]+\.?\d*)', page_source)
            if amounts:
                parsed = []
                for amount in amounts:
                    try:
                        val = float(amount.replace(',', ''))
                        if 0 < val < 10000:
                            parsed.append(val)
                    except:
                        continue
                
                if parsed:
                    balance = max(parsed)
                    self.last_balance = balance
                    logger.info(f"✓ Balance found: ${balance:.2f}")
                    return balance
            
            logger.warning("Could not find balance on page")
            return None
            
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return None
    
    def refresh_balance(self):
        """Refresh the page and get updated balance"""
        try:
            self.driver.refresh()
            time.sleep(2)  # Wait for page to load
            return self.get_balance()
        except Exception as e:
            logger.error(f"Error refreshing balance: {e}")
            return self.last_balance
    
    def close(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()
            logger.info("✓ Browser closed")


def test_selenium_balance():
    """Test the Selenium balance checker"""
    print("="*70)
    print("SELENIUM FAL.AI BALANCE CHECKER")
    print("="*70)
    print()
    
    checker = SeleniumBalanceChecker()
    
    # Start browser
    print("Starting Chrome browser...")
    if not checker.start_browser():
        print("Failed to start browser")
        return
    
    # Navigate to balance page
    print("Navigating to fal.ai...")
    if not checker.navigate_to_balance_page():
        print("Failed to navigate")
        checker.close()
        return
    
    # Wait for user to login
    if not checker.wait_for_login():
        print("\nTimeout - please try again")
        checker.close()
        return
    
    # Get balance
    print("\nReading balance from page...")
    balance = checker.get_balance()
    
    if balance:
        print(f"\n{'='*70}")
        print(f"SUCCESS! Current Balance: ${balance:.2f}")
        print(f"{'='*70}")
        print("\nThis can now check balance in real-time during video generation!")
        print("\nTesting refresh...")
        time.sleep(2)
        
        # Test refresh
        new_balance = checker.refresh_balance()
        if new_balance:
            print(f"Refreshed balance: ${new_balance:.2f}")
    else:
        print("\nCould not read balance from page")
        print("Please check if you're on the correct page")
    
    print("\nKeeping browser open for 10 seconds...")
    print("(In the real script, this stays open during processing)")
    time.sleep(10)
    
    # Close browser
    print("\nClosing browser...")
    checker.close()
    
    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70)


if __name__ == "__main__":
    test_selenium_balance()
