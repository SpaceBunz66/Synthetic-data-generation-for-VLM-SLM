"""Font loading helpers with Windows-friendly fallbacks."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Optional

from PIL import ImageFont


WINDOWS_FONT_DIR = Path("C:/Windows/Fonts")

FONT_CANDIDATES: Dict[str, Iterable[str]] = {
    "en": ("arialbd.ttf", "arial.ttf", "segoeuib.ttf", "segoeui.ttf"),
    "ja": ("meiryob.ttc", "meiryo.ttc", "YuGothB.ttc", "YuGothR.ttc", "msgothic.ttc"),
    "zh": ("msyhbd.ttc", "msyh.ttc", "simhei.ttf", "simsun.ttc"),
    "ko": ("malgunbd.ttf", "malgun.ttf", "gulim.ttc"),
    "default": (
        "arialbd.ttf",
        "arial.ttf",
        "segoeuib.ttf",
        "segoeui.ttf",
        "meiryo.ttc",
        "msyh.ttc",
        "malgun.ttf",
    ),
}


def _first_existing(names: Iterable[str]) -> Optional[Path]:
    for name in names:
        path = WINDOWS_FONT_DIR / name
        if path.exists():
            return path
    return None


def load_font(size: int, language: str = "default", bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a font likely to cover the requested source language."""

    names = list(FONT_CANDIDATES.get(language, ()))
    if bold and language == "en":
        names = ["arialbd.ttf", "segoeuib.ttf", *names]
    names.extend(FONT_CANDIDATES["default"])

    font_path = _first_existing(names)
    if font_path:
        return ImageFont.truetype(str(font_path), size=size)
    return ImageFont.load_default(size=size)
