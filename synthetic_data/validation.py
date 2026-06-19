"""Schema and dataset validation helpers."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

from PIL import Image

from synthetic_data.content import ACTION_WORD_MARKERS


MANGA_FORBIDDEN_GAME_TERMS = ("quest", "inventory", "hp ", "mp ", "save point", "skill unlocked")


def validate_output_dir(output_dir: Path) -> Dict[str, Any]:
    manifest_path = output_dir / "manifest.jsonl"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")

    errors: List[str] = []
    category_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    renderer_counts: Counter[str] = Counter()
    sample_count = 0

    for record in _read_jsonl(manifest_path):
        sample_count += 1
        sample_id = record["id"]
        category_counts[record["category"]] += 1
        renderer_counts[str(record.get("renderer"))] += 1
        image_path = output_dir / record["image"]
        if not image_path.exists():
            errors.append(f"{sample_id}: missing image {record['image']}")
            continue
        with Image.open(image_path) as image:
            width, height = image.size

        paths = record["paths"]
        vlm = _read_json(output_dir / paths["vlm"])
        ocr = _read_json(output_dir / paths["ocr"])
        trans = _read_json(output_dir / paths["trans"])
        canonical = _read_json(output_dir / paths["canonical"])

        errors.extend(validate_vlm_payload(vlm, width, height, context=f"{sample_id}:vlm"))
        errors.extend(validate_ocr_payload(ocr, width, height, context=f"{sample_id}:ocr"))
        errors.extend(validate_trans_payload(trans, context=f"{sample_id}:trans"))
        errors.extend(validate_canonical_payload(canonical, context=f"{sample_id}:canonical"))
        if len(vlm["content"]) != len(ocr) or len(vlm["content"]) != len(trans):
            errors.append(f"{sample_id}: output line counts differ")
        for line in canonical.get("content", []):
            language_counts[str(line.get("source_language", "unknown"))] += 1

    chat_errors = validate_chat_jsonl(output_dir / "chat_vlm.jsonl", output_dir)
    errors.extend(chat_errors)

    return {
        "sample_count": sample_count,
        "category_counts": dict(category_counts),
        "language_counts": dict(language_counts),
        "renderer_counts": dict(renderer_counts),
        "error_count": len(errors),
        "errors": errors,
    }


def validate_vlm_payload(payload: Any, width: int, height: int, context: str = "vlm") -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return [f"{context}: expected object"]
    if payload.get("category") not in {"manga", "game"}:
        errors.append(f"{context}: category must be manga or game")
    content = payload.get("content")
    if not isinstance(content, list):
        return errors + [f"{context}: content must be list"]
    for idx, item in enumerate(content, start=1):
        errors.extend(_validate_text_item(item, width, height, f"{context}:content[{idx}]"))
        if "translated_text" not in item or not str(item.get("translated_text", "")).strip():
            errors.append(f"{context}:content[{idx}]: missing translated_text")
    return errors


def validate_ocr_payload(payload: Any, width: int, height: int, context: str = "ocr") -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, list):
        return [f"{context}: expected list"]
    for idx, item in enumerate(payload, start=1):
        errors.extend(_validate_text_item(item, width, height, f"{context}[{idx}]"))
    return errors


def validate_trans_payload(payload: Any, context: str = "trans") -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, list):
        return [f"{context}: expected list"]
    for idx, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            errors.append(f"{context}[{idx}]: expected object")
            continue
        if "id" not in item:
            errors.append(f"{context}[{idx}]: missing id")
        if not str(item.get("text", "")).strip():
            errors.append(f"{context}[{idx}]: missing text")
        if not str(item.get("translated_text", "")).strip():
            errors.append(f"{context}[{idx}]: missing translated_text")
    return errors


def validate_canonical_payload(payload: Any, context: str = "canonical") -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return [f"{context}: expected object"]
    category = payload.get("category")
    content = payload.get("content")
    if not isinstance(content, list):
        return [f"{context}: content must be list"]

    languages = {line.get("source_language") for line in content if isinstance(line, dict)}
    if len(languages) > 1:
        errors.append(f"{context}: mixed source languages {sorted(languages)}")

    for idx, line in enumerate(content, start=1):
        if not isinstance(line, dict):
            errors.append(f"{context}:content[{idx}]: expected object")
            continue
        kind = str(line.get("kind", ""))
        text = str(line.get("text", "")).casefold()
        translated = str(line.get("translated_text", "")).casefold()
        if kind == "sfx":
            errors.append(f"{context}:content[{idx}]: sfx kind is not allowed in default dataset")
        if any(marker in text or marker in translated for marker in ACTION_WORD_MARKERS):
            errors.append(f"{context}:content[{idx}]: action/sfx word leaked into text")
        if category == "manga" and any(term in text for term in MANGA_FORBIDDEN_GAME_TERMS):
            errors.append(f"{context}:content[{idx}]: game term leaked into manga text")
    return errors


def validate_chat_jsonl(chat_path: Path, output_dir: Path) -> List[str]:
    errors: List[str] = []
    if not chat_path.exists():
        return [f"missing chat jsonl: {chat_path}"]
    for record in _read_jsonl(chat_path):
        sample_id = record.get("id", "<unknown>")
        messages = record.get("messages", [])
        if len(messages) != 2:
            errors.append(f"{sample_id}: chat must have user and assistant messages")
            continue
        try:
            assistant_payload = json.loads(messages[1]["content"])
        except Exception as exc:
            errors.append(f"{sample_id}: assistant content is not JSON: {exc}")
            continue
        vlm_path = output_dir / "annotations" / "vlm" / f"{sample_id}.json"
        if vlm_path.exists() and assistant_payload != _read_json(vlm_path):
            errors.append(f"{sample_id}: chat assistant JSON does not match vlm output")
    return errors


def _validate_text_item(item: Any, width: int, height: int, context: str) -> List[str]:
    errors: List[str] = []
    if not isinstance(item, dict):
        return [f"{context}: expected object"]
    bbox = item.get("bbox_2d")
    if not _valid_bbox(bbox, width, height):
        errors.append(f"{context}: invalid bbox_2d {bbox}")
    if not str(item.get("text", "")).strip():
        errors.append(f"{context}: missing text")
    return errors


def _valid_bbox(bbox: Any, width: int, height: int) -> bool:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return False
    if not all(isinstance(v, int) for v in bbox):
        return False
    x1, y1, x2, y2 = bbox
    return 0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)
