"""Text wrapping and bbox helpers."""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

from PIL import ImageDraw, ImageFont


def text_bbox(draw: ImageDraw.ImageDraw, xy: Tuple[int, int], text: str, font: ImageFont.ImageFont) -> List[int]:
    bbox = draw.textbbox(xy, text, font=font)
    return [int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])]


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int = 5,
) -> List[str]:
    if not text:
        return []

    tokens = _tokens(text)
    separator = " " if " " in text else ""
    lines: List[str] = []
    current = ""
    for token in tokens:
        candidate = token if not current else current + separator + token
        if text_size(draw, candidate, font)[0] <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        if len(lines) >= max_lines - 1:
            current = token
            break
        current = token

    if current:
        lines.append(current)
    return _fit_last_line(draw, lines[:max_lines], font, max_width)


def clamp_bbox(bbox: Sequence[float], width: int, height: int) -> List[int]:
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(width - 1, int(round(x1))))
    y1 = max(0, min(height - 1, int(round(y1))))
    x2 = max(0, min(width, int(round(x2))))
    y2 = max(0, min(height, int(round(y2))))
    if x2 <= x1:
        x2 = min(width, x1 + 1)
    if y2 <= y1:
        y2 = min(height, y1 + 1)
    return [x1, y1, x2, y2]


def union_bbox(boxes: Iterable[Sequence[int]]) -> List[int]:
    boxes = list(boxes)
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def _tokens(text: str) -> List[str]:
    if " " in text:
        return text.split()
    return list(text)


def _fit_last_line(
    draw: ImageDraw.ImageDraw,
    lines: List[str],
    font: ImageFont.ImageFont,
    max_width: int,
) -> List[str]:
    if not lines:
        return []
    last = lines[-1]
    if text_size(draw, last, font)[0] <= max_width:
        return lines

    base = last
    while len(base) > 1 and text_size(draw, base + "...", font)[0] > max_width:
        base = base[:-1]
    lines[-1] = base + "..." if base != last else base
    return lines
