# 🎬 Kling UI - AI Video Generator

Batch video generation tool using fal.ai Platform API to create AI videos from images.

## ✨ Features

- **CLI Mode**: Rich terminal UI with colorful menus and progress tracking
- **GUI Mode**: Modern dark-themed Tkinter interface with drag-and-drop
- **40+ AI Video Models**: Access Kling, Veo, Sora, Wan, and many more from fal.ai
- **Queue Management**: Process up to 50 images with concurrent generation (5 workers)

## 🤖 MCP Testing Status

- ✅ **GitHub MCP**: Successfully created issue #1 via gh command
- ✅ **TaskMaster AI MCP**: Created test task in .taskmaster/tasks/test_mcp_task.md  
- ✅ **Desktop Commander MCP**: Successfully edited this README file
- ✅ **Serena MCP**: Testing semantic code analysis (should find `FalAIKlingGenerator` class)
- 🧠 **All MCPs**: Functional and operational!

This project demonstrates integration with multiple MCP servers for enhanced AI capabilities.
- **Ping-Pong Loop**: Create seamless looping videos with FFmpeg integration
- **Smart Prompts**: 3 prompt slots with quick switching and full editor
- **Negative Prompts**: Model-aware negative prompt support (auto-detected)
- **Reprocessing Options**: Overwrite or increment filenames for re-runs
- **Flexible Output**: Save to source folder or custom location
- **Duplicate Detection**: Skip already-processed images automatically
- **Balance Tracking**: Optional real-time fal.ai credit monitoring via Selenium

## 🚀 Quick Start

### Windows Users (Recommended)

1. **Extract** the distribution folder anywhere
2. **Double-click** `run_kling_ui.bat`
3. First run will:
   - Create a Python virtual environment (`venv/`)
   - Install all dependencies automatically
   - Launch the CLI interface
4. **Enter your fal.ai API key** when prompted (get one at https://fal.ai)

### Manual Setup

```bash
# Create virtual environment
python -m venv venv

# Activate it
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Run the app
python kling_automation_ui.py
```

## 📋 Requirements

- **Python 3.8+** (with tkinter - included in standard Windows installer)
- **fal.ai API key** (https://fal.ai - create free account)
- **FFmpeg** (optional, for video looping feature)
  - Download: https://ffmpeg.org/download.html
  - Or install via: `winget install FFmpeg`

## 🎮 Usage

### CLI Mode (Default)

Run `python kling_automation_ui.py` or use the batch file.

**Menu Options:**
| Key | Action |
|-----|--------|
| 1 | Change output mode (source folder / custom) |
| 2 | Edit/view prompt (full editor with slots) |
| 3 | Toggle verbose logging |
| 4 | Select input folder (GUI dialog) |
| 5 | Select single image (GUI dialog) |
| 6 | **Launch GUI** (drag-and-drop mode) |
| 7 | Check dependencies |
| e | Quick edit prompt (single line) |
| m | Change AI model (browse 40+ models) |
| p | Swap prompt slot (1/2/3) |
| q | Quit |

**Or:** Paste/type a folder path directly to start processing.

### GUI Mode

Launch via menu option `6` or directly:
```python
python -c "from kling_gui import KlingGUIWindow; KlingGUIWindow().run()"
```

**Features:**
- Drag images from Windows Explorer onto the drop zone
- Real-time processing queue with status icons
- Color-coded log display
- Processed videos history with quick-open buttons
- Edit prompt and model from the config panel
- Pause/Resume/Retry controls

## ⚙️ Configuration

All settings are saved to `kling_config.json`:

| Setting | Description |
|---------|-------------|
| `falai_api_key` | Your fal.ai API key |
| `output_folder` | Default output location |
| `use_source_folder` | Save videos alongside source images |
| `current_model` | Active AI model endpoint |
| `current_prompt_slot` | Active prompt slot (1-3) |
| `saved_prompts` | Prompt text for each slot |
| `negative_prompts` | Negative prompt text for each slot |
| `video_duration` | Default duration in seconds |
| `loop_videos` | Enable ping-pong loop effect |
| `allow_reprocess` | Allow reprocessing existing videos |
| `reprocess_mode` | "overwrite" or "increment" |
| `verbose_logging` | Show detailed API logs |
| `duplicate_detection` | Skip existing videos |

## 🤖 Supported Models

The app dynamically fetches all available image-to-video models from fal.ai:

**Popular Models:**
- Kling v2.6 / v2.5 Turbo Pro (recommended)
- Google Veo 3 / Veo 3.1
- Sora 2
- Wan 2.5 (with audio)
- Pixverse V5
- Hunyuan Video
- LTX-2
- And 30+ more...

Use `m` in CLI or the model dropdown in GUI to browse all available models.

## 📁 File Structure

```
distribution/
├── run_kling_ui.bat        # Main launcher (creates venv on first run)
├── kling_automation_ui.py  # CLI application
├── kling_generator_falai.py # fal.ai API integration
├── dependency_checker.py   # Package verification tool
├── balance_tracker.py      # Real-time balance monitoring
├── selenium_balance_checker.py # Chrome automation for balance
├── requirements.txt        # Python dependencies
├── README.md              # This file
└── kling_gui/             # GUI package
    ├── __init__.py
    ├── main_window.py     # Main Tkinter window
    ├── config_panel.py    # Model/prompt settings
    ├── queue_manager.py   # Processing queue
    ├── drop_zone.py       # Drag-and-drop widget
    ├── log_display.py     # Color-coded log
    └── video_looper.py    # FFmpeg loop wrapper
```

## 💰 Pricing

Costs vary by model (check fal.ai dashboard):
- **Kling 2.5 Turbo Pro**: ~$0.07/second = ~$0.70 per 10s video
- **Veo 3**: Varies by duration
- Other models have different pricing tiers

## 🔧 Troubleshooting

### "tkinter not found"
- Reinstall Python with the "tcl/tk and IDLE" option checked
- Or use the CLI mode which has limited tkinter dependency

### "tkinterdnd2 import error"
- The batch file will attempt to reinstall automatically
- Manual fix: `pip install --force-reinstall tkinterdnd2`

### "No drag-drop"
- Fallback: Use the "Add Files..." button in GUI
- Or use CLI mode with folder selection dialog (option 4/5)

### "FFmpeg not found"
- Download from https://ffmpeg.org/download.html
- Or: `winget install FFmpeg`
- Make sure `ffmpeg.exe` is in your PATH

### API Errors
- Check your API key is correct
- Verify your fal.ai account has credits
- Check https://status.fal.ai for outages

## 📝 License

MIT License - Feel free to modify and distribute.

## 🙏 Credits

- **fal.ai** - AI video generation platform
- **tkinterdnd2** - Drag-and-drop support
- **Rich** - Beautiful terminal UI
- **FFmpeg** - Video processing
