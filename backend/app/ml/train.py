"""Train the optional classifier on deterministic synthetic profiles."""

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.ml.inference import default_artifact_path, train_model


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=2000, help="Even synthetic sample count (minimum 100)")
    parser.add_argument("--seed", type=int, default=2026, help="Deterministic data and split seed")
    parser.add_argument("--output", type=Path, default=default_artifact_path(), help="Local model artifact path")
    arguments = parser.parse_args(argv)
    metadata = train_model(arguments.output, samples=arguments.samples, seed=arguments.seed)
    print(json.dumps({"artifact": str(arguments.output.resolve()), **metadata}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())