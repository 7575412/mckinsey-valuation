import os
import sys

# Ensure the project root (containing the `engine` package) is importable
# when running pytest from anywhere.
sys.path.insert(0, os.path.dirname(__file__))
