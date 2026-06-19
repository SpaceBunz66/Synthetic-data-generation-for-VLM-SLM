# -*- coding: utf-8 -*-
"""Synthetic manga and game renderers."""

from __future__ import annotations

import html
import io
import math
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw

from synthetic_data.fonts import load_font
from synthetic_data.layout import clamp_bbox, text_bbox, text_size, wrap_text
from synthetic_data.schema import LineAnnotation, RenderedSample, TextBlock


@dataclass(frozen=True)
class RenderResult:
    image: Image.Image
    sample: RenderedSample


class MangaRenderer:
    """Pillow renderer for original, license-safe manga-style pages."""

    width = 1024
    height = 1440

    def render(self, sample_id: str, blocks: Sequence[TextBlock], rng: random.Random) -> RenderResult:
        image = Image.new("RGB", (self.width, self.height), "white")
        draw = ImageDraw.Draw(image)
        panel_rects = self._draw_panels(draw, rng)
        lines: List[LineAnnotation] = []

        for idx, block in enumerate(blocks):
            panel = panel_rects[idx % len(panel_rects)]
            bubble = self._bubble_rect(panel, idx, len(panel_rects), rng)
            self._draw_bubble(draw, bubble, rng)
            font, font_size, visual_lines, line_height = self._fit_bubble_text(draw, bubble, block, rng)
            total_height = line_height * len(visual_lines)
            y = int((bubble[1] + bubble[3] - total_height) / 2)
            for visual_line in visual_lines:
                w, _ = text_size(draw, visual_line, font)
                x = int((bubble[0] + bubble[2] - w) / 2)
                draw.text((x, y), visual_line, font=font, fill=(8, 8, 8))
                box = clamp_bbox(text_bbox(draw, (x, y), visual_line, font), self.width, self.height)
                lines.append(
                    LineAnnotation(
                        id=len(lines) + 1,
                        group_id=block.group_id,
                        bbox_2d=box,
                        text=visual_line,
                        translated_text=block.translated_text,
                        source_language=block.source_language,
                        kind=block.kind,
                    )
                )
                y += line_height

        metadata = {
            "renderer": "manga_pillow",
            "template": "synthetic_panels_bubbles_v1",
            "asset_provenance": "procedural/licensed-by-construction",
            "sample_id": sample_id,
        }
        return RenderResult(
            image=image,
            sample=RenderedSample(self.width, self.height, lines, metadata),
        )

    def _draw_panels(self, draw: ImageDraw.ImageDraw, rng: random.Random) -> List[Tuple[int, int, int, int]]:
        panels = [
            (60, 45, 964, 385),
            (60, 420, 493, 810),
            (530, 420, 964, 810),
            (60, 850, 964, 1370),
        ]
        for i, rect in enumerate(panels):
            draw.rectangle(rect, fill=(248, 248, 248), outline=(0, 0, 0), width=5)
            self._draw_panel_texture(draw, rect, rng, density=12 + i * 3)
        return panels

    def _draw_panel_texture(
        self,
        draw: ImageDraw.ImageDraw,
        rect: Tuple[int, int, int, int],
        rng: random.Random,
        density: int,
    ) -> None:
        x1, y1, x2, y2 = rect
        for y in range(y1 + 14, y2, density):
            shade = rng.randint(190, 225)
            draw.line((x1 + 4, y, x2 - 4, y), fill=(shade, shade, shade), width=1)
        for _ in range(32):
            cx = rng.randint(x1 + 30, x2 - 30)
            cy = rng.randint(y1 + 30, y2 - 30)
            radius = rng.randint(10, 45)
            shade = rng.randint(205, 240)
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=(shade, shade, shade), width=1)

    def _bubble_rect(
        self,
        panel: Tuple[int, int, int, int],
        idx: int,
        panel_count: int,
        rng: random.Random,
    ) -> Tuple[int, int, int, int]:
        x1, y1, x2, y2 = panel
        panel_w = x2 - x1
        panel_h = y2 - y1
        bw = rng.randint(max(210, panel_w // 4), max(260, panel_w // 2))
        bh = rng.randint(130, min(230, max(150, panel_h - 60)))
        zones = [
            (x1 + 28, y1 + 28),
            (x2 - bw - 28, y1 + 38),
            (x1 + 32, y2 - bh - 38),
            (x2 - bw - 34, y2 - bh - 34),
        ]
        zone_index = (idx + idx // panel_count) % len(zones)
        bx, by = zones[zone_index]
        bx += rng.randint(-12, 12)
        by += rng.randint(-10, 10)
        return (bx, by, bx + bw, by + bh)

    def _fit_bubble_text(
        self,
        draw: ImageDraw.ImageDraw,
        bubble: Tuple[int, int, int, int],
        block: TextBlock,
        rng: random.Random,
    ) -> Tuple[Any, int, List[str], int]:
        max_width = max(60, bubble[2] - bubble[0] - 48)
        max_height = max(50, bubble[3] - bubble[1] - 36)
        start_size = rng.randint(26, 38) if block.kind != "sfx" else rng.randint(32, 46)
        for font_size in range(start_size, 17, -2):
            font = load_font(font_size, block.source_language, bold=True)
            line_height = max(font_size + 7, 24)
            visual_lines = wrap_text(draw, block.text, font, max_width=max_width, max_lines=5)
            if visual_lines and line_height * len(visual_lines) <= max_height:
                return font, font_size, visual_lines, line_height
        font_size = 18
        font = load_font(font_size, block.source_language, bold=True)
        line_height = 24
        visual_lines = wrap_text(draw, block.text, font, max_width=max_width, max_lines=4)
        return font, font_size, visual_lines, line_height

    def _draw_bubble(
        self,
        draw: ImageDraw.ImageDraw,
        rect: Tuple[int, int, int, int],
        rng: random.Random,
    ) -> None:
        if rng.random() < 0.55:
            draw.rounded_rectangle(rect, radius=42, fill=(255, 255, 255), outline=(0, 0, 0), width=4)
        else:
            draw.ellipse(rect, fill=(255, 255, 255), outline=(0, 0, 0), width=4)
        x1, y1, x2, y2 = rect
        tail_x = rng.randint(x1 + 40, x2 - 40)
        tail_y = y2 - rng.randint(4, 16)
        draw.polygon(
            [(tail_x - 14, tail_y), (tail_x + 18, tail_y), (tail_x + rng.randint(-20, 20), tail_y + 44)],
            fill=(255, 255, 255),
            outline=(0, 0, 0),
        )


class GameRenderer:
    """HTML/Playwright renderer with Pillow fallback."""

    width = 640
    height = 640

    def __init__(self, mode: str = "auto") -> None:
        if mode not in {"auto", "playwright", "pillow"}:
            raise ValueError("mode must be one of: auto, playwright, pillow")
        self.mode = mode

    def render(self, sample_id: str, blocks: Sequence[TextBlock], rng: random.Random) -> RenderResult:
        if self.mode in {"auto", "playwright"}:
            try:
                return self._render_with_playwright(sample_id, blocks, rng)
            except Exception as exc:
                if self.mode == "playwright":
                    raise
                result = self._render_with_pillow(sample_id, blocks, rng)
                result.sample.metadata["playwright_error"] = f"{type(exc).__name__}: {exc}"
                return result
        return self._render_with_pillow(sample_id, blocks, rng)

    def _render_with_playwright(
        self,
        sample_id: str,
        blocks: Sequence[TextBlock],
        rng: random.Random,
    ) -> RenderResult:
        from playwright.sync_api import sync_playwright

        layout = self._game_layout(blocks, rng)
        html_doc = self._html_for_layout(layout)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": self.width, "height": self.height}, device_scale_factor=1)
            page.set_content(html_doc, wait_until="networkidle")
            boxes = page.evaluate(
                """
                () => {
                  const root = document.querySelector('#scene').getBoundingClientRect();
                  return [...document.querySelectorAll('.line')].map((el) => {
                    const r = el.getBoundingClientRect();
                    return [
                      Math.round(r.left - root.left),
                      Math.round(r.top - root.top),
                      Math.round(r.right - root.left),
                      Math.round(r.bottom - root.top)
                    ];
                  });
                }
                """
            )
            png = page.screenshot(type="png")
            browser.close()

        image = Image.open(io.BytesIO(png)).convert("RGB")
        lines = self._annotations_from_layout(layout, boxes)
        metadata = {
            "renderer": "game_playwright",
            "template": "html_css_game_ui_v1",
            "asset_provenance": "procedural/licensed-by-construction",
            "sample_id": sample_id,
        }
        return RenderResult(image=image, sample=RenderedSample(self.width, self.height, lines, metadata))

    def _render_with_pillow(
        self,
        sample_id: str,
        blocks: Sequence[TextBlock],
        rng: random.Random,
    ) -> RenderResult:
        image = Image.new("RGB", (self.width, self.height), (30, 34, 44))
        draw = ImageDraw.Draw(image)
        self._draw_game_background(draw, rng)
        layout = self._game_layout(blocks, rng)
        lines: List[LineAnnotation] = []

        for item in layout:
            if item["box"]:
                rect = item["box"]
                draw.rounded_rectangle(rect, radius=8, fill=item["box_fill"], outline=item["box_outline"], width=2)
            font = load_font(item["font_size"], item["source_language"], bold=True)
            box = text_bbox(draw, (item["x"], item["y"]), item["text"], font)
            draw.text((item["x"], item["y"]), item["text"], font=font, fill=item["color"])
            lines.append(self._line_annotation(item, clamp_bbox(box, self.width, self.height), len(lines) + 1))

        metadata = {
            "renderer": "game_pillow",
            "template": "procedural_game_ui_v1",
            "asset_provenance": "procedural/licensed-by-construction",
            "sample_id": sample_id,
        }
        return RenderResult(image=image, sample=RenderedSample(self.width, self.height, lines, metadata))

    def _game_layout(self, blocks: Sequence[TextBlock], rng: random.Random) -> List[Dict[str, Any]]:
        layout: List[Dict[str, Any]] = []
        slots = [
            {"box": (32, 470, 608, 610), "x": 58, "y": 492, "font_size": 23, "color": (245, 246, 238)},
            {"box": (32, 40, 250, 154), "x": 54, "y": 62, "font_size": 21, "color": (255, 232, 166)},
            {"box": None, "x": 312, "y": 96, "font_size": 20, "color": (236, 236, 236)},
            {"box": None, "x": 412, "y": 238, "font_size": 19, "color": (210, 240, 255)},
            {"box": (382, 38, 604, 176), "x": 406, "y": 62, "font_size": 20, "color": (220, 255, 210)},
        ]
        for block, slot in zip(blocks, slots):
            font = load_font(slot["font_size"], block.source_language, bold=True)
            scratch = ImageDraw.Draw(Image.new("RGB", (self.width, self.height)))
            max_width = self.width - slot["x"] - 26 if slot["box"] is None else slot["box"][2] - slot["box"][0] - 44
            for line_number, visual_line in enumerate(wrap_text(scratch, block.text, font, max_width, max_lines=3)):
                layout.append(
                    {
                        "text": visual_line,
                        "translated_text": block.translated_text,
                        "source_language": block.source_language,
                        "kind": block.kind,
                        "group_id": block.group_id,
                        "x": slot["x"],
                        "y": slot["y"] + line_number * (slot["font_size"] + 7),
                        "font_size": slot["font_size"],
                        "color": slot["color"],
                        "box": slot["box"] if line_number == 0 else None,
                        "box_fill": (25, 33, 44),
                        "box_outline": (180, 200, 220),
                    }
                )
        return layout

    def _html_for_layout(self, layout: Sequence[Dict[str, Any]]) -> str:
        box_html = []
        line_html = []
        emitted_boxes = set()
        for idx, item in enumerate(layout):
            if item["box"] and item["box"] not in emitted_boxes:
                emitted_boxes.add(item["box"])
                x1, y1, x2, y2 = item["box"]
                box_html.append(
                    f"<div class='panel' style='left:{x1}px;top:{y1}px;width:{x2-x1}px;height:{y2-y1}px'></div>"
                )
            color = "rgb(%d,%d,%d)" % item["color"]
            line_html.append(
                "<span class='line' "
                f"data-idx='{idx}' "
                f"style='left:{item['x']}px;top:{item['y']}px;"
                f"font-size:{item['font_size']}px;color:{color}'>"
                f"{html.escape(item['text'])}</span>"
            )
        return f"""
        <!doctype html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            * {{ box-sizing: border-box; }}
            body {{ margin: 0; background: #111; }}
            #scene {{
              position: relative;
              width: {self.width}px;
              height: {self.height}px;
              overflow: hidden;
              background:
                radial-gradient(circle at 62% 42%, rgba(110,160,180,.35), transparent 24%),
                linear-gradient(145deg, #28364a 0%, #171d26 56%, #0f141b 100%);
              font-family: "Segoe UI", Arial, sans-serif;
            }}
            #scene:before {{
              content: "";
              position: absolute;
              inset: 0;
              background:
                linear-gradient(95deg, transparent 0 48%, rgba(255,255,255,.10) 49% 51%, transparent 52%),
                repeating-linear-gradient(0deg, rgba(255,255,255,.03) 0 2px, transparent 2px 7px);
            }}
            .panel {{
              position: absolute;
              border: 2px solid rgba(210,225,235,.88);
              background: rgba(16, 24, 36, .84);
              border-radius: 8px;
              box-shadow: 0 8px 24px rgba(0,0,0,.35);
            }}
            .line {{
              position: absolute;
              z-index: 2;
              font-weight: 700;
              line-height: 1.16;
              white-space: pre;
              text-shadow: 0 2px 2px rgba(0,0,0,.9), 0 0 5px rgba(0,0,0,.65);
            }}
          </style>
        </head>
        <body><div id="scene">{''.join(box_html)}{''.join(line_html)}</div></body>
        </html>
        """

    def _annotations_from_layout(self, layout: Sequence[Dict[str, Any]], boxes: Sequence[Sequence[int]]) -> List[LineAnnotation]:
        lines: List[LineAnnotation] = []
        for idx, (item, box) in enumerate(zip(layout, boxes), start=1):
            lines.append(self._line_annotation(item, clamp_bbox(box, self.width, self.height), idx))
        return lines

    def _line_annotation(self, item: Dict[str, Any], bbox: List[int], line_id: int) -> LineAnnotation:
        return LineAnnotation(
            id=line_id,
            group_id=item["group_id"],
            bbox_2d=bbox,
            text=item["text"],
            translated_text=item["translated_text"],
            source_language=item["source_language"],
            kind=item["kind"],
        )

    def _draw_game_background(self, draw: ImageDraw.ImageDraw, rng: random.Random) -> None:
        for y in range(self.height):
            ratio = y / self.height
            color = (
                int(28 + 18 * ratio),
                int(34 + 25 * ratio),
                int(46 + 36 * ratio),
            )
            draw.line((0, y, self.width, y), fill=color)
        horizon = rng.randint(270, 330)
        draw.polygon([(0, horizon), (140, 210), (310, horizon + 34), (640, 190), (640, 640), (0, 640)], fill=(36, 48, 58))
        for _ in range(18):
            x = rng.randint(0, self.width)
            y = rng.randint(70, 390)
            radius = rng.randint(12, 42)
            shade = rng.randint(60, 110)
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=(shade, shade + 8, shade + 12), width=2)
        for angle in range(-40, 60, 18):
            x = 320 + int(math.sin(math.radians(angle)) * 180)
            draw.line((320, 330, x, 620), fill=(58, 67, 74), width=3)
