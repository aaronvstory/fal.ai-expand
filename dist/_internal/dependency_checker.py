"""
Dependency Checker - Verify and install all required dependencies for Kling UI.

Checks:
- Python packages (pip)
- External tools (FFmpeg)
- Optional enhancements (tkinterdnd2 for drag-drop)
"""

import subprocess
import sys
import shutil
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class Dependency:
    """Represents a dependency with its status."""
    name: str
    import_name: str  # The actual import name (may differ from package name)
    pip_name: str     # The pip install name
    required: bool    # True = required, False = optional
    description: str
    installed: bool = False
    version: Optional[str] = None


# Define all dependencies
PYTHON_DEPENDENCIES = [
    Dependency(
        name="Requests",
        import_name="requests",
        pip_name="requests",
        required=True,
        description="HTTP library for API calls to fal.ai"
    ),
    Dependency(
        name="Pillow (PIL)",
        import_name="PIL",
        pip_name="Pillow",
        required=True,
        description="Image processing library"
    ),
    Dependency(
        name="TkinterDnD2",
        import_name="tkinterdnd2",
        pip_name="tkinterdnd2",
        required=False,
        description="Drag-and-drop support for GUI mode"
    ),
    Dependency(
        name="Selenium",
        import_name="selenium",
        pip_name="selenium",
        required=False,
        description="Browser automation (for balance checker)"
    ),
    Dependency(
        name="Webdriver Manager",
        import_name="webdriver_manager",
        pip_name="webdriver-manager",
        required=False,
        description="Automatic ChromeDriver management"
    ),
]


@dataclass
class ExternalTool:
    """Represents an external tool dependency."""
    name: str
    command: str
    args: List[str]
    required: bool
    description: str
    install_hint: str
    installed: bool = False
    version: Optional[str] = None


EXTERNAL_TOOLS = [
    ExternalTool(
        name="FFmpeg",
        command="ffmpeg",
        args=["-version"],
        required=False,
        description="Video processing for Loop Video feature",
        install_hint="Download from https://ffmpeg.org/download.html or install via: winget install FFmpeg"
    ),
]


