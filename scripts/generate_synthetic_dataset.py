"""CLI for generating synthetic manga/game data."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthetic_data.generator import generate_dataset


class ProgressBar:
    def __init__(self, total: int, stream: TextIO = sys.stderr) -> None:
        self.total = max(0, total)
        self.stream = stream
        self.started_at = time.monotonic()
        self.last_len = 0

    def update(self, event: Dict[str, Any]) -> None:
        phase = event.get("phase")
        if phase == "generate":
            self._draw_generate(event)
        elif phase == "validate":
            self._write_status("Validating outputs...")
        elif phase == "done":
            errors = event.get("validation_errors", 0)
            self._write_status(f"Done. Validation errors: {errors}")
            self.stream.write("\n")
            self.stream.flush()

    def _draw_generate(self, event: Dict[str, Any]) -> None:
        completed = int(event.get("completed", 0))
        total = max(1, int(event.get("total", self.total or 1)))
        elapsed = max(0.001, time.monotonic() - self.started_at)
        rate = completed / elapsed
        remaining = max(0, total - completed)
        eta = remaining / rate if rate > 0 else None
        percent = completed / total
        bar_width = 28
        filled = min(bar_width, int(round(bar_width * percent)))
        bar = "#" * filled + "-" * (bar_width - filled)
        sample_id = str(event.get("sample_id", ""))
        renderer = str(event.get("renderer", ""))
        status = (
            f"Generating [{bar}] {completed}/{total} "
            f"{percent * 100:5.1f}% | elapsed {format_duration(elapsed)} "
            f"| ETA {format_duration(eta)} | {rate:4.2f} img/s"
        )
        if sample_id:
            status += f" | {sample_id}"
        if renderer:
            status += f" ({renderer})"
        self._write_status(status)

    def _write_status(self, status: str) -> None:
        clear = " " * max(0, self.last_len - len(status))
        self.stream.write("\r" + status + clear)
        self.stream.flush()
        self.last_len = len(status)


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic manga/game OCR/VLM data.")
    parser.add_argument("--output", type=Path, default=Path("data/generated/synthetic_poc"))
    parser.add_argument("--count", type=int, default=20, help="Number of images to generate.")
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--clean", action="store_true", help="Delete the output directory before generation.")
    parser.add_argument("--no-augment", action="store_true", help="Disable image augmentation.")
    parser.add_argument(
        "--difficulty",
        choices=("normal", "dense"),
        default="normal",
        help="Use dense to render busier scenes with more visible text regions.",
    )
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
    parser.add_argument(
        "--blocks-per-sample",
        type=int,
        default=None,
        help="Semantic text blocks per image. Defaults to 5 for normal and 12 for dense.",
    )
    parser.add_argument("--no-progress", action="store_true", help="Disable progress bar and ETA output.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    progress = None if args.no_progress else ProgressBar(args.count)
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
        difficulty=args.difficulty,
        progress_callback=progress.update if progress else None,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
