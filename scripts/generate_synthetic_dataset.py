"""CLI for generating synthetic manga/game data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthetic_data.generator import generate_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic manga/game OCR/VLM data.")
    parser.add_argument("--output", type=Path, default=Path("data/generated/synthetic_poc"))
    parser.add_argument("--count", type=int, default=20, help="Number of images to generate.")
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--clean", action="store_true", help="Delete the output directory before generation.")
    parser.add_argument("--no-augment", action="store_true", help="Disable image augmentation.")
    parser.add_argument("--use-llm", action="store_true", help="Backward-compatible shortcut for API content generation.")
    parser.add_argument("--llm-model", default=None, help="Backward-compatible model override.")
    parser.add_argument(
        "--content-provider",
        choices=("fallback", "openai", "gemini", "groq"),
        default="fallback",
        help="Source for text content. API providers require their *_API_KEY env var.",
    )
    parser.add_argument(
        "--content-model",
        default=None,
        help="Model for API content providers, e.g. gemini-2.0-flash or llama-3.1-8b-instant.",
    )
    parser.add_argument("--api-timeout", type=int, default=45, help="API timeout in seconds.")
    parser.add_argument(
        "--game-renderer",
        choices=("auto", "playwright", "pillow"),
        default="auto",
        help="Use Playwright for game UI when available; auto falls back to Pillow.",
    )
    parser.add_argument("--blocks-per-sample", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = generate_dataset(
        output_dir=args.output,
        count=args.count,
        seed=args.seed,
        clean=args.clean,
        augment=not args.no_augment,
        use_llm=args.use_llm,
        llm_model=args.llm_model,
        content_provider=args.content_provider,
        content_model=args.content_model,
        api_timeout=args.api_timeout,
        game_renderer=args.game_renderer,
        blocks_per_sample=args.blocks_per_sample,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
