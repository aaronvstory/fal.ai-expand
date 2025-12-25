"""
Test configuration for pytest
Adds parent directory to sys.path for module imports
"""
import sys
import os

# Add parent directory to path for importing project modules
sys.path.insert(0, os.path.dirname(__file__) + '/..')
