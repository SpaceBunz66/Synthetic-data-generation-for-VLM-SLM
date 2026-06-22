"""End-to-end synthetic dataset generation."""

from __future__ import annotations

import random
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from synthetic_data.augment import Augmentor
from synthetic_data.content import ContentProvider
from synthetic_data.exporters import SyntheticDatasetWriter
from synthetic_data.renderers import GameRenderer, MangaRenderer
from synthetic_data.schema import SyntheticSample
from synthetic_data.validation import validate_output_dir


def generate_dataset(
    output_dir: Path,
    count: int = 20,
    seed: int = 1337,
    clean: bool = False,
    augment: bool = True,
    use_llm: bool = False,
    llm_model: str | None = None,
    content_provider: str = "fallback",
    content_model: str | None = None,
    api_timeout: int = 45,
    game_renderer: str = "auto",
    blocks_per_sample: int | None = None,
    difficulty: str = "normal",
) -> Dict[str, Any]:
    """Generate a synthetic manga/game dataset and return validation summary."""

    if difficulty not in {"normal", "dense"}:
        raise ValueError("difficulty must be one of: normal, dense")

    requested_blocks = blocks_per_sample if blocks_per_sample is not None else (12 if difficulty == "dense" else 5)

    output_dir = output_dir.resolve()
    if clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    selected_model = content_model or llm_model
    content_provider_obj = ContentProvider(
        output_dir / "cache" / "content",
        use_llm=use_llm,
        model=selected_model,
        provider=content_provider,
        api_timeout=api_timeout,
    )
    writer = SyntheticDatasetWriter(output_dir)
    augmentor = Augmentor(enabled=augment)
    manga_renderer = MangaRenderer(difficulty=difficulty)
    game_renderer_obj = GameRenderer(mode=game_renderer, difficulty=difficulty)

    category_counts: Counter[str] = Counter()
    renderer_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()

    for index in range(count):
        category = "manga" if index % 2 == 0 else "game"
        sample_seed = seed + index * 1009
        rng = random.Random(sample_seed)
        sample_id = f"{category}_{index:06d}"

        blocks = content_provider_obj.make_blocks(category, sample_seed, requested_blocks)
        if category == "manga":
            rendered = manga_renderer.render(sample_id, blocks, rng)
        else:
            rendered = game_renderer_obj.render(sample_id, blocks, rng)

        image, lines, augmentation_meta = augmentor.apply(rendered.image, rendered.sample.lines, rng)
        metadata = dict(rendered.sample.metadata)
        metadata.update(
            {
                "seed": sample_seed,
                "source_languages": sorted({block.source_language for block in blocks}),
                "content_cache": "cache/content",
                "augmentation": augmentation_meta,
                "difficulty": difficulty,
                "requested_blocks": requested_blocks,
                "rendered_line_count": len(lines),
            }
        )

        image_file = f"images/{sample_id}.png"
        sample = SyntheticSample(
            id=sample_id,
            category=category,
            image_file=image_file,
            image_width=image.width,
            image_height=image.height,
            content=lines,
            metadata=metadata,
        )
        writer.write_sample(sample, image)

        category_counts[category] += 1
        renderer_counts[str(metadata.get("renderer", "unknown"))] += 1
        language_counts.update(line.source_language for line in lines)

    summary: Dict[str, Any] = {
        "requested_count": count,
        "seed": seed,
        "augment": augment,
        "use_llm": content_provider_obj.use_llm,
        "content_provider": content_provider_obj.provider,
        "content_model": content_provider_obj.model,
        "game_renderer": game_renderer,
        "blocks_per_sample": requested_blocks,
        "difficulty": difficulty,
        "category_counts": dict(category_counts),
        "renderer_counts": dict(renderer_counts),
        "language_counts": dict(language_counts),
    }
    validation = validate_output_dir(output_dir)
    summary["validation"] = validation
    writer.write_summary(summary)
    return summary
