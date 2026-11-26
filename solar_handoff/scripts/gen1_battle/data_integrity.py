"""Default data location, relative to this portable bundle."""
from pathlib import Path
DATA = Path(__file__).resolve().parents[2] / "data" / "processed"
