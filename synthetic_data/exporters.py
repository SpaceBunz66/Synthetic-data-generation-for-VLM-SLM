"""Dataset exporters for canonical, OCR, translation, VLM, and chat JSONL outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from PIL import Image

from synthetic_data.schema import SyntheticSample


VLM_INSTRUCTION = (
    "Extract every visible text line from the image. Return JSON with category and content. "
    "Each content item must include bbox_2d as [x1,y1,x2,y2], text, and translated_text."
)


class SyntheticDatasetWriter:
    """Write all generated dataset views in a stable directory layout."""

    def __init__(self, output_dir: Path, append: bool = False) -> None:
        self.output_dir = output_dir
        self.image_dir = output_dir / "images"
        self.canonical_dir = output_dir / "annotations" / "canonical"
        self.vlm_dir = output_dir / "annotations" / "vlm"
        self.ocr_dir = output_dir / "annotations" / "ocr"
        self.trans_dir = output_dir / "annotations" / "trans"
        for path in [self.image_dir, self.canonical_dir, self.vlm_dir, self.ocr_dir, self.trans_dir]:
            path.mkdir(parents=True, exist_ok=True)

        self.manifest_path = output_dir / "manifest.jsonl"
        self.chat_path = output_dir / "chat_vlm.jsonl"
        self.vlm_jsonl_path = output_dir / "annotations" / "vlm.jsonl"
        self.ocr_jsonl_path = output_dir / "annotations" / "ocr.jsonl"
        self.trans_jsonl_path = output_dir / "annotations" / "trans.jsonl"
        if not append:
            for path in [
                self.manifest_path,
                self.chat_path,
                self.vlm_jsonl_path,
                self.ocr_jsonl_path,
                self.trans_jsonl_path,
            ]:
                if path.exists():
                    path.unlink()

    def write_sample(self, sample: SyntheticSample, image: Image.Image) -> None:
        image_path = self.output_dir / sample.image_file
        image.save(image_path)

        self._write_json(self.canonical_dir / f"{sample.id}.json", sample.to_canonical())
        self._write_json(self.vlm_dir / f"{sample.id}.json", sample.to_vlm())
        self._write_json(self.ocr_dir / f"{sample.id}.json", sample.to_ocr())
        self._write_json(self.trans_dir / f"{sample.id}.json", sample.to_trans())

        self._append_jsonl(self.manifest_path, self._manifest_record(sample))
        self._append_jsonl(self.chat_path, self._chat_record(sample))
        self._append_jsonl(self.vlm_jsonl_path, {"id": sample.id, "image": sample.image_file, "output": sample.to_vlm()})
        self._append_jsonl(self.ocr_jsonl_path, {"id": sample.id, "image": sample.image_file, "output": sample.to_ocr()})
        self._append_jsonl(self.trans_jsonl_path, {"id": sample.id, "image": sample.image_file, "output": sample.to_trans()})

    def write_summary(self, summary: Dict[str, Any]) -> None:
        self._write_json(self.output_dir / "summary.json", summary)

    def _manifest_record(self, sample: SyntheticSample) -> Dict[str, Any]:
        return {
            "id": sample.id,
            "category": sample.category,
            "image": sample.image_file,
            "width": sample.image_width,
            "height": sample.image_height,
            "line_count": len(sample.content),
            "languages": sorted({line.source_language for line in sample.content}),
            "renderer": sample.metadata.get("renderer"),
            "augmentation": sample.metadata.get("augmentation", {}),
            "paths": {
                "canonical": f"annotations/canonical/{sample.id}.json",
                "vlm": f"annotations/vlm/{sample.id}.json",
                "ocr": f"annotations/ocr/{sample.id}.json",
                "trans": f"annotations/trans/{sample.id}.json",
            },
        }

    def _chat_record(self, sample: SyntheticSample) -> Dict[str, Any]:
        return {
            "id": sample.id,
            "image": sample.image_file,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": sample.image_file},
                        {"type": "text", "text": VLM_INSTRUCTION},
                    ],
                },
                {
                    "role": "assistant",
                    "content": json.dumps(sample.to_vlm(), ensure_ascii=False, separators=(",", ":")),
                },
            ],
        }

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _append_jsonl(path: Path, payload: Any) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
