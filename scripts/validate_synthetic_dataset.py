"""CLI for validating generated synthetic manga/game data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthetic_data.validation import validate_output_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate generated synthetic dataset exports.")
    parser.add_argument("output", type=Path, nargs="?", default=Path("data/generated/synthetic_poc"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = validate_output_dir(args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["error_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
