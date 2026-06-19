from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from synthetic_data.content import ContentProvider
from synthetic_data.generator import generate_dataset
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
            self.assertTrue((out / "chat_vlm.jsonl").exists())
            self.assertTrue((out / "annotations" / "vlm" / "manga_000000.json").exists())
            self.assertTrue((out / "annotations" / "ocr" / "manga_000000.json").exists())
            self.assertTrue((out / "annotations" / "trans" / "manga_000000.json").exists())

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

    def test_content_is_single_language_per_image_and_domain_specific(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dataset"
            generate_dataset(out, count=8, seed=123, clean=True, augment=False, game_renderer="pillow")

            banned_action_words = ("rầm", "ầm", "boom", "bang", "crash", "ドン", "轰", "쾅")
            manga_game_terms = ("quest", "inventory", "hp ", "mp ", "save point", "skill unlocked")
            english_ui_terms = ("COMBO", "SAVE", "START", "SKILLS", "INVENTORY", "OPTIONS")
            game_seen = False

            for path in (out / "annotations" / "canonical").glob("*.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                languages = {line["source_language"] for line in payload["content"]}
                self.assertEqual(len(languages), 1, path.name)
                source_language = next(iter(languages))
                self.assertIn(source_language, {"en", "ja", "zh"})
                for line in payload["content"]:
                    text = line["text"].casefold()
                    translated = line["translated_text"].casefold()
                    self.assertNotEqual(line["kind"], "sfx")
                    self.assertFalse(any(word in text or word in translated for word in banned_action_words), path.name)
                    if payload["category"] == "manga":
                        self.assertFalse(any(term in text for term in manga_game_terms), path.name)
                    if payload["category"] == "game":
                        if source_language != "en":
                            self.assertFalse(any(term.casefold() in text for term in english_ui_terms), path.name)
                        game_seen = game_seen or line["kind"] in {"hud", "quest", "menu"}

            self.assertTrue(game_seen)

    def test_fallback_content_has_high_diversity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            provider = ContentProvider(Path(tmp) / "cache")
            texts = []
            for i in range(18):
                category = "manga" if i % 2 == 0 else "game"
                blocks = provider.make_blocks(category, seed=9000 + i * 101, count=8)
                self.assertEqual(len({block.source_language for block in blocks}), 1)
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
