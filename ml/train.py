"""Train the optional classifier on deterministic synthetic profiles."""

import sys
from pathlib import Path

BACKEND_PATH = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.ml.train import main


if __name__ == "__main__":
    raise SystemExit(main())
