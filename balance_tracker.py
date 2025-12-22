"""
Real-time Balance Tracker for Kling UI
Integrates with Selenium Balance Checker
"""

import threading
import time
from typing import Optional, Callable
from selenium_balance_checker import SeleniumBalanceChecker


class RealTimeBalanceTracker:
    """
    Background thread that monitors fal.ai balance in real-time
    """
    
    def __init__(self, update_interval: int = 30):
        self.checker = None
        self.update_interval = update_interval  # seconds
        self.running = False
        self.thread = None
        self.current_balance = None
        self.initial_balance = None
        self.total_spent = 0.0
        self.callback = None
        self.cost_per_video = 0.70  # fal.ai cost
        
    def set_callback(self, callback: Callable):
        """Set callback function to update UI"""
        self.callback = callback
    
    def start(self):
        """Start the balance tracking thread"""
        if self.running:
            return True
        
        try:
            import os
            import sys
            import logging
            
            # SUPPRESS ALL OUTPUT - stderr, stdout, and logging
            if os.name == 'nt':  # Windows
                # Save originals
                self._original_stderr = sys.stderr
                self._original_stdout = sys.stdout
                # Redirect everything to NUL
                devnull = open('NUL', 'w')
                sys.stderr = devnull
                sys.stdout = devnull
            
            # Suppress selenium and Chrome logging at every level
            os.environ['WDM_LOG_LEVEL'] = '0'
            os.environ['WDM_PRINT_FIRST_LINE'] = 'False'
            os.environ['WDM_LOG'] = '0'
            
            # Disable all logging
            logging.getLogger('selenium').setLevel(logging.CRITICAL)
            logging.getLogger('urllib3').setLevel(logging.CRITICAL)
            logging.getLogger('WDM').setLevel(logging.CRITICAL)
            logging.disable(logging.CRITICAL)
            
            # Initialize selenium checker in HEADLESS mode
            self.checker = SeleniumBalanceChecker(headless=True)
            
            # Start browser and get initial balance
            if not self.checker.start_browser():
                # Restore output
                if os.name == 'nt':
                    sys.stderr = self._original_stderr
                    sys.stdout = self._original_stdout
                # Silently fail - don't print anything
                return False
            
            if not self.checker.navigate_to_balance_page():
                # Restore output
                if os.name == 'nt':
                    sys.stderr = self._original_stderr
                    sys.stdout = self._original_stdout
                self.checker.close()
                # Silently fail - don't print anything
                return False
            
            # In headless mode, page needs more time to load - wait 8 seconds
            time.sleep(8)
            
            # Get initial balance with retry (headless mode can be slower)
            max_retries = 3
            for attempt in range(max_retries):
                self.initial_balance = self.checker.get_balance()
                if self.initial_balance is not None:
                    break
                if attempt < max_retries - 1:
                    time.sleep(3)  # Wait 3 more seconds between retries
            
            self.current_balance = self.initial_balance
            
            if self.initial_balance is None:
                # Restore output
                if os.name == 'nt':
                    sys.stderr = self._original_stderr
                    sys.stdout = self._original_stdout
                self.checker.close()
                # Silently fail - don't print anything
                return False
            
            # Start background thread
            self.running = True
            self.thread = threading.Thread(target=self._update_loop, daemon=True)
            self.thread.start()
            
            # Restore output now that browser is running
            if os.name == 'nt':
                sys.stderr = self._original_stderr
                sys.stdout = self._original_stdout
            
            return True
            
        except Exception as e:
            # Restore output
            if os.name == 'nt' and hasattr(self, '_original_stderr'):
                sys.stderr = self._original_stderr
                if hasattr(self, '_original_stdout'):
                    sys.stdout = self._original_stdout
            # Silently fail - don't print anything
            if self.checker:
                self.checker.close()
            return False
    
    def _update_loop(self):
        """Background loop to update balance"""
        while self.running:
            try:
                # Refresh balance
                new_balance = self.checker.refresh_balance()
                
                if new_balance is not None:
                    self.current_balance = new_balance
                    
                    # Calculate spent
                    if self.initial_balance is not None:
                        self.total_spent = self.initial_balance - self.current_balance
                    
                    # Notify callback
                    if self.callback:
                        self.callback(self.current_balance, self.total_spent)
                
                # Wait before next update
                time.sleep(self.update_interval)
                
            except Exception as e:
                print(f"Error updating balance: {e}")
                time.sleep(self.update_interval)
    
    def stop(self):
        """Stop the balance tracking"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.checker:
            self.checker.close()
    
    def get_balance_info(self):
        """Get current balance information"""
        return {
            'current': self.current_balance,
            'initial': self.initial_balance,
            'spent': self.total_spent,
            'remaining_videos': int(self.current_balance / self.cost_per_video) if self.current_balance else 0
        }
    
    def increment_video_cost(self):
        """Manually increment cost when video completes"""
        self.total_spent += self.cost_per_video
        if self.current_balance is not None:
            self.current_balance -= self.cost_per_video