class DependencyChecker:
    """Check and install dependencies for Kling UI."""

    # ANSI color codes
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"
    RESET = "\033[0m"

    def __init__(self):
        self.python_deps = [Dependency(**d.__dict__) for d in PYTHON_DEPENDENCIES]
        self.external_tools = [ExternalTool(**t.__dict__) for t in EXTERNAL_TOOLS]

    def print_header(self, text: str):
        """Print a header line."""
        print(f"\n{self.MAGENTA}{'═' * 79}{self.RESET}")
        print(f"{self.MAGENTA}  {text}{self.RESET}")
        print(f"{self.MAGENTA}{'═' * 79}{self.RESET}\n")

    def print_section(self, text: str):
        """Print a section header."""
        print(f"\n{self.CYAN}{'─' * 79}{self.RESET}")
        print(f"{self.CYAN}  {text}{self.RESET}")
        print(f"{self.CYAN}{'─' * 79}{self.RESET}\n")

    def check_python_package(self, dep: Dependency) -> bool:
        """Check if a Python package is installed."""
        try:
            module = __import__(dep.import_name)
            dep.installed = True
            # Try to get version
            try:
                dep.version = getattr(module, '__version__', None)
                if dep.version is None:
                    import importlib.metadata
                    dep.version = importlib.metadata.version(dep.pip_name)
            except Exception:
                dep.version = "unknown"
            return True
        except ImportError:
            dep.installed = False
            return False

    def check_external_tool(self, tool: ExternalTool) -> bool:
        """Check if an external tool is available."""
        try:
            result = subprocess.run(
                [tool.command] + tool.args,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                tool.installed = True
                # Extract version from first line
                first_line = result.stdout.split('\n')[0] if result.stdout else ""
                tool.version = first_line[:60] if first_line else "installed"
                return True
        except FileNotFoundError:
            tool.installed = False
        except subprocess.TimeoutExpired:
            tool.installed = False
        except Exception:
            tool.installed = False
        return False

    def check_all(self) -> Tuple[int, int, int, int]:
        """
        Check all dependencies.

        Returns:
            (required_ok, required_missing, optional_ok, optional_missing)
        """
        required_ok = 0
        required_missing = 0
        optional_ok = 0
        optional_missing = 0

        # Check Python packages
        for dep in self.python_deps:
            installed = self.check_python_package(dep)
            if dep.required:
                if installed:
                    required_ok += 1
                else:
                    required_missing += 1
            else:
                if installed:
                    optional_ok += 1
                else:
                    optional_missing += 1

        # Check external tools
        for tool in self.external_tools:
            installed = self.check_external_tool(tool)
            if tool.required:
                if installed:
                    required_ok += 1
                else:
                    required_missing += 1
            else:
                if installed:
                    optional_ok += 1
                else:
                    optional_missing += 1

        return required_ok, required_missing, optional_ok, optional_missing

    def display_status(self):
        """Display the status of all dependencies."""
        self.print_header("DEPENDENCY CHECK")

        # Python packages
        self.print_section("Python Packages")

        for dep in self.python_deps:
            req_label = f"{self.RED}[REQUIRED]{self.RESET}" if dep.required else f"{self.GRAY}[optional]{self.RESET}"

            if dep.installed:
                version_str = f" v{dep.version}" if dep.version and dep.version != "unknown" else ""
                print(f"  {self.GREEN}✓{self.RESET} {dep.name}{version_str} {req_label}")
                print(f"    {self.GRAY}{dep.description}{self.RESET}")
            else:
                print(f"  {self.RED}✗{self.RESET} {dep.name} {req_label}")
                print(f"    {self.GRAY}{dep.description}{self.RESET}")
                print(f"    {self.YELLOW}Install: pip install {dep.pip_name}{self.RESET}")
            print()

        # External tools
        self.print_section("External Tools")

        for tool in self.external_tools:
            req_label = f"{self.RED}[REQUIRED]{self.RESET}" if tool.required else f"{self.GRAY}[optional]{self.RESET}"

            if tool.installed:
                print(f"  {self.GREEN}✓{self.RESET} {tool.name} {req_label}")
                print(f"    {self.GRAY}{tool.description}{self.RESET}")
                if tool.version:
                    print(f"    {self.GRAY}Version: {tool.version}{self.RESET}")
            else:
                print(f"  {self.RED}✗{self.RESET} {tool.name} {req_label}")
                print(f"    {self.GRAY}{tool.description}{self.RESET}")
                print(f"    {self.YELLOW}{tool.install_hint}{self.RESET}")
            print()

    def display_summary(self, required_ok: int, required_missing: int,
                       optional_ok: int, optional_missing: int):
        """Display summary of dependency check."""
        self.print_section("SUMMARY")

        total_required = required_ok + required_missing
        total_optional = optional_ok + optional_missing

        # Required dependencies
        if required_missing == 0:
            print(f"  {self.GREEN}✓ All required dependencies installed ({required_ok}/{total_required}){self.RESET}")
        else:
            print(f"  {self.RED}✗ Missing required dependencies: {required_missing}/{total_required}{self.RESET}")

        # Optional dependencies
        if optional_missing == 0:
            print(f"  {self.GREEN}✓ All optional dependencies installed ({optional_ok}/{total_optional}){self.RESET}")
        else:
            print(f"  {self.YELLOW}⚠ Missing optional dependencies: {optional_missing}/{total_optional}{self.RESET}")

        print()

        return required_missing == 0

    def get_missing_pip_packages(self) -> List[Dependency]:
        """Get list of missing pip packages."""
        return [dep for dep in self.python_deps if not dep.installed]

    def install_pip_package(self, dep: Dependency) -> bool:
        """Install a single pip package."""
        try:
            print(f"  {self.CYAN}Installing {dep.name}...{self.RESET}")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", dep.pip_name],
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode == 0:
                print(f"  {self.GREEN}✓ {dep.name} installed successfully{self.RESET}")
                return True
            else:
                print(f"  {self.RED}✗ Failed to install {dep.name}{self.RESET}")
                if result.stderr:
                    print(f"    {self.GRAY}{result.stderr[-200:]}{self.RESET}")
                return False
        except subprocess.TimeoutExpired:
            print(f"  {self.RED}✗ Installation timed out for {dep.name}{self.RESET}")
            return False
        except Exception as e:
            print(f"  {self.RED}✗ Error installing {dep.name}: {e}{self.RESET}")
            return False

    def install_all_missing(self, include_optional: bool = True) -> Tuple[int, int]:
        """
        Install all missing pip packages.

        Args:
            include_optional: Whether to install optional packages too

        Returns:
            (success_count, failure_count)
        """
        missing = self.get_missing_pip_packages()
        if not include_optional:
            missing = [dep for dep in missing if dep.required]

        if not missing:
            print(f"  {self.GREEN}No packages to install!{self.RESET}")
            return 0, 0

        self.print_section(f"Installing {len(missing)} package(s)")

        success = 0
        failed = 0

        for dep in missing:
            if self.install_pip_package(dep):
                success += 1
            else:
                failed += 1
            print()

        return success, failed


def run_dependency_check(auto_mode: bool = False) -> bool:
    """
    Run the full dependency check workflow.

    Args:
        auto_mode: If True, automatically install without prompting

    Returns:
        True if all required dependencies are satisfied
    """
    checker = DependencyChecker()

    # Initial check
    req_ok, req_missing, opt_ok, opt_missing = checker.check_all()

    # Display status
    checker.display_status()

    # Display summary
    all_required_ok = checker.display_summary(req_ok, req_missing, opt_ok, opt_missing)

    # If nothing missing, we're done
    missing_pip = checker.get_missing_pip_packages()
    if not missing_pip:
        print(f"{checker.GREEN}All Python packages are installed!{checker.RESET}")

        # Check for missing external tools
        missing_tools = [t for t in checker.external_tools if not t.installed]
        if missing_tools:
            print(f"\n{checker.YELLOW}Note: Some external tools are not installed.{checker.RESET}")
            print(f"{checker.GRAY}These must be installed manually (see instructions above).{checker.RESET}")

        return all_required_ok

    # Offer to install missing packages
    print(f"\n{checker.CYAN}{'─' * 79}{checker.RESET}")

    missing_required = [d for d in missing_pip if d.required]
    missing_optional = [d for d in missing_pip if not d.required]

    print(f"\n  Missing packages:")
    if missing_required:
        print(f"    {checker.RED}Required: {', '.join(d.pip_name for d in missing_required)}{checker.RESET}")
    if missing_optional:
        print(f"    {checker.YELLOW}Optional: {', '.join(d.pip_name for d in missing_optional)}{checker.RESET}")

    print()
    print(f"  {checker.WHITE}Options:{checker.RESET}")
    print(f"    {checker.CYAN}1{checker.RESET}  Install all missing packages (required + optional)")
    print(f"    {checker.CYAN}2{checker.RESET}  Install required packages only")
    print(f"    {checker.CYAN}3{checker.RESET}  Skip installation")
    print()

    if auto_mode:
        choice = "1"
        print(f"  {checker.GRAY}Auto-mode: Installing all packages...{checker.RESET}")
    else:
        choice = input(f"  {checker.GREEN}Enter choice (1/2/3): {checker.RESET}").strip()

    if choice == "1":
        success, failed = checker.install_all_missing(include_optional=True)
    elif choice == "2":
        success, failed = checker.install_all_missing(include_optional=False)
    else:
        print(f"\n  {checker.YELLOW}Installation skipped.{checker.RESET}")
        return all_required_ok

    # Re-run check to verify
    print(f"\n{checker.MAGENTA}{'═' * 79}{checker.RESET}")
    print(f"{checker.MAGENTA}  VERIFICATION - Re-checking dependencies...{checker.RESET}")
    print(f"{checker.MAGENTA}{'═' * 79}{checker.RESET}")

    # Reset and recheck
    checker = DependencyChecker()
    req_ok, req_missing, opt_ok, opt_missing = checker.check_all()
    checker.display_status()
    all_required_ok = checker.display_summary(req_ok, req_missing, opt_ok, opt_missing)

    if all_required_ok:
        print(f"\n{checker.GREEN}✓ All required dependencies are now installed!{checker.RESET}")
    else:
        print(f"\n{checker.RED}✗ Some required dependencies are still missing.{checker.RESET}")
        print(f"{checker.YELLOW}Please install them manually and try again.{checker.RESET}")

    return all_required_ok


# Allow running directly
if __name__ == "__main__":
    import sys
    auto = "--auto" in sys.argv
    success = run_dependency_check(auto_mode=auto)
    sys.exit(0 if success else 1)
