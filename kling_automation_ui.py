import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
import logging
import tkinter as tk
from tkinter import filedialog

# Import path utilities for frozen exe compatibility
from path_utils import get_config_path, get_crash_log_path, get_app_dir

# Import the fal.ai KlingBatchGenerator
from kling_generator_falai import FalAIKlingGenerator

class KlingAutomationUI:
    def __init__(self):
        self.config_file = get_config_path("kling_config.json")
        self.config = self.load_config()
        self.verbose_logging = self.config.get("verbose_logging", False)
        self.setup_logging()
        self.check_first_run_api_key()

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default"""
        # Default prompt slot 1 - basic head turn
        prompt_slot_1 = (
            "Turn head to the right slowly then all the way to the left slowly then to the right slowly, and to the left slowly. "
            "Make sure the body is kept still while doing this - ONLY turn THE HEAD NOT THE BODY. The subject should perform smooth, "
            "natural head movements with no body movement whatsoever. Keep shoulders, neck, and torso completely stationary. "
            "Head movements should be slow, deliberate, and realistic. Eyes can follow natural movement patterns. "
            "Maintain neutral facial expression throughout. Camera remains fixed and stationary. "
            "Generate in maximum resolution and professional quality with no blur, pixelation, or quality degradation."
        )

        # Default prompt slot 2 - enhanced lifelike animation (recommended)
        prompt_slot_2 = (
            "Generate a lifelike video animation from the provided image. The subject must rotate only their head in an exceptionally slow, "
            "smooth, and biologically realistic motion: start by gently turning the head left, up to 70 degrees from center, with absolutely "
            "no movement in the shoulders, neck, or upper body, which must stay perfectly upright and still. Hold a brief, natural pause at "
            "the leftmost position, then gently turn the head all the way to the right, maintaining the same extremely slow and continuous, "
            "lifelike pace. Head motion must appear completely natural, never robotic, mechanical, stiff, or artificial—mimic genuine human "
            "motion with soft micro-adjustments. Eyes stay focused on the camera lens through both turns. Facial expression remains strictly "
            "neutral and relaxed throughout. Lighting on the face and background must stay natural, matching the original image, with no added "
            "highlights, shadows, flicker, or artificial lighting. The camera is fixed and stationary. Only the head moves; the rest of the body remains motionless."
        )

        default_config = {
            "output_folder": "",  # Empty by default - user picks their own
            "use_source_folder": True,  # Default: save videos alongside source images
            "falai_api_key": "",  # Will prompt user on first run
            "verbose_logging": True,
            "duplicate_detection": True,
            "delay_between_generations": 1,
            # Prompt slot system - default to slot 2 (enhanced prompt)
            "current_prompt_slot": 2,
            "saved_prompts": {
                "1": prompt_slot_1,
                "2": prompt_slot_2,
                "3": None
            },
            # Model configuration - Kling 2.5 Turbo Pro
            "current_model": "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
            "model_display_name": "Kling 2.5 Turbo Pro",
            "video_duration": 10
        }

        try:
            if Path(self.config_file).exists():
                with open(self.config_file, 'r') as f:
                    loaded_config = json.load(f)
                    # Merge with defaults, ensuring new fields exist
                    merged = {**default_config, **loaded_config}
                    # Ensure saved_prompts has all slots
                    if "saved_prompts" not in merged:
                        merged["saved_prompts"] = default_config["saved_prompts"]
                    else:
                        for slot in ["1", "2", "3"]:
                            if slot not in merged["saved_prompts"]:
                                merged["saved_prompts"][slot] = None
                    return merged
        except Exception:
            pass
        return default_config

    def get_current_prompt(self) -> str:
        """Get the current prompt from the active slot"""
        slot = str(self.config.get("current_prompt_slot", 1))
        saved = self.config.get("saved_prompts", {})
        prompt = saved.get(slot)
        if prompt:
            return prompt
        # Fallback to default
        return self.get_default_prompt()

    def get_default_prompt(self) -> str:
        """Get the default head movement prompt"""
        return (
            "Turn head to the right slowly then all the way to the left slowly then to the right slowly, and to the left slowly. "
            "Make sure the body is kept still while doing this - ONLY turn THE HEAD NOT THE BODY. The subject should perform smooth, "
            "natural head movements with no body movement whatsoever. Keep shoulders, neck, and torso completely stationary. "
            "Head movements should be slow, deliberate, and realistic. Eyes can follow natural movement patterns. "
            "Maintain neutral facial expression throughout. Camera remains fixed and stationary. "
            "Generate in maximum resolution and professional quality with no blur, pixelation, or quality degradation."
        )

    def fetch_model_pricing(self, model_endpoint: str) -> Optional[float]:
        """Fetch pricing for a model from fal.ai API"""
        try:
            import requests
            headers = {"Authorization": f"Key {self.config['falai_api_key']}"}
            response = requests.get(
                f"https://api.fal.ai/v1/models/pricing?endpoint_id={model_endpoint}",
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                prices = data.get("prices", [])
                if prices:
                    return prices[0].get("unit_price")
        except Exception:
            pass
        return None

    def fetch_available_models(self) -> list:
        """Fetch available video models from fal.ai Platform API with pagination"""
        try:
            import requests
            headers = {"Authorization": f"Key {self.config['falai_api_key']}"}
            all_models = []
            cursor = None

            # Paginate through all results
            while True:
                params = {"category": "image-to-video", "status": "active", "limit": 50}
                if cursor:
                    params["cursor"] = cursor

                response = requests.get(
                    "https://api.fal.ai/v1/models",
                    params=params,
                    headers=headers,
                    timeout=15
                )

                if response.status_code != 200:
                    if self.verbose_logging:
                        print(f"\033[91mAPI returned status {response.status_code}\033[0m")
                    break

                data = response.json()
                for m in data.get("models", []):
                    endpoint_id = m.get("endpoint_id", "")
                    metadata = m.get("metadata", {})
                    description = metadata.get("description", "")
                    # Keep up to 200 chars for wrapping (3 lines of ~65 chars)
                    if len(description) > 200:
                        description = description[:197] + "..."
                    all_models.append({
                        "name": metadata.get("display_name", endpoint_id),
                        "endpoint_id": endpoint_id,
                        "description": description,
                        "duration": metadata.get("duration_estimate", 10),
                    })

                # Check for more pages
                if data.get("has_more") and data.get("next_cursor"):
                    cursor = data["next_cursor"]
                else:
                    break

            # Batch fetch pricing for all models (up to 50 at a time)
            if all_models:
                endpoint_ids = [m["endpoint_id"] for m in all_models]
                prices = self.fetch_batch_pricing(endpoint_ids)
                for model in all_models:
                    model["price"] = prices.get(model["endpoint_id"])

            if all_models:
                return all_models

        except Exception as e:
            if self.verbose_logging:
                print(f"\033[91mError fetching models: {e}\033[0m")

        # Fallback to curated list if API fails
        return [
            {"name": "Kling 2.1 Professional", "endpoint_id": "fal-ai/kling-video/v2.1/pro/image-to-video", "duration": 10, "description": "Professional quality video generation"},
            {"name": "Kling 2.5 Turbo Pro", "endpoint_id": "fal-ai/kling-video/v2.5-turbo/pro/image-to-video", "duration": 5, "description": "Fast turbo video generation"},
            {"name": "Kling O1", "endpoint_id": "fal-ai/kling-video/o1/image-to-video", "duration": 10, "description": "Kling O1 model"},
            {"name": "Wan 2.5", "endpoint_id": "fal-ai/wan-25-preview/image-to-video", "duration": 5, "description": "Best open source video model with sound"},
            {"name": "Veo 3", "endpoint_id": "fal-ai/veo3/image-to-video", "duration": 8, "description": "Google Veo 3 video generation"},
            {"name": "Ovi", "endpoint_id": "fal-ai/ovi/image-to-video", "duration": 5, "description": "Ovi video generation"},
            {"name": "LTX-2", "endpoint_id": "fal-ai/ltx-2/image-to-video", "duration": 5, "description": "LTX-2 video model"},
            {"name": "Pixverse V5", "endpoint_id": "fal-ai/pixverse/v5/image-to-video", "duration": 4, "description": "Pixverse V5 video generation"},
            {"name": "Hunyuan Video", "endpoint_id": "fal-ai/hunyuan-video/image-to-video", "duration": 5, "description": "Tencent Hunyuan video model"},
            {"name": "MiniMax Video", "endpoint_id": "fal-ai/minimax-video/image-to-video", "duration": 6, "description": "MiniMax video generation"},
        ]

    def fetch_batch_pricing(self, endpoint_ids: list) -> dict:
        """Fetch pricing for multiple models at once (max 50)"""
        prices = {}
        try:
            import requests
            headers = {"Authorization": f"Key {self.config['falai_api_key']}"}

            # Process in batches of 50
            for i in range(0, len(endpoint_ids), 50):
                batch = endpoint_ids[i:i+50]
                response = requests.get(
                    "https://api.fal.ai/v1/models/pricing",
                    params={"endpoint_id": batch},
                    headers=headers,
                    timeout=15
                )
                if response.status_code == 200:
                    data = response.json()
                    for p in data.get("prices", []):
                        endpoint = p.get("endpoint_id", "")
                        unit_price = p.get("unit_price")
                        unit = p.get("unit", "")
                        prices[endpoint] = {"price": unit_price, "unit": unit}
        except Exception:
            pass
        return prices
    
    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            if self.verbose_logging:
                print(f"Error saving config: {e}")
    
    def setup_logging(self):
        """Setup logging based on verbose setting"""
        if self.verbose_logging:
            logging.basicConfig(
                level=logging.INFO, 
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler('kling_automation.log'),
                    logging.StreamHandler()
                ]
            )
        else:
            logging.basicConfig(
                level=logging.ERROR,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[logging.FileHandler('kling_automation.log')]
            )
            logging.getLogger().setLevel(logging.CRITICAL)

    def check_first_run_api_key(self):
        """Check if API key is configured, prompt user on first run"""
        if not self.config.get("falai_api_key", "").strip():
            self.clear_screen_simple()
            print("\n" + "=" * 60)
            print("  KLING UI - First Time Setup")
            print("=" * 60)
            print("\nWelcome! To use this tool, you need a fal.ai API key.")
            print("\nTo get your API key:")
            print("  1. Go to https://fal.ai")
            print("  2. Create an account or sign in")
            print("  3. Navigate to your API keys section")
            print("  4. Create and copy your API key")
            print("\n" + "-" * 60)

            while True:
                api_key = input("\nEnter your fal.ai API key: ").strip()
                if api_key:
                    self.config["falai_api_key"] = api_key
                    self.save_config()
                    print("\n✓ API key saved successfully!")
                    print("  Your settings are stored in kling_config.json")
                    input("\nPress Enter to continue...")
                    break
                else:
                    print("API key cannot be empty. Please try again.")

    def clear_screen_simple(self):
        """Clear screen without dependencies"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def clear_screen(self):
        """Clear terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def print_cyan(self, text):
        """Print text in cyan color"""
        print(f"\033[96m{text}\033[0m")
    
    def print_light_purple(self, text):
        """Print text in light purple color"""
        print(f"\033[94m{text}\033[0m")
    
    def print_magenta(self, text):
        """Print text in magenta color"""  
        print(f"\033[95m{text}\033[0m")
        
    def print_green(self, text):
        """Print text in green color"""
        print(f"\033[92m{text}\033[0m", end="")
    
    def print_yellow(self, text):
        """Print text in yellow color"""
        print(f"\033[93m{text}\033[0m")
        
    def print_red(self, text):
        """Print text in red color"""
        print(f"\033[91m{text}\033[0m")
    
    def display_header(self):
        """Display the main header with dynamic model info"""
        self.clear_screen()

        model_name = self.config.get("model_display_name", "Kling 2.1 Professional")
        duration = self.config.get("video_duration", 10)

        # Fetch pricing (cached after first call)
        if not hasattr(self, '_cached_price'):
            self._cached_price = self.fetch_model_pricing(self.config.get("current_model", ""))
        price = self._cached_price
        price_str = f"${price:.2f}/sec" if price else "Check fal.ai"

        # Beautiful header with horizontal-only borders
        print("\033[38;5;27m" + "═" * 79 + "\033[0m")
        print()

        # ASCII art title
        title_art = "🎬  FAL.AI VIDEO GENERATOR  🎬"
        padding = (79 - len(title_art)) // 2
        print(f"\033[1;97m{' ' * padding}{title_art}\033[0m")

        print()
        print("\033[38;5;27m" + "─" * 79 + "\033[0m")

        # Model info row
        print(f"  Model: \033[95m{model_name}\033[0m")

        # Config row
        print(f"  Duration: \033[92m{duration}s\033[0m   ·   Price: \033[93m{price_str}\033[0m   ·   Workers: \033[96m5\033[0m")

        # Balance link row
        print(f"  💰 Balance: \033[90mhttps://fal.ai/dashboard\033[0m")

        print()
        print("\033[38;5;27m" + "═" * 79 + "\033[0m")
        print()
    
    def display_configuration_menu(self):
        """Display configuration setup menu with full prompt display"""
        self.print_magenta("═" * 79)
        self.print_magenta("                           CONFIGURATION SETUP                                ")
        self.print_magenta("═" * 79)
        print()

        self.print_cyan("─" * 79)
        self.print_cyan(" INPUT CONFIGURATION")
        self.print_cyan("─" * 79)
        print()

        # Show output mode with clear indication
        use_source = self.config.get('use_source_folder', True)
        if use_source:
            print(f"  \033[92m📂 Output Mode: SAME FOLDER AS SOURCE IMAGES\033[0m")
            print(f"     \033[90m(Videos saved alongside each input image)\033[0m")
        else:
            print(f"  \033[93m📂 Output Mode: CUSTOM FOLDER\033[0m")
            print(f"     \033[97m{self.config['output_folder']}\033[0m")
        print()

        # Show full prompt with wrapping
        current_slot = self.config.get("current_prompt_slot", 1)
        current_prompt = self.get_current_prompt()
        slot_label = f"Slot {current_slot}"
        if not self.config.get("saved_prompts", {}).get(str(current_slot)):
            slot_label += " (default)"

        print(f"  \033[95mCurrent prompt ({slot_label}):\033[0m")
        print("  \033[90m" + "─" * 73 + "\033[0m")

        # Wrap prompt text at 70 chars
        words = current_prompt.split()
        line = "  "
        for word in words:
            if len(line) + len(word) + 1 <= 73:
                line += word + " "
            else:
                print(f"\033[97m{line}\033[0m")
                line = "  " + word + " "
        if line.strip():
            print(f"\033[97m{line}\033[0m")

        print("  \033[90m" + "─" * 73 + "\033[0m")
        print()

        self.print_cyan("─" * 79)
        self.print_cyan(" AVAILABLE OPTIONS")
        self.print_cyan("─" * 79)
        print()

        verbose_status = "\033[92mON\033[0m" if self.verbose_logging else "\033[91mOFF\033[0m"
        model_name = self.config.get("model_display_name", "Kling 2.1 Professional")

        # Show prompt slots status
        saved_prompts = self.config.get("saved_prompts", {})
        slots_status = []
        for i in ["1", "2", "3"]:
            if saved_prompts.get(i):
                slots_status.append(f"\033[92m{i}\033[0m")
            else:
                slots_status.append(f"\033[90m{i}\033[0m")

        # Show current output mode status in menu
        output_mode_status = "\033[92mSource Folder\033[0m" if self.config.get('use_source_folder', True) else "\033[93mCustom\033[0m"
        print(f"  \033[93m1\033[0m   Change output mode (currently: {output_mode_status})")
        print(f"  \033[93m2\033[0m   Edit/view Kling prompt (full editor)")
        print(f"  \033[93m3\033[0m   Toggle verbose logging (currently: {verbose_status})")
        print(f"  \033[93m4\033[0m   Select Input Folder (GUI)")
        print(f"  \033[93m5\033[0m   Select Single Image (GUI)")
        print(f"  \033[93m6\033[0m   Launch GUI (Drag & Drop mode)")
        print(f"  \033[93m7\033[0m   Check Dependencies")
        print()
        print(f"  \033[96me\033[0m   Quick edit prompt")
        print(f"  \033[96mm\033[0m   Change model (\033[95m{model_name}\033[0m)")
        print(f"  \033[96mp\033[0m   Swap prompt slot (current: \033[95m{current_slot}\033[0m) [{'/'.join(slots_status)}]")
        print()
        print(f"  \033[91mq\033[0m   Quit")

        print()
        print("\033[92m➤ Enter path to your GenX images input folder (or select an option above):\033[0m ", end='', flush=True)

    def select_folder_gui(self):
        """Open GUI folder selection dialog"""
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        folder_path = filedialog.askdirectory(title="Select GenX Images Input Folder")
        root.destroy()
        return folder_path

    def select_file_gui(self):
        """Open GUI file selection dialog"""
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.askopenfilename(
            title="Select Single GenX Image",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp *.gif *.webp *.tiff *.tif"), ("All files", "*.*")]
        )
        root.destroy()
        return file_path

    def launch_gui(self):
        """Launch the Tkinter GUI mode for drag-and-drop processing."""
        try:
            from kling_gui.main_window import launch_gui as gui_launch
            print("\nLaunching GUI mode...")
            gui_launch(config_path=self.config_file)
        except ImportError as e:
            self.print_red(f"\nGUI module not found: {e}")
            self.print_yellow("Make sure kling_gui package is in the same directory.")
            input("Press Enter to continue...")
        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            self.print_red(f"\nError launching GUI: {e}")
            print("\nFull traceback:")
            print(tb_str)
            write_crash_log(type(e).__name__, str(e), tb_str)
            input("Press Enter to continue...")

    def check_dependencies(self):
        """Check and optionally install all required dependencies."""
        try:
            from dependency_checker import run_dependency_check
            print()
            run_dependency_check(auto_mode=False)
            print()
            input("Press Enter to continue...")
        except ImportError as e:
            self.print_red(f"\nDependency checker module not found: {e}")
            self.print_yellow("Make sure dependency_checker.py is in the same directory.")
            input("Press Enter to continue...")
        except Exception as e:
            self.print_red(f"\nError running dependency check: {e}")
            input("Press Enter to continue...")

    def toggle_verbose_logging(self):
        """Toggle verbose logging on/off"""
        self.verbose_logging = not self.verbose_logging
        self.config["verbose_logging"] = self.verbose_logging
        self.save_config()
        self.setup_logging()
        
        status = "enabled" if self.verbose_logging else "disabled"
        print(f"\nVerbose logging {status}")
        time.sleep(1)
    
    
    def change_output_mode(self):
        """Change output mode between source folder and custom folder"""
        print()
        use_source = self.config.get('use_source_folder', True)

        print("\033[96m" + "─" * 60 + "\033[0m")
        print("\033[95m OUTPUT MODE SETTINGS\033[0m")
        print("\033[96m" + "─" * 60 + "\033[0m")
        print()

        if use_source:
            print(f"  \033[92m✓ Current: SAME FOLDER AS SOURCE IMAGES\033[0m")
            print(f"     Videos are saved alongside each input image")
        else:
            print(f"  \033[93m✓ Current: CUSTOM FOLDER\033[0m")
            print(f"     All videos go to: {self.config['output_folder']}")
        print()

        print("\033[93mOptions:\033[0m")
        print(f"  \033[96m1\033[0m   Use source folder (save video next to input image)")
        print(f"  \033[96m2\033[0m   Use custom folder (all videos to one location)")
        print(f"  \033[91m0\033[0m   Cancel")
        print()

        choice = input("\033[92mSelect option: \033[0m").strip()

        if choice == '1':
            self.config['use_source_folder'] = True
            self.save_config()
            print("\n\033[92m✓ Output mode: SAME FOLDER AS SOURCE IMAGES\033[0m")
            print("  Videos will be saved alongside each input image")
            time.sleep(1.5)
        elif choice == '2':
            self.config['use_source_folder'] = False
            print(f"\n\033[93mCurrent custom folder:\033[0m {self.config['output_folder']}")
            new_path = input("\033[92mEnter new folder path (or Enter to keep current):\033[0m ").strip()

            if new_path and ((new_path.startswith('"') and new_path.endswith('"')) or
                            (new_path.startswith("'") and new_path.endswith("'"))):
                new_path = new_path[1:-1]

            if new_path:
                try:
                    Path(new_path).mkdir(parents=True, exist_ok=True)
                    self.config['output_folder'] = new_path
                    print(f"\033[92m✓ Custom folder set to: {new_path}\033[0m")
                except Exception as e:
                    self.print_red(f"Error creating folder: {e}")
                    time.sleep(1.5)
                    return

            self.save_config()
            print(f"\n\033[92m✓ Output mode: CUSTOM FOLDER\033[0m")
            print(f"  All videos will go to: {self.config['output_folder']}")
            time.sleep(1.5)
        else:
            print("\033[90mCancelled\033[0m")
            time.sleep(0.5)
    
    def edit_prompt(self):
        """Edit or view the Kling generation prompt (full editor with slot support)"""
        self.clear_screen()

        current_slot = str(self.config.get("current_prompt_slot", 1))
        current_prompt = self.get_current_prompt()
        default_prompt = self.get_default_prompt()

        print("\033[96m" + "═" * 79 + "\033[0m")
        self.print_magenta("                           KLING PROMPT EDITOR")
        print("\033[96m" + "═" * 79 + "\033[0m")
        print()

        # Show all slots
        print("\033[93mSaved Prompts:\033[0m")
        saved_prompts = self.config.get("saved_prompts", {})
        for i in ["1", "2", "3"]:
            prompt = saved_prompts.get(i)
            active = " \033[92m(ACTIVE)\033[0m" if i == current_slot else ""
            if prompt:
                preview = prompt[:50] + "..." if len(prompt) > 50 else prompt
                print(f"  [{i}] {preview}{active}")
            else:
                print(f"  [{i}] \033[90m(empty){active}\033[0m")
        print()

        # Show current prompt in full
        print("\033[93mCurrent Prompt (Slot {}):\033[0m".format(current_slot))
        print("\033[97m" + "─" * 79 + "\033[0m")
        words = current_prompt.split()
        line = ""
        for word in words:
            if len(line) + len(word) + 1 <= 75:
                line += word + " "
            else:
                print(f"  {line}")
                line = word + " "
        if line:
            print(f"  {line}")
        print("\033[97m" + "─" * 79 + "\033[0m")
        print()

        print("\033[92mOptions:\033[0m")
        print("  \033[93m1\033[0m - Reset to default prompt (head movement)")
        print("  \033[93m2\033[0m - Enter custom prompt for current slot")
        print("  \033[93m3\033[0m - Clear current slot (make empty)")
        print("  \033[93m4\033[0m - Return without changes")
        print()

        choice = input("\033[92mSelect option (1-4): \033[0m").strip()

        if choice == '1':
            self.config["saved_prompts"][current_slot] = default_prompt
            self.save_config()
            print("\n\033[92mReset to default head movement prompt\033[0m")
            time.sleep(1.5)
        elif choice == '2':
            print()
            print("\033[93mEnter your custom prompt (press Enter twice when done):\033[0m")
            print("\033[90m(Tip: You can paste multi-line text)\033[0m")
            print()

            lines = []
            empty_count = 0
            while True:
                try:
                    line = input()
                    if line:
                        lines.append(line)
                        empty_count = 0
                    else:
                        empty_count += 1
                        if empty_count >= 2:
                            break
                except EOFError:
                    break

            if lines:
                custom_prompt = " ".join(lines).strip()
                self.config["saved_prompts"][current_slot] = custom_prompt
                self.save_config()
                print("\n\033[92mCustom prompt saved to Slot {}!\033[0m".format(current_slot))
                time.sleep(1.5)
            else:
                print("\n\033[91mNo prompt entered, keeping current\033[0m")
                time.sleep(1.5)
        elif choice == '3':
            self.config["saved_prompts"][current_slot] = None
            self.save_config()
            print("\n\033[93mSlot {} cleared\033[0m".format(current_slot))
            time.sleep(1.5)

    def quick_edit_prompt(self):
        """Quick inline prompt editor - single line input"""
        print()
        print("\033[93mQuick Edit - Enter new prompt (single line, or press Enter to cancel):\033[0m")
        new_prompt = input("\033[92m➤ \033[0m").strip()

        if new_prompt:
            current_slot = str(self.config.get("current_prompt_slot", 1))
            self.config["saved_prompts"][current_slot] = new_prompt
            self.save_config()
            print("\033[92m✓ Prompt saved to Slot {}\033[0m".format(current_slot))
            time.sleep(1)
        else:
            print("\033[90mCancelled\033[0m")
            time.sleep(0.5)

    def swap_prompt_slot(self):
        """Swap between prompt slots 1, 2, 3"""
        print()
        saved_prompts = self.config.get("saved_prompts", {})
        current_slot = self.config.get("current_prompt_slot", 1)

        print("\033[93mSaved Prompts:\033[0m")
        for i in ["1", "2", "3"]:
            prompt = saved_prompts.get(i)
            active = " \033[92m◄ ACTIVE\033[0m" if str(i) == str(current_slot) else ""
            if prompt:
                preview = prompt[:60] + "..." if len(prompt) > 60 else prompt
                print(f"  [\033[96m{i}\033[0m] {preview}{active}")
            else:
                print(f"  [\033[90m{i}\033[0m] \033[90m(empty)\033[0m{active}")
        print()

        choice = input("\033[92mSelect slot (1-3) or Enter to cancel: \033[0m").strip()
        if choice in ["1", "2", "3"]:
            self.config["current_prompt_slot"] = int(choice)
            self.save_config()
            prompt = saved_prompts.get(choice)
            if prompt:
                print(f"\033[92m✓ Switched to Slot {choice}\033[0m")
            else:
                print(f"\033[93m⚠ Switched to Slot {choice} (empty - will use default)\033[0m")
            time.sleep(1)
        else:
            print("\033[90mCancelled\033[0m")
            time.sleep(0.5)

    def select_model(self):
        """Select AI model from presets or enter custom endpoint"""
        self.clear_screen()

        print("\033[96m" + "═" * 79 + "\033[0m")
        self.print_magenta("                           MODEL SELECTION")
        print("\033[96m" + "═" * 79 + "\033[0m")
        print()

        current_model = self.config.get("current_model", "")
        current_name = self.config.get("model_display_name", "Unknown")
        print(f"\033[95mCurrent model:\033[0m {current_name}")
        print(f"\033[90m  Endpoint: {current_model}\033[0m")
        print()

        # Preset models
        presets = [
            ("Kling 2.1 Professional", "fal-ai/kling-video/v2.1/pro/image-to-video", 10),
            ("Kling 2.5 Turbo Pro", "fal-ai/kling-video/v2.5-turbo/pro/image-to-video", 10),
            ("Wan 2.5", "fal-ai/wan-25-preview/image-to-video", 5),
            ("Veo 3", "fal-ai/veo3/image-to-video", 8),
            ("Ovi", "fal-ai/ovi/image-to-video", 5),
        ]

        print("\033[93mPreset Models:\033[0m")
        for idx, (name, endpoint, duration) in enumerate(presets, 1):
            # Fetch pricing
            price = self.fetch_model_pricing(endpoint)
            price_str = f"${price:.2f}/sec" if price else "check fal.ai"
            active = " \033[92m◄\033[0m" if endpoint == current_model else ""
            print(f"  \033[96m{idx}\033[0m   {name} ({price_str}){active}")

        print()
        print(f"  \033[93m6\033[0m   Enter custom endpoint")
        print(f"  \033[93m7\033[0m   Fetch all models from fal.ai")
        print(f"  \033[91m0\033[0m   Cancel")
        print()
        print(f"  \033[90mSee all: https://fal.ai/models?category=video\033[0m")
        print()

        choice = input("\033[92mSelect option: \033[0m").strip()

        if choice == '0':
            return
        elif choice == '6':
            # Custom endpoint
            print()
            print("\033[93mEnter fal.ai endpoint ID (e.g., fal-ai/kling-video/v2.1/pro/image-to-video):\033[0m")
            endpoint = input("\033[92m➤ \033[0m").strip()
            if endpoint:
                name = input("\033[92mDisplay name for this model: \033[0m").strip() or endpoint
                duration = input("\033[92mVideo duration in seconds (default 10): \033[0m").strip()
                duration = int(duration) if duration.isdigit() else 10

                self.config["current_model"] = endpoint
                self.config["model_display_name"] = name
                self.config["video_duration"] = duration
                self._cached_price = None  # Clear cache
                self.save_config()
                print(f"\033[92m✓ Model set to: {name}\033[0m")
                time.sleep(1.5)
        elif choice == '7':
            # Show all available models with pagination
            print("\n\033[93mFetching all image-to-video models from fal.ai...\033[0m")
            models = self.fetch_available_models()
            current_model = self.config.get("current_model", "")
            page_size = 40  # Show up to 40 per page
            page = 0
            total_pages = (len(models) + page_size - 1) // page_size

            print(f"\033[92mFound {len(models)} models total\033[0m")

            while True:
                start_idx = page * page_size
                end_idx = min(start_idx + page_size, len(models))
                page_models = models[start_idx:end_idx]

                print(f"\n\033[92m{'═' * 60}\033[0m")
                print(f"\033[92m  Image-to-Video Models  ·  Page {page+1}/{total_pages}  ·  Showing {start_idx+1}-{end_idx} of {len(models)}\033[0m")
                print(f"\033[92m{'═' * 60}\033[0m\n")
                for idx, m in enumerate(page_models, start_idx + 1):
                    endpoint = m.get("endpoint_id", "")
                    name = m.get("name", endpoint)
                    duration = m.get("duration", 10)
                    description = m.get("description", "")
                    price_info = m.get("price")
                    if price_info:
                        price_str = f"${price_info['price']:.3f}/{price_info['unit']}"
                    else:
                        price_str = "pricing unavailable"
                    active = "  \033[92m◄ CURRENT\033[0m" if endpoint == current_model else ""

                    print(f"  \033[96m{idx:2d}\033[0m  \033[1;97m{name}\033[0m{active}")
                    print(f"       Price: \033[93m{price_str}\033[0m")
                    if description:
                        # Wrap description to ~65 chars per line, max 3 lines
                        words = description.split()
                        lines = []
                        current_line = ""
                        for word in words:
                            if len(current_line) + len(word) + 1 <= 65:
                                current_line += (" " if current_line else "") + word
                            else:
                                if current_line:
                                    lines.append(current_line)
                                current_line = word
                            if len(lines) >= 3:
                                break
                        if current_line and len(lines) < 3:
                            lines.append(current_line)
                        for line in lines[:3]:
                            print(f"       \033[90m{line}\033[0m")
                    print(f"       \033[36m{endpoint}\033[0m")
                    print()  # Blank line between entries

                print()
                nav_hint = []
                if page > 0:
                    nav_hint.append("p=prev")
                if page < total_pages - 1:
                    nav_hint.append("n=next")
                nav_str = f" ({', '.join(nav_hint)})" if nav_hint else ""

                sel = input(f"\033[92mEnter number to select{nav_str}, or Enter to cancel: \033[0m").strip().lower()

                if sel == 'n' and page < total_pages - 1:
                    page += 1
                    continue
                elif sel == 'p' and page > 0:
                    page -= 1
                    continue
                elif sel == '' or sel == 'q':
                    break
                elif sel.isdigit() and 1 <= int(sel) <= len(models):
                    selected = models[int(sel) - 1]
                    self.config["current_model"] = selected.get("endpoint_id")
                    self.config["model_display_name"] = selected.get("name", selected.get("endpoint_id"))
                    self.config["video_duration"] = selected.get("duration", 10)
                    self._cached_price = None
                    self.save_config()
                    print(f"\033[92m✓ Model set to: {selected.get('name')}\033[0m")
                    time.sleep(1.5)
                    break
                else:
                    print("\033[91mInvalid selection\033[0m")
                    time.sleep(1)
        elif choice.isdigit() and 1 <= int(choice) <= len(presets):
            name, endpoint, duration = presets[int(choice) - 1]
            self.config["current_model"] = endpoint
            self.config["model_display_name"] = name
            self.config["video_duration"] = duration
            self._cached_price = None  # Clear price cache
            self.save_config()
            print(f"\033[92m✓ Model set to: {name}\033[0m")
            time.sleep(1.5)
    
    def run_configuration_menu(self):
        """Main configuration menu loop"""
        while True:
            self.display_header()
            self.display_configuration_menu()
            
            # Use empty input prompt so text appears right after the green prompt
            choice = input().strip()
            
            if choice.startswith('"') and choice.endswith('"'):
                choice = choice[1:-1]
            elif choice.startswith("'") and choice.endswith("'"):
                choice = choice[1:-1]
            
            choice_lower = choice.lower()
            
            if choice_lower == 'q':
                print("\nGoodbye!")
                sys.exit(0)
            elif choice_lower == '1':
                self.change_output_mode()
                continue
            elif choice_lower == '2':
                self.edit_prompt()
                continue
            elif choice_lower == '3':
                self.toggle_verbose_logging()
                continue
            elif choice_lower == '4':
                selected_path = self.select_folder_gui()
                if selected_path:
                    return selected_path
                continue
            elif choice_lower == '5':
                selected_path = self.select_file_gui()
                if selected_path:
                    return selected_path
                continue
            elif choice_lower == '6':
                self.launch_gui()
                continue
            elif choice_lower == '7':
                self.check_dependencies()
                continue
            elif choice_lower == 'e':
                self.quick_edit_prompt()
                continue
            elif choice_lower == 'm':
                self.select_model()
                continue
            elif choice_lower == 'p':
                self.swap_prompt_slot()
                continue
            elif choice and Path(choice).exists():
                return choice
            elif choice:
                self.print_red(f"Path not found: {choice}")
                input("Press Enter to continue...")
            else:
                self.print_yellow("Please enter a valid path or select an option")
                time.sleep(1)
    
    def count_genx_files(self, root_directory: str) -> int:
        """Count total genx files to process"""
        count = 0
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff', '.tif'}
        
        try:
            for folder_path in Path(root_directory).iterdir():
                if folder_path.is_dir():
                    for file_path in folder_path.iterdir():
                        if (file_path.is_file() and 
                            file_path.suffix.lower() in image_extensions and
                            'genx' in file_path.name.lower()):
                            count += 1
        except Exception:
            pass
        return count
    
    def get_all_folders(self, root_directory: str):
        """Get all folders that contain genx images"""
        folders = []
        try:
            if self.get_genx_files_in_folder(root_directory):
                folders.append(root_directory)
            
            for folder_path in Path(root_directory).iterdir():
                if folder_path.is_dir():
                    if self.get_genx_files_in_folder(str(folder_path)):
                        folders.append(str(folder_path))
        except Exception:
            pass
        return folders
    
    def get_genx_files_in_folder(self, folder_path: str):
        """Get genx files in a specific folder"""
        genx_files = []
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff', '.tif'}
        
        try:
            for file_path in Path(folder_path).iterdir():
                if (file_path.is_file() and 
                    file_path.suffix.lower() in image_extensions and
                    'genx' in file_path.name.lower()):
                    genx_files.append(str(file_path))
        except Exception:
            pass
        return genx_files
    
    def start_processing(self, input_folder: str):
        """Start the video generation process with Rich UI"""
        from rich.console import Console
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn, TimeElapsedColumn
        from rich.panel import Panel
        from rich.text import Text
        from rich.table import Table
        from rich.align import Align
        from rich.spinner import Spinner
        from rich.live import Live
        from rich.console import Group
        
        console = Console(force_terminal=True, width=120)
        self.clear_screen()
        
        # Header panel - show configured model
        model_name = self.config.get("model_display_name", "Kling 2.1 Professional")
        header_text = Text()
        header_text.append(f"🚀 {model_name.upper()} BATCH VIDEO GENERATOR 🚀", style="bold cyan")
        
        header_panel = Panel(
            Align.center(header_text),
            style="bright_blue",
            padding=(0, 1)
        )
        
        console.print(header_panel)
        
        # Create loading spinner
        def create_loading_spinner(message):
            return Spinner("dots", text=message, style="green bold")
        
        with Live(create_loading_spinner("Analyzing input..."), 
                  console=console, refresh_per_second=10) as loading_live:
            
            # Use fal.ai API with configurable model
            generator = FalAIKlingGenerator(
                api_key=self.config['falai_api_key'],
                verbose=self.verbose_logging,
                model_endpoint=self.config.get('current_model'),
                model_display_name=self.config.get('model_display_name')
            )
            
            # Get use_source_folder setting early for consistent use throughout
            use_source = self.config.get('use_source_folder', True)

            input_path = Path(input_folder)
            if input_path.is_file():
                genx_count = 1
                folders = [input_folder] # Treat file as single item list for processing logic
                total_files = 1
                loading_live.update(create_loading_spinner(f"Prepared single file: {input_path.name}"))
            else:
                loading_live.update(create_loading_spinner("Analyzing folders and checking for duplicates..."))
                genx_count = self.count_genx_files(input_folder)
                folders = self.get_all_folders(input_folder)

                loading_live.update(create_loading_spinner("Filtering out duplicates..."))

                total_files = 0
                for folder in folders:
                    genx_images = generator.get_genx_image_files(folder, use_source, self.config['output_folder'])
                    total_files += len(genx_images)
        
        # Clear screen
        console.clear()
        os.system('cls' if os.name == 'nt' else 'clear')
        time.sleep(0.1)
        
        console.print(header_panel)
        
        # Balance tracking removed - use fal.ai dashboard instead
        # Dashboard link shown in header
        
        try:
            if not self.verbose_logging:
                # Configuration panel
                config_table = Table.grid(padding=0)
                config_table.add_column(style="cyan", justify="left", width=18)  # Increased width for longer labels
                config_table.add_column(style="white", justify="left")
                
                if Path(input_folder).is_file():
                     config_table.add_row("Input:", f"Single File: {Path(input_folder).name}")
                else:
                     config_table.add_row("Files Amt:", f"{total_files} GenX files")
                
                model_name = self.config.get("model_display_name", "Kling 2.1 Professional")
                duration = self.config.get("video_duration", 10)
                price = self.fetch_model_pricing(self.config.get("current_model", ""))
                price_str = f"${price:.2f}/sec" if price else "Check fal.ai"

                config_table.add_row("Provider:", "fal.ai API")
                config_table.add_row("Model:", model_name)
                config_table.add_row("Duration:", f"{duration} seconds")
                config_table.add_row("Cost:", price_str)
                # Show output mode
                use_source = self.config.get('use_source_folder', True)
                if use_source:
                    config_table.add_row("Output:", "📂 Same folder as source images")
                else:
                    config_table.add_row("Output folder:", self.config['output_folder'])
                config_table.add_row("Verbose mode:", "Hidden")
                
                config_panel = Panel(
                    config_table,
                    title="Configuration",
                    border_style="green",
                    title_align="left",
                    padding=(0, 1)
                )
                console.print(config_panel)
                print()  # Blank line after panel
                
                # Progress bar
                with Progress(
                    SpinnerColumn(style="bright_cyan"),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(bar_width=None),
                    MofNCompleteColumn(), 
                    TextColumn("•"),
                    TimeElapsedColumn(),
                    console=console
                ) as progress:
                    
                    if Path(input_folder).is_file():
                         main_task = progress.add_task("📊 [cyan]0% complete[/cyan] • 🎬 Processing Single File... 🚀", total=total_files)
                    else:
                         main_task = progress.add_task("📊 [cyan]0% complete[/cyan] • 🎬 Processing GenX files... 🚀", total=total_files)
                    
                    active_generations = []  # Track currently processing files
                    recent_status = ""
                    processed = 0
                    videos_completed = 0  # Track successful completions for cost
                    all_files = []  # Track ALL files for "Next" display
                    
                    # Collect all files upfront for Next display
                    if Path(input_folder).is_file():
                        all_files.append(Path(input_folder).stem)
                    else:
                        for folder in folders:
                            genx_images = generator.get_genx_image_files(folder, use_source, self.config['output_folder'])
                            for img in genx_images:
                                folder_name = Path(folder).name
                                all_files.append(folder_name)
                    
                    def create_colorful_spinners():
                        activity_text = Text()
                        activity_text.append("🔥 Activity: ", style="bright_green bold")
                        
                        if active_generations:
                            # Show only 2 names to avoid overflow
                            activity_text.append(f"{len(active_generations)} concurrent • ", style="bright_cyan")
                            display_names = [Path(f).stem[:15] for f in active_generations[:2]]  # Only 2 names, shorter
                            activity_text.append(", ".join(display_names), style="white")
                            if len(active_generations) > 2:
                                activity_text.append(f" (+{len(active_generations)-2} more)", style="bright_yellow")
                        elif recent_status:
                            if "Completed:" in recent_status:
                                filename = recent_status.replace("Completed: ", "")
                                activity_text.append("✅ Completed: ", style="bright_green")
                                activity_text.append(filename[:30], style="white")  # Limit length
                            elif "Failed:" in recent_status:
                                filename = recent_status.replace("Failed: ", "")
                                activity_text.append("❌ Failed: ", style="bright_red")
                                activity_text.append(filename[:30], style="white")  # Limit length
                            else:
                                activity_text.append(recent_status, style="bright_cyan")
                        else:
                            activity_text.append("Initializing...", style="bright_cyan")
                        activity_spinner = Spinner("dots", text=activity_text, style="bright_green")
                        
                        # Action spinner (balance tracking removed - check fal.ai dashboard)
                        action_text = Text()
                        action_text.append("⚡ Action: ", style="bright_blue bold")
                        action_text.append("💰 Balance: fal.ai/dashboard • ", style="bright_yellow")
                        action_text.append("Monitoring for Interrupts...", style="bright_white")
                        action_spinner = Spinner("dots", text=action_text, style="bright_blue")
                        
                        next_text = Text()
                        next_text.append("🔮 Next: ", style="bright_magenta bold")
                        
                        # Calculate remaining (not yet started)
                        total_in_progress = processed + len(active_generations)
                        remaining_to_start = len(all_files) - total_in_progress
                        
                        # Show next folder names (not yet processed or in progress)
                        if remaining_to_start > 0:
                            upcoming = all_files[total_in_progress:total_in_progress+3]  # Next 3 folders
                            
                            # Get unique folder names
                            unique_folders = []
                            seen = set()
                            for folder_name in upcoming:
                                if folder_name not in seen:
                                    unique_folders.append(folder_name)
                                    seen.add(folder_name)
                            
                            if unique_folders:
                                display = ", ".join(unique_folders[:3])
                                if remaining_to_start > 3:
                                    display += f" (+{remaining_to_start-3} more)"
                                next_text.append(display, style="bright_yellow")
                            else:
                                next_text.append(f"{remaining_to_start} videos remaining in queue", style="bright_yellow")
                        else:
                            next_text.append("All generations complete", style="bright_green")
                        next_spinner = Spinner("dots", text=next_text, style="bright_magenta")
                        
                        return Group(activity_spinner, action_spinner, next_spinner)
                    
                    with Live(create_colorful_spinners(), console=console, refresh_per_second=10) as live:
                        def update_progress(completed, total, new_status):
                            nonlocal recent_status, processed, active_generations
                            recent_status = new_status
                            processed = completed
                            
                            # Update active generations list
                            if "Generating:" in new_status:
                                filename = new_status.replace("Generating: ", "")
                                if filename not in active_generations:
                                    active_generations.append(filename)
                            elif "Completed:" in new_status or "Failed:" in new_status:
                                filename = new_status.replace("Completed: ", "").replace("Failed: ", "")
                                if filename in active_generations:
                                    active_generations.remove(filename)
                            
                            current_pct = int((completed / total) * 100) if total > 0 else 0
                            progress.update(main_task, 
                                completed=completed,
                                description=f"📊 [cyan]{current_pct}% complete[/cyan] • 🚀")
                            live.update(create_colorful_spinners())
                        
                        # Use concurrent processing with 5 workers (Kling API max)
                        use_source = self.config.get('use_source_folder', True)
                        generator.process_all_images_concurrent(
                            target_directory=input_folder,
                            output_directory=self.config['output_folder'],
                            max_workers=5,
                            custom_prompt=self.get_current_prompt(),
                            progress_callback=update_progress,
                            use_source_folder=use_source
                        )
                        
                        if total_files > 0:
                            progress.update(main_task, completed=total_files, 
                                description="📊 [cyan]100% complete[/cyan] • 🎉 All files processed!")
                            recent_status = "Processing complete!"
                            active_generations.clear()
                            live.update(create_colorful_spinners())
                        
                        time.sleep(2)
                        
            else:
                # Verbose processing with concurrent execution
                print("Processing started with verbose logging...")
                print("Using 5 concurrent workers for faster processing...")
                use_source = self.config.get('use_source_folder', True)
                if use_source:
                    print("Output mode: Videos saved alongside source images")
                else:
                    print(f"Output folder: {self.config['output_folder']}")
                print("All detailed logs will be displayed below:")
                print()

                generator.process_all_images_concurrent(
                    target_directory=input_folder,
                    output_directory=self.config['output_folder'],
                    max_workers=5,
                    custom_prompt=self.get_current_prompt(),
                    use_source_folder=use_source
                )
                    
        except Exception as e:
            print(f"\nError during processing: {e}")
            if self.verbose_logging:
                import traceback
                print(f"{traceback.format_exc()}")
        
        print("\nProcessing complete!")
        use_source = self.config.get('use_source_folder', True)
        if use_source:
            print("Videos saved alongside source images in their respective folders")
        else:
            print(f"Check your videos in: {self.config['output_folder']}")
        input("\nPress Enter to return to main menu...")
    
    def run(self):
        """Main application loop"""
        while True:
            input_folder = self.run_configuration_menu()
            self.start_processing(input_folder)


def write_crash_log(error_type: str, error_msg: str, traceback_str: str):
    """Write crash information to a log file for debugging."""
    from datetime import datetime
    crash_log_path = get_crash_log_path()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    crash_info = f"""
{'='*60}
CRASH REPORT - {timestamp}
{'='*60}
Error Type: {error_type}
Error Message: {error_msg}

Full Traceback:
{traceback_str}
{'='*60}

"""
    try:
        # Append to crash log (keep history)
        with open(crash_log_path, 'a', encoding='utf-8') as f:
            f.write(crash_info)
        print(f"\n[Crash log saved to: {crash_log_path}]")
    except Exception as log_error:
        print(f"[Could not write crash log: {log_error}]")


def main():
    """Entry point"""
    try:
        os.system('color')

        import sys
        if sys.platform == 'win32':
            try:
                import codecs
                sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
                sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
            except:
                pass

        app = KlingAutomationUI()
        app.run()
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
        sys.exit(0)
    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()

        # Print full error to console
        print("\n" + "="*60)
        print("  FATAL ERROR - Application Crashed")
        print("="*60)
        print(f"\nError: {type(e).__name__}: {e}")
        print("\nFull traceback:")
        print(tb_str)
        print("="*60)

        # Write to crash log file
        write_crash_log(type(e).__name__, str(e), tb_str)

        sys.exit(1)


if __name__ == "__main__":
    main()
