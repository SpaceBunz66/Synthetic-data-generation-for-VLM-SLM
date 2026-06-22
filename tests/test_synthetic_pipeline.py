from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from synthetic_data.content import ContentProvider
from synthetic_data.generator import generate_dataset
from synthetic_data.renderers import GAME_NAMEPLATE_TEXTS
from synthetic_data.validation import (
    validate_ocr_payload,
    validate_output_dir,
    validate_trans_payload,
    validate_vlm_payload,
)


class SyntheticPipelineTests(unittest.TestCase):
    def test_generates_expected_exports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dataset"
            summary = generate_dataset(
                out,
                count=4,
                seed=42,
                clean=True,
                augment=True,
                game_renderer="pillow",
            )
            self.assertEqual(summary["validation"]["error_count"], 0)
            self.assertEqual(summary["validation"]["sample_count"], 4)
            self.assertEqual(summary["validation"]["category_counts"], {"manga": 2, "game": 2})
            self.assertEqual(summary["difficulty"], "normal")
            self.assertEqual(summary["blocks_per_sample"], 5)
            self.assertTrue((out / "chat_vlm.jsonl").exists())
            self.assertTrue((out / "annotations" / "vlm" / "manga_000000.json").exists())
            self.assertTrue((out / "annotations" / "ocr" / "manga_000000.json").exists())
            self.assertTrue((out / "annotations" / "trans" / "manga_000000.json").exists())
            canonical = json.loads((out / "annotations" / "canonical" / "manga_000000.json").read_text(encoding="utf-8"))
            self.assertEqual(canonical["metadata"]["difficulty"], "normal")
            self.assertEqual(canonical["metadata"]["requested_blocks"], 5)
            self.assertEqual(canonical["metadata"]["rendered_line_count"], len(canonical["content"]))

    def test_chat_answer_matches_vlm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dataset"
            generate_dataset(out, count=2, seed=7, clean=True, augment=False, game_renderer="pillow")
            records = [
                json.loads(line)
                for line in (out / "chat_vlm.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            for record in records:
                expected = json.loads((out / "annotations" / "vlm" / f"{record['id']}.json").read_text(encoding="utf-8"))
                actual = json.loads(record["messages"][1]["content"])
                self.assertEqual(actual, expected)

    def test_deterministic_without_augmentation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first"
            second = Path(tmp) / "second"
            generate_dataset(first, count=2, seed=99, clean=True, augment=False, game_renderer="pillow")
            generate_dataset(second, count=2, seed=99, clean=True, augment=False, game_renderer="pillow")
            first_vlm = (first / "annotations" / "vlm" / "manga_000000.json").read_text(encoding="utf-8")
            second_vlm = (second / "annotations" / "vlm" / "manga_000000.json").read_text(encoding="utf-8")
            self.assertEqual(first_vlm, second_vlm)

    def test_dense_difficulty_increases_game_text_density(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            normal = Path(tmp) / "normal"
            dense = Path(tmp) / "dense"
            normal_summary = generate_dataset(
                normal,
                count=2,
                seed=101,
                clean=True,
                augment=False,
                game_renderer="pillow",
                difficulty="normal",
            )
            dense_summary = generate_dataset(
                dense,
                count=2,
                seed=101,
                clean=True,
                augment=False,
                game_renderer="pillow",
                difficulty="dense",
            )
            self.assertEqual(normal_summary["validation"]["error_count"], 0)
            self.assertEqual(dense_summary["validation"]["error_count"], 0)
            self.assertEqual(dense_summary["blocks_per_sample"], 12)

            normal_game = json.loads((normal / "annotations" / "canonical" / "game_000001.json").read_text(encoding="utf-8"))
            dense_game = json.loads((dense / "annotations" / "canonical" / "game_000001.json").read_text(encoding="utf-8"))
            dense_groups = {line["group_id"] for line in dense_game["content"]}

            self.assertEqual(dense_game["metadata"]["difficulty"], "dense")
            self.assertEqual(dense_game["metadata"]["requested_blocks"], 12)
            self.assertGreater(len(dense_groups), 5)
            self.assertGreater(dense_game["metadata"]["rendered_line_count"], normal_game["metadata"]["rendered_line_count"])

    def test_renderers_vary_panel_and_game_scene_styles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dataset"
            summary = generate_dataset(
                out,
                count=8,
                seed=404,
                clean=True,
                augment=False,
                game_renderer="pillow",
                difficulty="dense",
            )
            self.assertEqual(summary["validation"]["error_count"], 0)

            panel_layouts = set()
            panel_art_styles = set()
            panel_art_counts = []
            panel_art_overlaps = []
            scene_styles = set()
            bubble_overlaps = []
            noise_patterns = set()
            nameplate_texts = []
            for path in (out / "annotations" / "canonical").glob("*.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload["category"] == "manga":
                    panel_layouts.add(payload["metadata"].get("panel_layout"))
                    panel_art = payload["metadata"].get("panel_art", {})
                    panel_art_styles.update(panel_art.get("styles", []))
                    panel_art_counts.append(panel_art.get("art_count", 0))
                    panel_art_overlaps.append(panel_art.get("bubble_overlap_max", 1.0))
                    bubble_overlaps.append(payload["metadata"].get("bubble_overlap_max", 1.0))
                    noise_patterns.update(payload["metadata"].get("panel_noise", {}).get("patterns", []))
                if payload["category"] == "game":
                    scene_styles.add(payload["metadata"].get("scene_style"))
                    if payload["metadata"].get("scene_style") == "nameplate_scene":
                        nameplate_texts.extend(line["text"] for line in payload["content"])

            self.assertGreaterEqual(len(panel_layouts), 2)
            self.assertGreaterEqual(len(panel_art_styles), 3)
            self.assertTrue(panel_art_counts)
            self.assertTrue(all(count >= 5 for count in panel_art_counts))
            self.assertLessEqual(max(panel_art_overlaps), 0.2)
            self.assertGreaterEqual(len(scene_styles), 2)
            self.assertLessEqual(max(bubble_overlaps), 0.2)
            self.assertIn("paper_grain", noise_patterns)
            self.assertTrue({"screentone", "hatching", "dust_scratches"} & noise_patterns)
            self.assertTrue(nameplate_texts)
            self.assertTrue(all(text in GAME_NAMEPLATE_TEXTS for text in nameplate_texts))

    def test_dense_difficulty_is_deterministic_without_augmentation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first"
            second = Path(tmp) / "second"
            generate_dataset(first, count=2, seed=303, clean=True, augment=False, game_renderer="pillow", difficulty="dense")
            generate_dataset(second, count=2, seed=303, clean=True, augment=False, game_renderer="pillow", difficulty="dense")
            first_vlm = (first / "annotations" / "vlm" / "game_000001.json").read_text(encoding="utf-8")
            second_vlm = (second / "annotations" / "vlm" / "game_000001.json").read_text(encoding="utf-8")
            self.assertEqual(first_vlm, second_vlm)

    def test_content_is_single_language_per_image_and_domain_specific(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dataset"
            generate_dataset(out, count=8, seed=123, clean=True, augment=False, game_renderer="pillow")

            banned_action_words = ("rầm", "ầm", "boom", "bang", "crash", "ドン", "轰", "쾅")
            manga_game_terms = ("quest", "inventory", "hp ", "mp ", "save point", "skill unlocked")
            game_seen = False

            for path in (out / "annotations" / "canonical").glob("*.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                languages = {line["source_language"] for line in payload["content"]}
                self.assertEqual(len(languages), 1, path.name)
                source_language = next(iter(languages))
                self.assertEqual(source_language, "en")
                for line in payload["content"]:
                    text = line["text"].casefold()
                    translated = line["translated_text"].casefold()
                    self.assertNotEqual(line["kind"], "sfx")
                    self.assertFalse(any(word in text or word in translated for word in banned_action_words), path.name)
                    if payload["category"] == "manga":
                        self.assertFalse(any(term in text for term in manga_game_terms), path.name)
                    if payload["category"] == "game":
                        game_seen = game_seen or line["kind"] in {"hud", "quest", "menu"}

            self.assertTrue(game_seen)

    def test_fallback_content_has_high_diversity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            provider = ContentProvider(Path(tmp) / "cache")
            texts = []
            for i in range(18):
                category = "manga" if i % 2 == 0 else "game"
                blocks = provider.make_blocks(category, seed=9000 + i * 101, count=8)
                self.assertEqual({block.source_language for block in blocks}, {"en"})
                texts.extend(block.text for block in blocks)

            unique_ratio = len(set(texts)) / len(texts)
            self.assertGreater(unique_ratio, 0.78)

    def test_api_provider_without_key_falls_back_to_rich_generator(self) -> None:
        old_key = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cache = Path(tmp) / "cache"
                provider = ContentProvider(cache, provider="gemini")
                blocks = provider.make_blocks("game", seed=3030, count=5)
                self.assertEqual(len(blocks), 5)
                self.assertEqual(len({block.text for block in blocks}), 5)
                self.assertEqual({block.source_language for block in blocks}, {"en"})
                payloads = [json.loads(path.read_text(encoding="utf-8")) for path in cache.glob("*.json")]
                self.assertTrue(any("api_error" in payload for payload in payloads))
        finally:
            if old_key is not None:
                os.environ["GEMINI_API_KEY"] = old_key

    def test_existing_example_json_shapes_are_valid(self) -> None:
        root = Path(__file__).resolve().parents[1]
        example_dir = root / "data" / "example_json_output"
        if not example_dir.exists():
            self.skipTest("Optional data/example_json_output fixtures are not present.")
        image_width = 1200
        image_height = 1800
        vlm = json.loads((example_dir / "vlm.json").read_text(encoding="utf-8"))
        ocr = json.loads((example_dir / "ocr.json").read_text(encoding="utf-8"))
        trans = json.loads((example_dir / "trans.json").read_text(encoding="utf-8"))
        self.assertEqual(validate_vlm_payload(vlm, image_width, image_height), [])
        self.assertEqual(validate_ocr_payload(ocr, image_width, image_height), [])
        self.assertEqual(validate_trans_payload(trans), [])


if __name__ == "__main__":
    unittest.main()
