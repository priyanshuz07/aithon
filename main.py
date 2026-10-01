from pathlib import Path
import sys

backend_directory = str(Path(__file__).resolve().parent / "backend")
if backend_directory not in sys.path:
    sys.path.insert(0, backend_directory)

from app.main import app

__all__ = ["app"]