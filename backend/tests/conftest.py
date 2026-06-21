import sys
from pathlib import Path

# Shared conftest for all tests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
