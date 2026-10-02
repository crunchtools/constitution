import sys
from pathlib import Path

# The scripts live at the repo root and are run by path, not installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
