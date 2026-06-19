"""Canonical schema objects for synthetic dataset generation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Dict, List


BBox = List[int]


@dataclass(frozen=True)
class TextBlock:
    """A semantic text block before rendering wraps it into visual lines."""

    id: int
    text: str
    translated_text: str
    source_language: str
    kind: str
    group_id: str


@dataclass(frozen=True)
class LineAnnotation:
    """A rendered line annotation with pixel coordinates."""

    id: int
    group_id: str
    bbox_2d: BBox
    text: str
    translated_text: str
    source_language: str
    kind: str

    def with_bbox(self, bbox_2d: BBox) -> "LineAnnotation":
        return replace(self, bbox_2d=[int(v) for v in bbox_2d])

    def to_ocr(self) -> Dict[str, Any]:
        return {"bbox_2d": self.bbox_2d, "text": self.text}

    def to_trans(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "translated_text": self.translated_text,
        }

    def to_vlm(self) -> Dict[str, Any]:
        return {
            "bbox_2d": self.bbox_2d,
            "text": self.text,
            "translated_text": self.translated_text,
        }

    def to_canonical(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RenderedSample:
    """Renderer result before export."""

    image_width: int
    image_height: int
    lines: List[LineAnnotation]
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class SyntheticSample:
    """Canonical exported sample."""

    id: str
    category: str
    image_file: str
    image_width: int
    image_height: int
    content: List[LineAnnotation]
    metadata: Dict[str, Any]

    def to_canonical(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "image": {
                "file_name": self.image_file,
                "width": self.image_width,
                "height": self.image_height,
            },
            "content": [line.to_canonical() for line in self.content],
            "metadata": self.metadata,
        }

    def to_vlm(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "content": [line.to_vlm() for line in self.content],
        }

    def to_ocr(self) -> List[Dict[str, Any]]:
        return [line.to_ocr() for line in self.content]

    def to_trans(self) -> List[Dict[str, Any]]:
        return [line.to_trans() for line in self.content]
