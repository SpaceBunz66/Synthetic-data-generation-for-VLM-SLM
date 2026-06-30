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


Rect = Tuple[int, int, int, int]
NameplateEntry = Tuple[str, str, str, str]

GAME_NAMEPLATES: Tuple[NameplateEntry, ...] = (
    ("Officer Torlyun", "Officer Torlyun", "Recruiting Officer", "sĩ quan tuyển mộ"),
    ("Sentinel Dawnshadow", "Sentinel Dawnshadow", "Recruiting Officer", "sĩ quan tuyển mộ"),
    ("Shield Captain Chien", "Shield Captain Chien", "Local Supplier", "nhà cung cấp địa phương"),
    ("Trader Aranda", "Trader Aranda", "Local Supplier", "nhà cung cấp địa phương"),
    ("Captain Rhea", "Captain Rhea", "Quest Giver", "người giao nhiệm vụ"),
    ("Archivist Noll", "Archivist Noll", "Lorekeeper", "người giữ tri thức"),
    ("Merchant Vale", "Merchant Vale", "General Goods", "hàng hóa tổng hợp"),
    ("Scout Ilya", "Scout Ilya", "Pathfinder", "người dẫn đường"),
    ("Healer Orin", "Healer Orin", "Medic", "thầy thuốc"),
    ("Guard Toma", "Guard Toma", "City Watch", "lính gác thành phố"),
)

GAME_NAMEPLATE_TEXTS = tuple(
    text
    for name, _name_vi, title, _title_vi in GAME_NAMEPLATES
    for text in (name, f"<{title}>")
)


@dataclass(frozen=True)
class RenderResult:
    image: Image.Image
    sample: RenderedSample


class MangaRenderer:
    """Pillow renderer for original, license-safe manga-style pages."""

    width = 1024
    height = 1440

    def __init__(self, difficulty: str = "normal") -> None:
        if difficulty not in {"normal", "dense"}:
            raise ValueError("difficulty must be one of: normal, dense")
        self.difficulty = difficulty

    def render(self, sample_id: str, blocks: Sequence[TextBlock], rng: random.Random) -> RenderResult:
        image = Image.new("RGB", (self.width, self.height), "white")
        draw = ImageDraw.Draw(image)
        dense = self.difficulty == "dense"
        panel_layout, panel_rects, panel_noise = self._draw_dense_panels(draw, rng) if dense else self._draw_panels(draw, rng)
        lines: List[LineAnnotation] = []
        placed_bubbles: Dict[Rect, List[Rect]] = {panel: [] for panel in panel_rects}
        bubble_boxes: List[Rect] = []
        bubble_plan: List[Tuple[TextBlock, Rect]] = []

        for idx, block in enumerate(blocks):
            panel = panel_rects[idx % len(panel_rects)]
            existing = placed_bubbles[panel]
            if dense:
                bubble = self._dense_bubble_rect(panel, existing, rng)
            else:
                bubble = self._bubble_rect(panel, idx, len(panel_rects), rng, existing)
            existing.append(bubble)
            bubble_boxes.append(bubble)
            bubble_plan.append((block, bubble))

        art_rng = random.Random(f"{sample_id}:manga_art:{self.difficulty}:{panel_layout}")
        panel_art = self._draw_manga_panel_art(draw, panel_rects, placed_bubbles, art_rng, dense)
        if dense:
            self._draw_manga_dense_occlusion(draw, art_rng)

        for block, bubble in bubble_plan:
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
            "template": "synthetic_dense_panels_bubbles_v1" if dense else "synthetic_panels_bubbles_v1",
            "panel_layout": panel_layout,
            "panel_noise": panel_noise,
            "panel_art": panel_art,
            "bubble_count": len(bubble_boxes),
            "bubble_overlap_max": round(_max_overlap_ratio(bubble_boxes), 4),
            "asset_provenance": "procedural/licensed-by-construction",
            "sample_id": sample_id,
        }
        return RenderResult(
            image=image,
            sample=RenderedSample(self.width, self.height, lines, metadata),
        )

    def _draw_panels(self, draw: ImageDraw.ImageDraw, rng: random.Random) -> Tuple[str, List[Rect], Dict[str, Any]]:
        layouts: List[Tuple[str, List[Rect]]] = [
            (
                "wide_split_wide",
                [
                    (60, 45, 964, 385),
                    (60, 420, 493, 810),
                    (530, 420, 964, 810),
                    (60, 850, 964, 1370),
                ],
            ),
            (
                "left_tall_right_stack",
                [
                    (56, 48, 440, 720),
                    (476, 48, 966, 352),
                    (476, 386, 966, 720),
                    (58, 758, 966, 1372),
                ],
            ),
            (
                "top_pair_center_wide_bottom_pair",
                [
                    (58, 46, 486, 360),
                    (522, 46, 966, 360),
                    (58, 398, 966, 850),
                    (58, 888, 486, 1370),
                    (522, 888, 966, 1370),
                ],
            ),
            (
                "staircase_five",
                [
                    (58, 46, 590, 330),
                    (626, 46, 966, 520),
                    (58, 366, 590, 754),
                    (626, 556, 966, 944),
                    (58, 790, 590, 1370),
                    (626, 980, 966, 1370),
                ],
            ),
            (
                "three_row_mosaic",
                [
                    (58, 46, 966, 306),
                    (58, 344, 342, 784),
                    (378, 344, 650, 784),
                    (686, 344, 966, 784),
                    (58, 822, 512, 1370),
                    (548, 822, 966, 1370),
                ],
            ),
        ]
        layout_name, panels = rng.choice(layouts)
        noise_patterns: List[str] = []
        for i, rect in enumerate(panels):
            draw.rectangle(rect, fill=(248, 248, 248), outline=(0, 0, 0), width=5)
            self._draw_panel_texture(draw, rect, rng, density=12 + i * 3)
            noise_patterns.extend(self._draw_panel_noise(draw, rect, rng, dense=False))
        return layout_name, panels, _noise_metadata(noise_patterns, len(panels))

    def _draw_dense_panels(self, draw: ImageDraw.ImageDraw, rng: random.Random) -> Tuple[str, List[Rect], Dict[str, Any]]:
        layouts: List[Tuple[str, List[Rect]]] = [
            (
                "dense_two_column_grid_8",
                [
                    (46, 42, 488, 354),
                    (512, 42, 978, 354),
                    (46, 378, 488, 690),
                    (512, 378, 978, 690),
                    (46, 714, 488, 1026),
                    (512, 714, 978, 1026),
                    (46, 1050, 488, 1362),
                    (512, 1050, 978, 1362),
                ],
            ),
            (
                "dense_mosaic_7",
                [
                    (46, 42, 356, 390),
                    (380, 42, 978, 250),
                    (380, 274, 662, 622),
                    (686, 274, 978, 622),
                    (46, 414, 356, 866),
                    (380, 646, 978, 994),
                    (46, 890, 978, 1362),
                ],
            ),
            (
                "dense_vertical_strip_6",
                [
                    (46, 42, 314, 426),
                    (46, 450, 314, 834),
                    (46, 858, 314, 1362),
                    (338, 42, 978, 374),
                    (338, 398, 978, 842),
                    (338, 866, 978, 1362),
                ],
            ),
            (
                "dense_staggered_8",
                [
                    (46, 42, 520, 302),
                    (544, 42, 978, 430),
                    (46, 326, 294, 754),
                    (318, 326, 520, 754),
                    (544, 454, 978, 754),
                    (46, 778, 520, 1058),
                    (544, 778, 978, 1058),
                    (46, 1082, 978, 1362),
                ],
            ),
            (
                "dense_triptych_5",
                [
                    (46, 42, 978, 306),
                    (46, 330, 338, 954),
                    (362, 330, 662, 954),
                    (686, 330, 978, 954),
                    (46, 978, 978, 1362),
                ],
            ),
        ]
        layout_name, panels = rng.choice(layouts)
        noise_patterns: List[str] = []
        for rect in panels:
            fill = rng.randint(238, 250)
            draw.rectangle(rect, fill=(fill, fill, fill), outline=(0, 0, 0), width=5)
            self._draw_panel_texture(draw, rect, rng, density=rng.randint(7, 13))
            noise_patterns.extend(self._draw_panel_noise(draw, rect, rng, dense=True))
            if rng.random() < 0.45:
                self._draw_dense_speed_lines(draw, rect, rng)
        return layout_name, panels, _noise_metadata(noise_patterns, len(panels))

    def _draw_panel_texture(
        self,
        draw: ImageDraw.ImageDraw,
        rect: Rect,
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

    def _draw_panel_noise(
        self,
        draw: ImageDraw.ImageDraw,
        rect: Rect,
        rng: random.Random,
        dense: bool,
    ) -> List[str]:
        patterns = ["paper_grain", "edge_shadow"]
        x1, y1, x2, y2 = rect
        panel_w = x2 - x1
        panel_h = y2 - y1
        area = panel_w * panel_h

        grain_count = max(50, min(520 if dense else 320, area // (1300 if dense else 2200)))
        for _ in range(grain_count):
            x = rng.randint(x1 + 8, x2 - 8)
            y = rng.randint(y1 + 8, y2 - 8)
            shade = rng.randint(150, 238)
            if rng.random() < (0.18 if dense else 0.10):
                draw.line((x, y, x + rng.randint(-2, 2), y + rng.randint(-1, 2)), fill=(shade, shade, shade), width=1)
            else:
                draw.point((x, y), fill=(shade, shade, shade))

        if rng.random() < (0.72 if dense else 0.42):
            patterns.append("screentone")
            step = rng.randint(12, 20) if dense else rng.randint(18, 30)
            radius = 2 if dense and rng.random() < 0.45 else 1
            offset = rng.randint(0, step - 1)
            for y in range(y1 + 14 + offset, y2 - 14, step):
                row_shift = ((y - y1) // step) % 2 * (step // 2)
                for x in range(x1 + 14 + row_shift, x2 - 14, step):
                    if rng.random() < (0.72 if dense else 0.55):
                        shade = rng.randint(172, 214)
                        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(shade, shade, shade))

        if rng.random() < (0.62 if dense else 0.34):
            patterns.append("hatching")
            hatch_count = max(4, min(26 if dense else 14, area // (9000 if dense else 15000)))
            for _ in range(hatch_count):
                start_x = rng.randint(x1 + 10, x2 - 20)
                start_y = rng.randint(y1 + 10, y2 - 20)
                length = rng.randint(22, 90 if dense else 64)
                slope = rng.choice([-1, 1]) * rng.randint(4, 22)
                end_x = min(x2 - 8, start_x + length)
                end_y = max(y1 + 8, min(y2 - 8, start_y + slope))
                shade = rng.randint(145, 205)
                draw.line((start_x, start_y, end_x, end_y), fill=(shade, shade, shade), width=1)

        if rng.random() < (0.58 if dense else 0.32):
            patterns.append("dust_scratches")
            scratch_count = rng.randint(2, 8 if dense else 5)
            for _ in range(scratch_count):
                x = rng.randint(x1 + 12, x2 - 12)
                y = rng.randint(y1 + 12, y2 - 12)
                length = rng.randint(8, 42 if dense else 28)
                shade = rng.randint(120, 190)
                draw.line((x, y, min(x2 - 8, x + length), y + rng.randint(-3, 3)), fill=(shade, shade, shade), width=1)

        for inset in (6, 10, 14):
            shade = rng.randint(205, 232)
            draw.rectangle((x1 + inset, y1 + inset, x2 - inset, y2 - inset), outline=(shade, shade, shade), width=1)

        return patterns

    def _draw_manga_panel_art(
        self,
        draw: ImageDraw.ImageDraw,
        panels: Sequence[Rect],
        avoid_by_panel: Dict[Rect, Sequence[Rect]],
        rng: random.Random,
        dense: bool,
    ) -> Dict[str, Any]:
        art_styles = ["character_closeup", "two_shot", "environment", "object_focus", "action_silhouette"]
        offset = rng.randrange(len(art_styles))
        styles_used: List[str] = []
        art_boxes: List[Rect] = []
        max_bubble_overlap = 0.0
        color_clutter_count = 0
        color_palettes: List[str] = []

        for idx, panel in enumerate(panels):
            avoid = list(avoid_by_panel.get(panel, []))
            style = art_styles[(idx + offset) % len(art_styles)]
            if rng.random() < (0.24 if dense else 0.12):
                style = rng.choice(art_styles)

            art_rect = self._choose_panel_art_rect(panel, avoid, rng, dense)
            max_bubble_overlap = max(max_bubble_overlap, _max_overlap_with(art_rect, avoid))
            if style == "character_closeup":
                self._draw_manga_character_closeup(draw, art_rect, rng)
            elif style == "two_shot":
                self._draw_manga_two_shot(draw, art_rect, rng)
            elif style == "environment":
                self._draw_manga_environment(draw, art_rect, rng)
            elif style == "object_focus":
                self._draw_manga_object_focus(draw, art_rect, rng)
            else:
                self._draw_manga_action_silhouette(draw, art_rect, rng)

            styles_used.append(style)
            art_boxes.append(art_rect)
            if dense or rng.random() < 0.45:
                self._draw_manga_panel_props(draw, panel, avoid + [art_rect], rng, dense)
            clutter_count, palettes = self._draw_manga_color_clutter(draw, panel, avoid + [art_rect], rng, dense)
            color_clutter_count += clutter_count
            color_palettes.extend(palettes)

        return {
            "enabled": True,
            "art_count": len(art_boxes),
            "panel_count": len(panels),
            "styles": sorted(set(styles_used)),
            "color_clutter_count": color_clutter_count,
            "color_palettes": sorted(set(color_palettes)),
            "bubble_overlap_max": round(max_bubble_overlap, 4),
        }

    def _choose_panel_art_rect(
        self,
        panel: Rect,
        avoid: Sequence[Rect],
        rng: random.Random,
        dense: bool,
    ) -> Rect:
        x1, y1, x2, y2 = panel
        panel_w = x2 - x1
        panel_h = y2 - y1
        pad = 24 if dense else 30
        max_w = max(56, panel_w - pad * 2)
        max_h = max(70, panel_h - pad * 2)
        best_rect: Rect = _fit_rect_in_panel((x1 + pad, y1 + pad, x1 + pad + max_w, y1 + pad + max_h), panel, pad=18)
        best_score = float("inf")

        for attempt in range(96):
            crowded = len(avoid) >= 2 or attempt > 48
            width_low = 0.24 if crowded else 0.34
            width_high = 0.46 if crowded else (0.68 if dense else 0.62)
            height_low = 0.28 if crowded else 0.42
            height_high = 0.56 if crowded else 0.78
            width = min(max_w, max(54, int(panel_w * rng.uniform(width_low, width_high))))
            height = min(max_h, max(66, int(panel_h * rng.uniform(height_low, height_high))))

            anchors = [
                ((x1 + x2 - width) // 2, y2 - pad - height),
                (x1 + pad, y2 - pad - height),
                (x2 - pad - width, y2 - pad - height),
                ((x1 + x2 - width) // 2, (y1 + y2 - height) // 2),
                (x1 + pad, (y1 + y2 - height) // 2),
                (x2 - pad - width, (y1 + y2 - height) // 2),
                ((x1 + x2 - width) // 2, y1 + pad),
            ]
            if attempt < len(anchors):
                ax, ay = anchors[attempt]
            else:
                ax = rng.randint(x1 + 18, max(x1 + 18, x2 - width - 18))
                ay = rng.randint(y1 + 18, max(y1 + 18, y2 - height - 18))
            ax += rng.randint(-10, 10)
            ay += rng.randint(-10, 10)
            rect = _fit_rect_in_panel((ax, ay, ax + width, ay + height), panel, pad=18)
            overlap = _max_overlap_with(rect, avoid)
            area_bonus = _rect_area(rect) / max(1, panel_w * panel_h)
            score = overlap - area_bonus * 0.05
            if score < best_score:
                best_rect = rect
                best_score = score
            if overlap <= 0.015 and attempt >= 6:
                return rect

        return best_rect

    def _draw_manga_character_closeup(self, draw: ImageDraw.ImageDraw, rect: Rect, rng: random.Random) -> None:
        x1, y1, x2, y2 = rect
        w = x2 - x1
        h = y2 - y1
        cx = (x1 + x2) // 2 + rng.randint(-max(1, w // 12), max(1, w // 12))
        face_w = max(36, min(int(w * 0.58), int(h * 0.48), w - 24))
        face_h = max(48, min(int(h * 0.58), int(w * 0.72), h - 34))
        face_top = y1 + max(8, int(h * 0.12))
        face = (cx - face_w // 2, face_top, cx + face_w // 2, face_top + face_h)
        skin = rng.randint(218, 238)

        self._draw_manga_backdrop_lines(draw, rect, rng, count=8)
        draw.ellipse(face, fill=(skin, skin, skin), outline=(54, 54, 54), width=3)
        hair = rng.randint(42, 82)
        draw.pieslice(
            (face[0] - 8, face[1] - 24, face[2] + 8, face[1] + face_h // 2),
            start=180,
            end=360,
            fill=(hair, hair, hair),
            outline=(30, 30, 30),
        )
        for i in range(5):
            lock_x = face[0] + (i + 1) * face_w // 6 + rng.randint(-5, 5)
            draw.polygon(
                [
                    (lock_x - rng.randint(8, 18), face[1] + 4),
                    (lock_x + rng.randint(7, 16), face[1] + 4),
                    (lock_x + rng.randint(-10, 10), face[1] + rng.randint(face_h // 4, face_h // 2)),
                ],
                fill=(hair, hair, hair),
                outline=(34, 34, 34),
            )

        eye_y = face[1] + int(face_h * 0.48)
        eye_gap = max(16, face_w // 5)
        eye_w = max(11, face_w // 7)
        for ex in (cx - eye_gap, cx + eye_gap):
            draw.line((ex - eye_w, eye_y - 5, ex + eye_w, eye_y - 7), fill=(20, 20, 20), width=3)
            draw.ellipse((ex - eye_w // 2, eye_y - 2, ex + eye_w // 2, eye_y + 10), fill=(18, 18, 18))
            draw.ellipse((ex - 2, eye_y, ex + 2, eye_y + 4), fill=(235, 235, 235))
        draw.line((cx, eye_y + 12, cx - 5, eye_y + 34), fill=(72, 72, 72), width=2)
        draw.arc((cx - 22, eye_y + 40, cx + 22, eye_y + 62), start=12, end=168, fill=(46, 46, 46), width=2)

        shoulder_y = min(y2 - 14, face[3] - 6)
        shoulder_w = max(face_w, int(w * 0.72))
        draw.polygon(
            [
                (cx - shoulder_w // 2, shoulder_y),
                (cx + shoulder_w // 2, shoulder_y),
                (min(x2 - 8, cx + shoulder_w // 3), y2 - 8),
                (max(x1 + 8, cx - shoulder_w // 3), y2 - 8),
            ],
            fill=(rng.randint(150, 186), rng.randint(150, 186), rng.randint(150, 186)),
            outline=(48, 48, 48),
        )
        draw.line((cx - 18, shoulder_y + 14, cx, y2 - 10), fill=(74, 74, 74), width=2)
        draw.line((cx + 18, shoulder_y + 14, cx, y2 - 10), fill=(74, 74, 74), width=2)

    def _draw_manga_two_shot(self, draw: ImageDraw.ImageDraw, rect: Rect, rng: random.Random) -> None:
        x1, y1, x2, y2 = rect
        w = x2 - x1
        h = y2 - y1
        draw.rectangle((x1 + 8, y1 + 8, x2 - 8, y2 - 8), outline=(190, 190, 190), width=1)
        for _ in range(5):
            y = rng.randint(y1 + 14, max(y1 + 14, y2 - 20))
            draw.line((x1 + 12, y, x2 - 12, y + rng.randint(-8, 8)), fill=(180, 180, 180), width=1)
        base = y2 - 12
        scale = max(0.34, min(1.35, min(w / 260, h / 210)))
        self._draw_manga_bust(draw, x1 + w // 3, base, scale, rng, facing=1)
        self._draw_manga_bust(draw, x1 + (w * 2) // 3, base - rng.randint(0, max(1, h // 12)), scale * rng.uniform(0.9, 1.08), rng, facing=-1)
        table_y = y2 - max(18, h // 7)
        draw.polygon(
            [(x1 + 16, table_y), (x2 - 16, table_y), (x2 - 4, y2 - 4), (x1 + 4, y2 - 4)],
            fill=(198, 198, 198),
            outline=(86, 86, 86),
        )

    def _draw_manga_environment(self, draw: ImageDraw.ImageDraw, rect: Rect, rng: random.Random) -> None:
        x1, y1, x2, y2 = rect
        w = x2 - x1
        h = y2 - y1
        horizon = y1 + int(h * rng.uniform(0.42, 0.58))
        draw.rectangle(rect, outline=(92, 92, 92), width=2)
        draw.rectangle((x1 + 12, y1 + 10, x2 - 12, horizon), fill=(228, 228, 228), outline=(102, 102, 102), width=2)
        for x in range(x1 + 26, x2 - 16, max(44, w // 4)):
            draw.line((x, y1 + 12, x, horizon - 2), fill=(116, 116, 116), width=2)
        for y in range(y1 + 34, horizon - 4, max(28, h // 7)):
            draw.line((x1 + 12, y, x2 - 12, y), fill=(138, 138, 138), width=1)
        for _ in range(5):
            cloud_x = rng.randint(x1 + 24, max(x1 + 24, x2 - 60))
            cloud_y = rng.randint(y1 + 18, max(y1 + 18, horizon - 34))
            draw.ellipse((cloud_x, cloud_y, cloud_x + 42, cloud_y + 16), outline=(164, 164, 164), width=1)

        draw.polygon([(x1 + 8, horizon), (x2 - 8, horizon), (x2 - 4, y2 - 6), (x1 + 4, y2 - 6)], fill=(214, 214, 214), outline=(120, 120, 120))
        vanishing_x = rng.randint(x1 + w // 3, x1 + (w * 2) // 3)
        for x in range(x1 + 16, x2 - 8, max(28, w // 5)):
            draw.line((x, y2 - 6, vanishing_x, horizon), fill=(154, 154, 154), width=1)
        for i in range(4):
            shelf_y = horizon + 20 + i * max(18, h // 12)
            if shelf_y >= y2 - 24:
                break
            draw.line((x1 + 18, shelf_y, x2 - 18, shelf_y), fill=(102, 102, 102), width=2)
            for x in range(x1 + 22, x2 - 30, max(26, w // 8)):
                shade = rng.randint(128, 186)
                draw.rectangle((x, shelf_y - rng.randint(12, 22), x + rng.randint(10, 22), shelf_y), fill=(shade, shade, shade), outline=(82, 82, 82))

    def _draw_manga_object_focus(self, draw: ImageDraw.ImageDraw, rect: Rect, rng: random.Random) -> None:
        x1, y1, x2, y2 = rect
        w = x2 - x1
        h = y2 - y1
        cx = (x1 + x2) // 2
        cy = y1 + int(h * 0.54)
        self._draw_manga_backdrop_lines(draw, rect, rng, count=10)
        table_y = y1 + int(h * 0.68)
        draw.polygon([(x1 + 8, table_y), (x2 - 8, table_y), (x2 - 2, y2 - 4), (x1 + 2, y2 - 4)], fill=(208, 208, 208), outline=(96, 96, 96))

        item = rng.choice(["open_book", "pendant", "letter"])
        if item == "open_book":
            book_w = max(68, int(w * 0.48))
            book_h = max(42, int(h * 0.22))
            left_page = (cx - book_w // 2, cy - book_h // 2, cx, cy + book_h // 2)
            right_page = (cx, cy - book_h // 2, cx + book_w // 2, cy + book_h // 2)
            draw.polygon([(left_page[0], left_page[1]), (left_page[2], left_page[1] + 8), (left_page[2], left_page[3]), (left_page[0], left_page[3] - 8)], fill=(238, 238, 238), outline=(62, 62, 62))
            draw.polygon([(right_page[0], right_page[1] + 8), (right_page[2], right_page[1]), (right_page[2], right_page[3] - 8), (right_page[0], right_page[3])], fill=(238, 238, 238), outline=(62, 62, 62))
            for y in range(cy - book_h // 3, cy + book_h // 3, max(7, book_h // 5)):
                draw.line((left_page[0] + 10, y, left_page[2] - 8, y + rng.randint(-2, 2)), fill=(128, 128, 128), width=1)
                draw.line((right_page[0] + 8, y + rng.randint(-2, 2), right_page[2] - 10, y), fill=(128, 128, 128), width=1)
        elif item == "pendant":
            radius = max(18, min(w, h) // 9)
            draw.line((cx, y1 + 22, cx - radius, cy - radius), fill=(64, 64, 64), width=2)
            draw.line((cx, y1 + 22, cx + radius, cy - radius), fill=(64, 64, 64), width=2)
            draw.polygon(
                [(cx, cy - radius), (cx + radius, cy), (cx, cy + radius), (cx - radius, cy)],
                fill=(214, 214, 214),
                outline=(40, 40, 40),
            )
            draw.line((cx - radius // 2, cy, cx + radius // 2, cy), fill=(118, 118, 118), width=2)
        else:
            letter_w = max(74, int(w * 0.42))
            letter_h = max(46, int(h * 0.24))
            letter = (cx - letter_w // 2, cy - letter_h // 2, cx + letter_w // 2, cy + letter_h // 2)
            draw.rectangle(letter, fill=(242, 242, 242), outline=(58, 58, 58), width=2)
            draw.line((letter[0], letter[1], cx, cy, letter[2], letter[1]), fill=(88, 88, 88), width=1)
            draw.line((letter[0], letter[3], cx, cy, letter[2], letter[3]), fill=(142, 142, 142), width=1)

        hand_y = table_y - max(8, h // 20)
        draw.ellipse((x1 + max(12, w // 9), hand_y - 18, x1 + max(42, w // 4), hand_y + 16), fill=(224, 224, 224), outline=(82, 82, 82))
        draw.ellipse((x2 - max(42, w // 4), hand_y - 18, x2 - max(12, w // 9), hand_y + 16), fill=(224, 224, 224), outline=(82, 82, 82))

    def _draw_manga_action_silhouette(self, draw: ImageDraw.ImageDraw, rect: Rect, rng: random.Random) -> None:
        x1, y1, x2, y2 = rect
        w = x2 - x1
        h = y2 - y1
        cx = (x1 + x2) // 2 + rng.randint(-max(1, w // 10), max(1, w // 10))
        base = y2 - max(10, h // 12)
        for _ in range(18):
            sx = rng.choice([x1 + 6, x2 - 6, rng.randint(x1 + 6, x2 - 6)])
            sy = rng.randint(y1 + 6, y2 - 6)
            draw.line((sx, sy, cx, y1 + h // 2), fill=(rng.randint(150, 204),) * 3, width=1)
        head_r = max(8, min(int(min(w, h) * 0.09), max(8, h // 8)))
        body_h = max(24, min(int(h * 0.52), max(24, h - head_r * 2 - 14)))
        shade = rng.randint(38, 72)
        head = (cx - head_r, base - body_h - head_r * 2, cx + head_r, base - body_h)
        draw.ellipse(head, fill=(shade, shade, shade), outline=(16, 16, 16))
        torso_top = base - body_h
        torso_mid = base - body_h // 2
        draw.polygon(
            [(cx - head_r, torso_top), (cx + head_r, torso_top), (cx + head_r * 2, torso_mid), (cx, base - 8), (cx - head_r * 2, torso_mid)],
            fill=(shade + 16, shade + 16, shade + 16),
            outline=(22, 22, 22),
        )
        arm_span = max(34, w // 4)
        leg_span = max(28, w // 6)
        draw.line((cx - head_r, torso_mid, cx - arm_span, torso_mid + rng.randint(-28, 18)), fill=(24, 24, 24), width=5)
        draw.line((cx + head_r, torso_mid, cx + arm_span, torso_mid + rng.randint(-28, 18)), fill=(24, 24, 24), width=5)
        draw.line((cx, base - 8, cx - leg_span, base), fill=(24, 24, 24), width=6)
        draw.line((cx, base - 8, cx + leg_span, base - rng.randint(8, 28)), fill=(24, 24, 24), width=6)
        arc = (cx - w // 3, y1 + h // 5, cx + w // 3, y1 + h)
        draw.arc(arc, start=205, end=325, fill=(70, 70, 70), width=4)

    def _draw_manga_bust(
        self,
        draw: ImageDraw.ImageDraw,
        cx: int,
        base: int,
        scale: float,
        rng: random.Random,
        facing: int,
    ) -> None:
        head_r = max(9, int(26 * scale))
        body_w = max(28, int(72 * scale))
        body_h = max(34, int(88 * scale))
        face_top = base - body_h - head_r * 2
        shade = rng.randint(206, 232)
        draw.ellipse((cx - head_r, face_top, cx + head_r, face_top + head_r * 2), fill=(shade, shade, shade), outline=(52, 52, 52), width=2)
        hair = rng.randint(36, 82)
        draw.pieslice((cx - head_r - 4, face_top - 10, cx + head_r + 4, face_top + head_r + 8), 180, 360, fill=(hair, hair, hair), outline=(30, 30, 30))
        eye_y = face_top + head_r
        eye_shift = facing * max(2, head_r // 5)
        for ex in (cx - head_r // 3 + eye_shift, cx + head_r // 3 + eye_shift):
            draw.line((ex - 5, eye_y, ex + 5, eye_y - 1), fill=(22, 22, 22), width=2)
        draw.line((cx + facing * 2, eye_y + 8, cx + facing * 7, eye_y + 18), fill=(82, 82, 82), width=1)
        draw.arc((cx - 10 + facing * 3, eye_y + 20, cx + 12 + facing * 3, eye_y + 34), start=15, end=165, fill=(48, 48, 48), width=1)
        draw.polygon(
            [
                (cx - body_w // 2, base - body_h),
                (cx + body_w // 2, base - body_h),
                (cx + body_w // 3, base),
                (cx - body_w // 3, base),
            ],
            fill=(rng.randint(142, 182), rng.randint(142, 182), rng.randint(142, 182)),
            outline=(62, 62, 62),
        )
        draw.line((cx, base - body_h + 8, cx - facing * body_w // 4, base - 8), fill=(86, 86, 86), width=2)

    def _draw_manga_panel_props(
        self,
        draw: ImageDraw.ImageDraw,
        panel: Rect,
        avoid: Sequence[Rect],
        rng: random.Random,
        dense: bool,
    ) -> None:
        count = rng.randint(2, 4) if dense else rng.randint(0, 2)
        for _ in range(count):
            prop = self._choose_small_panel_rect(panel, avoid, rng)
            if _max_overlap_with(prop, avoid) > 0.08:
                continue
            x1, y1, x2, y2 = prop
            shade = rng.randint(118, 206)
            shape = rng.choice(["spark", "frame", "debris", "plant"])
            if shape == "spark":
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2
                draw.line((cx, y1, cx, y2), fill=(shade, shade, shade), width=2)
                draw.line((x1, cy, x2, cy), fill=(shade, shade, shade), width=2)
                draw.line((x1 + 2, y1 + 2, x2 - 2, y2 - 2), fill=(shade, shade, shade), width=1)
                draw.line((x1 + 2, y2 - 2, x2 - 2, y1 + 2), fill=(shade, shade, shade), width=1)
            elif shape == "frame":
                draw.rectangle(prop, outline=(shade, shade, shade), width=2)
                draw.line((x1 + 4, y2 - 5, x1 + (x2 - x1) // 2, y1 + 5), fill=(shade, shade, shade), width=1)
                draw.line((x1 + (x2 - x1) // 2, y1 + 5, x2 - 4, y2 - 5), fill=(shade, shade, shade), width=1)
            elif shape == "plant":
                stem_x = (x1 + x2) // 2
                draw.line((stem_x, y2, stem_x, y1 + 4), fill=(shade, shade, shade), width=2)
                draw.ellipse((x1, y1 + 2, stem_x + 2, y1 + (y2 - y1) // 2), outline=(shade, shade, shade), width=2)
                draw.ellipse((stem_x - 2, y1 + (y2 - y1) // 3, x2, y2 - 4), outline=(shade, shade, shade), width=2)
            else:
                draw.polygon([(x1, y2), ((x1 + x2) // 2, y1), (x2, y2)], outline=(shade, shade, shade))

    def _draw_manga_color_clutter(
        self,
        draw: ImageDraw.ImageDraw,
        panel: Rect,
        avoid: Sequence[Rect],
        rng: random.Random,
        dense: bool,
    ) -> Tuple[int, List[str]]:
        palettes = {
            "marker": [(226, 64, 72), (255, 210, 80), (74, 164, 238), (78, 198, 116)],
            "neon": [(236, 82, 198), (64, 224, 218), (255, 126, 72), (160, 112, 240)],
            "poster": [(190, 52, 60), (42, 84, 156), (238, 190, 74), (54, 142, 92)],
            "pastel": [(236, 150, 158), (132, 198, 226), (238, 216, 126), (164, 210, 150)],
        }
        attempts = rng.randint(4, 8) if dense else rng.randint(1, 3)
        count = 0
        used_palettes: List[str] = []
        x1, y1, x2, y2 = panel

        for _ in range(attempts):
            palette_name = rng.choice(list(palettes))
            palette = palettes[palette_name]
            rect = self._choose_small_panel_rect(panel, avoid, rng)
            if _max_overlap_with(rect, avoid) > (0.05 if dense else 0.03):
                continue
            rx1, ry1, rx2, ry2 = rect
            color = rng.choice(palette)
            shape = rng.choice(["paint", "sticker", "tape", "confetti", "warning"])
            if shape == "paint":
                radius = max(8, min(rx2 - rx1, ry2 - ry1) // 2)
                cx = (rx1 + rx2) // 2
                cy = (ry1 + ry2) // 2
                draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=color, outline=(40, 40, 40))
                for _dot in range(3):
                    dx = rng.randint(-radius * 2, radius * 2)
                    dy = rng.randint(-radius, radius)
                    dot_r = rng.randint(2, 5)
                    px = max(x1 + 8, min(x2 - 8, cx + dx))
                    py = max(y1 + 8, min(y2 - 8, cy + dy))
                    draw.ellipse((px - dot_r, py - dot_r, px + dot_r, py + dot_r), fill=color)
            elif shape == "sticker":
                draw.rounded_rectangle(rect, radius=6, fill=color, outline=(35, 35, 35), width=2)
                draw.line((rx1 + 5, ry1 + 5, rx2 - 5, ry2 - 5), fill=(255, 255, 255), width=2)
                draw.line((rx1 + 5, ry2 - 5, rx2 - 5, ry1 + 5), fill=(255, 255, 255), width=1)
            elif shape == "tape":
                strip_h = max(8, (ry2 - ry1) // 3)
                y = (ry1 + ry2 - strip_h) // 2
                draw.rectangle((rx1, y, rx2, y + strip_h), fill=color, outline=(54, 54, 54))
                for x in range(rx1 + 4, rx2, 10):
                    draw.line((x, y, x + 4, y + strip_h), fill=(255, 255, 255), width=1)
            elif shape == "warning":
                draw.polygon([(rx1, ry2), ((rx1 + rx2) // 2, ry1), (rx2, ry2)], fill=color, outline=(40, 40, 40))
                cx = (rx1 + rx2) // 2
                draw.line((cx, ry1 + 8, cx, ry2 - 10), fill=(20, 20, 20), width=2)
                draw.ellipse((cx - 2, ry2 - 7, cx + 2, ry2 - 3), fill=(20, 20, 20))
            else:
                for _piece in range(rng.randint(4, 8)):
                    px = rng.randint(rx1, max(rx1, rx2 - 4))
                    py = rng.randint(ry1, max(ry1, ry2 - 4))
                    draw.rectangle((px, py, px + rng.randint(3, 8), py + rng.randint(3, 8)), fill=rng.choice(palette))
            count += 1
            used_palettes.append(palette_name)

        return count, used_palettes

    def _choose_small_panel_rect(self, panel: Rect, avoid: Sequence[Rect], rng: random.Random) -> Rect:
        x1, y1, x2, y2 = panel
        panel_w = x2 - x1
        panel_h = y2 - y1
        best_rect = (x1 + 22, y1 + 22, x1 + 58, y1 + 58)
        best_overlap = float("inf")
        for _ in range(36):
            width = rng.randint(24, max(28, min(70, panel_w // 5)))
            height = rng.randint(20, max(24, min(64, panel_h // 5)))
            px = rng.randint(x1 + 18, max(x1 + 18, x2 - width - 18))
            py = rng.randint(y1 + 18, max(y1 + 18, y2 - height - 18))
            rect = _fit_rect_in_panel((px, py, px + width, py + height), panel, pad=14)
            overlap = _max_overlap_with(rect, avoid)
            if overlap < best_overlap:
                best_rect = rect
                best_overlap = overlap
            if overlap <= 0.02:
                break
        return best_rect

    def _draw_manga_backdrop_lines(
        self,
        draw: ImageDraw.ImageDraw,
        rect: Rect,
        rng: random.Random,
        count: int,
    ) -> None:
        x1, y1, x2, y2 = rect
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        for _ in range(count):
            edge = rng.choice(["left", "right", "top"])
            if edge == "left":
                sx, sy = x1 + 4, rng.randint(y1 + 4, y2 - 4)
            elif edge == "right":
                sx, sy = x2 - 4, rng.randint(y1 + 4, y2 - 4)
            else:
                sx, sy = rng.randint(x1 + 4, x2 - 4), y1 + 4
            draw.line((sx, sy, cx + rng.randint(-10, 10), cy + rng.randint(-10, 10)), fill=(rng.randint(164, 214),) * 3, width=1)

    def _draw_dense_speed_lines(self, draw: ImageDraw.ImageDraw, rect: Rect, rng: random.Random) -> None:
        x1, y1, x2, y2 = rect
        origin_x = rng.choice([x1 + 12, x2 - 12])
        origin_y = rng.randint(y1 + 20, y2 - 20)
        for _ in range(rng.randint(12, 22)):
            target_x = rng.randint(x1 + 10, x2 - 10)
            target_y = rng.randint(y1 + 10, y2 - 10)
            shade = rng.randint(165, 215)
            draw.line((origin_x, origin_y, target_x, target_y), fill=(shade, shade, shade), width=1)

    def _bubble_rect(
        self,
        panel: Rect,
        idx: int,
        panel_count: int,
        rng: random.Random,
        existing: Sequence[Rect] | None = None,
    ) -> Rect:
        x1, y1, x2, y2 = panel
        panel_w = x2 - x1
        panel_h = y2 - y1
        bw_min = min(max(180, panel_w // 4), max(120, panel_w - 64))
        bw_max = max(bw_min, min(max(240, panel_w // 2), max(130, panel_w - 44)))
        bh_min = min(130, max(90, panel_h - 70))
        bh_max = max(bh_min, min(230, max(120, panel_h - 56)))
        bw = rng.randint(bw_min, bw_max)
        bh = rng.randint(bh_min, bh_max)
        zones = [
            (x1 + 28, y1 + 28),
            (x2 - bw - 28, y1 + 38),
            (x1 + 32, y2 - bh - 38),
            (x2 - bw - 34, y2 - bh - 34),
        ]
        zone_index = (idx + idx // panel_count) % len(zones)
        existing = list(existing or [])
        best_rect: Rect | None = None
        best_overlap = float("inf")

        for attempt in range(32 if existing else 1):
            if attempt < len(zones):
                bx, by = zones[(zone_index + attempt) % len(zones)]
            else:
                bx = rng.randint(x1 + 22, max(x1 + 22, x2 - bw - 22))
                by = rng.randint(y1 + 22, max(y1 + 22, y2 - bh - 22))
            bx += rng.randint(-12, 12)
            by += rng.randint(-10, 10)
            rect = _fit_rect_in_panel((bx, by, bx + bw, by + bh), panel)
            overlap = _max_overlap_with(rect, existing)
            if overlap < best_overlap:
                best_rect = rect
                best_overlap = overlap
            if overlap <= 0.12:
                return rect
        return best_rect or _fit_rect_in_panel((x1 + 28, y1 + 28, x1 + 28 + bw, y1 + 28 + bh), panel)

    def _dense_bubble_rect(self, panel: Rect, existing: Sequence[Rect], rng: random.Random) -> Rect:
        x1, y1, x2, y2 = panel
        panel_w = x2 - x1
        panel_h = y2 - y1
        crowded = len(existing) >= 2
        max_w = max(122, min(panel_w - 36, panel_w // 2 + (0 if existing else 44)))
        max_h = max(78, min(panel_h - 36, panel_h // 2 + (0 if existing else 28)))
        if crowded:
            max_w = max(112, min(max_w, panel_w // 2 - 14))
            max_h = max(72, min(max_h, panel_h // 2 - 14))
        min_w = min(max_w, max(104, panel_w // 4))
        min_h = min(max_h, max(68, panel_h // 4))

        best_rect: Rect | None = None
        best_overlap = float("inf")
        for attempt in range(72):
            bw = rng.randint(min_w, max_w)
            bh = rng.randint(min_h, max_h)
            positions = [
                (x1 + 18, y1 + 18),
                (x2 - bw - 18, y1 + 18),
                (x1 + 18, y2 - bh - 18),
                (x2 - bw - 18, y2 - bh - 18),
                ((x1 + x2 - bw) // 2, y1 + 18),
                ((x1 + x2 - bw) // 2, y2 - bh - 18),
                (x1 + 18, (y1 + y2 - bh) // 2),
                (x2 - bw - 18, (y1 + y2 - bh) // 2),
            ]
            if attempt < len(positions):
                bx, by = positions[attempt]
            else:
                left_max = max(x1 + 18, x2 - bw - 18)
                top_max = max(y1 + 18, y2 - bh - 18)
                bx = rng.randint(x1 + 18, left_max)
                by = rng.randint(y1 + 18, top_max)
            rect = _fit_rect_in_panel((bx, by, bx + bw, by + bh), panel)
            overlap = _max_overlap_with(rect, existing)
            if overlap < best_overlap:
                best_rect = rect
                best_overlap = overlap
            if overlap <= 0.18:
                return rect
        return best_rect or _fit_rect_in_panel((x1 + 24, y1 + 24, x1 + 24 + max_w, y1 + 24 + max_h), panel)

    def _fit_bubble_text(
        self,
        draw: ImageDraw.ImageDraw,
        bubble: Rect,
        block: TextBlock,
        rng: random.Random,
    ) -> Tuple[Any, int, List[str], int]:
        max_width = max(60, bubble[2] - bubble[0] - 48)
        max_height = max(50, bubble[3] - bubble[1] - 36)
        if self.difficulty == "dense":
            start_size = rng.randint(21, 31)
        else:
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
        rect: Rect,
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

    def _draw_manga_dense_occlusion(self, draw: ImageDraw.ImageDraw, rng: random.Random) -> None:
        for _ in range(rng.randint(5, 9)):
            x = rng.randint(40, self.width - 40)
            y1 = rng.randint(30, self.height - 160)
            y2 = y1 + rng.randint(60, 180)
            shade = rng.randint(218, 238)
            draw.line((x, y1, x + rng.randint(-36, 36), y2), fill=(shade, shade, shade), width=rng.randint(1, 3))


class GameRenderer:
    """HTML/Playwright renderer with Pillow fallback."""

    width = 640
    height = 640

    def __init__(self, mode: str = "auto", difficulty: str = "normal") -> None:
        if mode not in {"auto", "playwright", "pillow"}:
            raise ValueError("mode must be one of: auto, playwright, pillow")
        if difficulty not in {"normal", "dense"}:
            raise ValueError("difficulty must be one of: normal, dense")
        self.mode = mode
        self.difficulty = difficulty

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
        scene_style = str(layout[0].get("scene_style", "hud_overlay")) if layout else "hud_overlay"
        scene_variant = str(layout[0].get("scene_variant", scene_style)) if layout else scene_style
        metadata = {
            "renderer": "game_playwright",
            "template": "html_css_dense_game_ui_v1" if self.difficulty == "dense" else "html_css_game_ui_v1",
            "scene_style": scene_style,
            "scene_variant": scene_variant,
            "scene_actor_count": self._scene_actor_count(scene_style),
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
        scene_style = str(layout[0].get("scene_style", "hud_overlay")) if layout else "hud_overlay"
        scene_variant = str(layout[0].get("scene_variant", scene_style)) if layout else scene_style
        if self.difficulty == "dense":
            self._draw_dense_game_clutter(draw, rng, scene_style)
        else:
            self._draw_normal_game_clutter(draw, rng, scene_style)
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
            "template": "procedural_dense_game_ui_v1" if self.difficulty == "dense" else "procedural_game_ui_v1",
            "scene_style": scene_style,
            "scene_variant": scene_variant,
            "scene_actor_count": self._scene_actor_count(scene_style),
            "asset_provenance": "procedural/licensed-by-construction",
            "sample_id": sample_id,
        }
        return RenderResult(image=image, sample=RenderedSample(self.width, self.height, lines, metadata))

    def _game_layout(self, blocks: Sequence[TextBlock], rng: random.Random) -> List[Dict[str, Any]]:
        if self.difficulty == "dense":
            return self._dense_game_layout(blocks, rng)
        return self._normal_game_layout(blocks, rng)

    def _normal_game_layout(self, blocks: Sequence[TextBlock], rng: random.Random) -> List[Dict[str, Any]]:
        style = rng.choice(["dialogue_scene", "nameplate_scene", "hud_overlay"])
        if style == "dialogue_scene":
            slots = [
                {"box": (34, 404, 606, 504), "x": 58, "y": 428, "font_size": 20, "color": (255, 240, 180), "max_lines": 2, "box_fill": (8, 10, 14), "box_outline": (230, 230, 220)},
                {"box": None, "x": 214, "y": 238, "font_size": 19, "color": (70, 255, 72), "max_lines": 1, "nameplate_role": "name", "nameplate_id": 0},
                {"box": None, "x": 366, "y": 184, "font_size": 17, "color": (70, 255, 72), "max_lines": 1, "nameplate_role": "name", "nameplate_id": 1},
                {"box": (44, 38, 212, 104), "x": 62, "y": 58, "font_size": 16, "color": (245, 246, 238), "max_lines": 1},
                {"box": None, "x": 420, "y": 548, "font_size": 17, "color": (230, 244, 255), "max_lines": 1},
            ]
        elif style == "nameplate_scene":
            slots = [
                {"box": None, "x": 46, "y": 230, "font_size": 20, "color": (38, 255, 52), "max_lines": 1, "nameplate_role": "name", "nameplate_id": 0},
                {"box": None, "x": 40, "y": 260, "font_size": 18, "color": (38, 255, 52), "max_lines": 1, "nameplate_role": "title", "nameplate_id": 0},
                {"box": None, "x": 260, "y": 170, "font_size": 18, "color": (38, 255, 52), "max_lines": 1, "nameplate_role": "name", "nameplate_id": 1},
                {"box": None, "x": 428, "y": 204, "font_size": 16, "color": (38, 255, 52), "max_lines": 1, "nameplate_role": "name", "nameplate_id": 2},
                {"box": (394, 466, 614, 572), "x": 416, "y": 488, "font_size": 17, "color": (255, 232, 166), "max_lines": 1},
            ]
        else:
            slots = [
                {"box": (32, 470, 608, 610), "x": 58, "y": 492, "font_size": 23, "color": (245, 246, 238)},
                {"box": (32, 40, 250, 154), "x": 54, "y": 62, "font_size": 21, "color": (255, 232, 166)},
                {"box": None, "x": 312, "y": 96, "font_size": 20, "color": (236, 236, 236)},
                {"box": None, "x": 412, "y": 238, "font_size": 19, "color": (210, 240, 255)},
                {"box": (382, 38, 604, 176), "x": 406, "y": 62, "font_size": 20, "color": (220, 255, 210)},
            ]
        for slot in slots:
            slot["scene_style"] = style
        return self._layout_from_slots(blocks, slots, rng)

    def _dense_game_layout(self, blocks: Sequence[TextBlock], rng: random.Random) -> List[Dict[str, Any]]:
        slots = self._dense_game_slots(len(blocks), rng)
        return self._layout_from_slots(blocks, slots, rng)

    def _layout_from_slots(
        self,
        blocks: Sequence[TextBlock],
        slots: Sequence[Dict[str, Any]],
        rng: random.Random,
    ) -> List[Dict[str, Any]]:
        layout: List[Dict[str, Any]] = []
        emitted_boxes: set[Rect] = set()
        nameplates: Dict[int, NameplateEntry] = {}
        for idx, block in enumerate(blocks):
            if idx >= len(slots):
                break
            slot = slots[idx]
            text, translated_text, kind = self._slot_text(slot, block, rng, nameplates)
            font = load_font(slot["font_size"], block.source_language, bold=True)
            scratch = ImageDraw.Draw(Image.new("RGB", (self.width, self.height)))
            max_width = self.width - slot["x"] - 26 if slot["box"] is None else slot["box"][2] - slot["box"][0] - 44
            box = slot["box"]
            for line_number, visual_line in enumerate(
                wrap_text(scratch, text, font, max_width, max_lines=int(slot.get("max_lines", 3)))
            ):
                item_box = None
                if line_number == 0 and box and slot.get("draw_box", True) and box not in emitted_boxes:
                    item_box = box
                    emitted_boxes.add(box)
                layout.append(
                    {
                        "text": visual_line,
                        "translated_text": translated_text,
                        "source_language": block.source_language,
                        "kind": kind,
                        "group_id": block.group_id,
                        "x": slot["x"],
                        "y": slot["y"] + line_number * (slot["font_size"] + 7),
                        "font_size": slot["font_size"],
                        "color": slot["color"],
                        "box": item_box,
                        "box_fill": slot.get("box_fill", (25, 33, 44)),
                        "box_outline": slot.get("box_outline", (180, 200, 220)),
                        "scene_style": slot.get("scene_style", "hud_overlay"),
                        "scene_variant": slot.get("scene_variant", slot.get("scene_style", "hud_overlay")),
                    }
                )
        return layout

    def _slot_text(
        self,
        slot: Dict[str, Any],
        block: TextBlock,
        rng: random.Random,
        nameplates: Dict[int, NameplateEntry],
    ) -> Tuple[str, str, str]:
        role = slot.get("nameplate_role")
        if role:
            nameplate_id = int(slot.get("nameplate_id", 0))
            if nameplate_id not in nameplates:
                nameplates[nameplate_id] = rng.choice(GAME_NAMEPLATES)
            name, name_vi, title, title_vi = nameplates[nameplate_id]
            if role == "title":
                return f"<{title}>", f"<{title_vi}>", "floating_label"
            return name, name_vi, "floating_label"
        return block.text, block.translated_text, block.kind

    def _dense_game_slots(self, block_count: int, rng: random.Random) -> List[Dict[str, Any]]:
        style = rng.choice(
            [
                "dialogue_scene",
                "nameplate_scene",
                "crafting_menu",
                "hud_overlay",
                "battle_arena",
                "vendor_shop",
                "map_screen",
                "party_status",
            ]
        )
        if style == "dialogue_scene":
            slots = self._dense_dialogue_slots(block_count, rng)
        elif style == "nameplate_scene":
            slots = self._dense_nameplate_slots(block_count, rng)
        elif style == "crafting_menu":
            slots = self._dense_crafting_slots(block_count, rng)
        elif style == "battle_arena":
            slots = self._dense_battle_slots(block_count, rng)
        elif style == "vendor_shop":
            slots = self._dense_vendor_slots(block_count, rng)
        elif style == "map_screen":
            slots = self._dense_map_slots(block_count, rng)
        elif style == "party_status":
            slots = self._dense_party_slots(block_count, rng)
        else:
            slots = self._dense_hud_slots(block_count, rng)
        scene_variant = f"{style}_{rng.choice(['a', 'b', 'c'])}"
        self._jitter_dense_slots(slots, rng)
        for slot in slots:
            slot["scene_style"] = style
            slot["scene_variant"] = scene_variant
        return slots

    def _dense_hud_slots(self, block_count: int, rng: random.Random) -> List[Dict[str, Any]]:
        panel_fill = (22, 30, 42)
        warm_fill = (42, 34, 26)
        slots: List[Dict[str, Any]] = [
            {"box": (26, 464, 614, 620), "x": 48, "y": 486, "font_size": 19, "color": (245, 246, 238), "max_lines": 1, "box_fill": panel_fill},
            {"box": (26, 464, 614, 620), "x": 48, "y": 518, "font_size": 19, "color": (242, 220, 158), "max_lines": 1, "box_fill": panel_fill},
            {"box": (26, 464, 614, 620), "x": 48, "y": 550, "font_size": 18, "color": (210, 238, 255), "max_lines": 1, "box_fill": panel_fill},
            {"box": (28, 34, 258, 162), "x": 50, "y": 54, "font_size": 17, "color": (255, 232, 166), "max_lines": 1, "box_fill": warm_fill},
            {"box": (28, 34, 258, 162), "x": 50, "y": 84, "font_size": 17, "color": (220, 255, 210), "max_lines": 1, "box_fill": warm_fill},
            {"box": (354, 34, 614, 180), "x": 376, "y": 54, "font_size": 16, "color": (230, 244, 255), "max_lines": 1, "box_fill": panel_fill},
            {"box": (354, 34, 614, 180), "x": 376, "y": 84, "font_size": 16, "color": (210, 240, 255), "max_lines": 1, "box_fill": panel_fill},
            {"box": (354, 34, 614, 180), "x": 376, "y": 114, "font_size": 16, "color": (220, 255, 210), "max_lines": 1, "box_fill": panel_fill},
            {"box": (32, 194, 274, 342), "x": 54, "y": 214, "font_size": 17, "color": (248, 236, 198), "max_lines": 1, "box_fill": (32, 33, 50)},
            {"box": (32, 194, 274, 342), "x": 54, "y": 244, "font_size": 17, "color": (230, 242, 255), "max_lines": 1, "box_fill": (32, 33, 50)},
            {"box": (366, 198, 612, 350), "x": 388, "y": 220, "font_size": 17, "color": (230, 255, 230), "max_lines": 1, "box_fill": (24, 42, 38)},
            {"box": (366, 198, 612, 350), "x": 388, "y": 250, "font_size": 17, "color": (255, 228, 178), "max_lines": 1, "box_fill": (24, 42, 38)},
            {"box": None, "x": 294, "y": 112, "font_size": 17, "color": (236, 236, 236), "max_lines": 1},
            {"box": None, "x": 292, "y": 368, "font_size": 17, "color": (210, 240, 255), "max_lines": 1},
            {"box": None, "x": 74, "y": 380, "font_size": 17, "color": (255, 242, 184), "max_lines": 1},
            {"box": None, "x": 444, "y": 392, "font_size": 16, "color": (238, 238, 238), "max_lines": 1},
        ]

        while len(slots) < block_count and len(slots) < 24:
            slots.append(
                {
                    "box": None,
                    "x": rng.randint(52, 470),
                    "y": rng.randint(70, 420),
                    "font_size": rng.randint(14, 17),
                    "color": rng.choice([(236, 236, 236), (210, 240, 255), (255, 232, 166), (220, 255, 210)]),
                    "max_lines": 1,
                }
            )
        return slots

    def _dense_dialogue_slots(self, block_count: int, rng: random.Random) -> List[Dict[str, Any]]:
        slots: List[Dict[str, Any]] = [
            {"box": (34, 402, 606, 508), "x": 58, "y": 426, "font_size": 19, "color": (255, 240, 180), "max_lines": 2, "box_fill": (8, 10, 14), "box_outline": (235, 235, 225)},
            {"box": (34, 402, 606, 508), "x": 58, "y": 458, "font_size": 19, "color": (255, 240, 180), "max_lines": 1, "box_fill": (8, 10, 14), "box_outline": (235, 235, 225)},
            {"box": None, "x": 218, "y": 236, "font_size": 18, "color": (44, 255, 50), "max_lines": 1, "nameplate_role": "name", "nameplate_id": 0},
            {"box": None, "x": 208, "y": 264, "font_size": 16, "color": (44, 255, 50), "max_lines": 1, "nameplate_role": "title", "nameplate_id": 0},
            {"box": None, "x": 392, "y": 178, "font_size": 16, "color": (44, 255, 50), "max_lines": 1, "nameplate_role": "name", "nameplate_id": 1},
            {"box": None, "x": 410, "y": 206, "font_size": 15, "color": (44, 255, 50), "max_lines": 1, "nameplate_role": "title", "nameplate_id": 1},
            {"box": (38, 42, 222, 112), "x": 58, "y": 62, "font_size": 16, "color": (245, 246, 238), "max_lines": 1, "box_fill": (16, 22, 30)},
            {"box": (432, 36, 606, 102), "x": 452, "y": 56, "font_size": 15, "color": (255, 232, 166), "max_lines": 1, "box_fill": (24, 22, 18)},
            {"box": None, "x": 74, "y": 552, "font_size": 16, "color": (230, 244, 255), "max_lines": 1},
            {"box": None, "x": 364, "y": 548, "font_size": 16, "color": (220, 255, 210), "max_lines": 1},
        ]
        while len(slots) < block_count and len(slots) < 18:
            slots.append(
                {
                    "box": None,
                    "x": rng.randint(46, 450),
                    "y": rng.randint(128, 358),
                    "font_size": rng.randint(14, 17),
                    "color": (44, 255, 50),
                    "max_lines": 1,
                    "nameplate_role": "name",
                    "nameplate_id": len(slots),
                }
            )
        return slots

    def _dense_nameplate_slots(self, block_count: int, rng: random.Random) -> List[Dict[str, Any]]:
        anchors = [(38, 232), (250, 166), (414, 204), (90, 382), (330, 356), (458, 318)]
        slots: List[Dict[str, Any]] = []
        for idx, (x, y) in enumerate(anchors):
            slots.append({"box": None, "x": x, "y": y, "font_size": 18 if idx < 3 else 16, "color": (38, 255, 52), "max_lines": 1, "nameplate_role": "name", "nameplate_id": idx})
            slots.append({"box": None, "x": max(18, x - 12), "y": y + 26, "font_size": 15, "color": (38, 255, 52), "max_lines": 1, "nameplate_role": "title", "nameplate_id": idx})
        slots.extend(
            [
                {"box": (38, 474, 602, 580), "x": 60, "y": 496, "font_size": 17, "color": (255, 238, 188), "max_lines": 1, "box_fill": (10, 12, 16), "box_outline": (215, 215, 205)},
                {"box": (38, 474, 602, 580), "x": 60, "y": 526, "font_size": 17, "color": (230, 244, 255), "max_lines": 1, "box_fill": (10, 12, 16), "box_outline": (215, 215, 205)},
            ]
        )
        while len(slots) < block_count and len(slots) < 20:
            slots.append(
                {
                    "box": None,
                    "x": rng.randint(36, 470),
                    "y": rng.randint(110, 420),
                    "font_size": rng.randint(14, 17),
                    "color": (38, 255, 52),
                    "max_lines": 1,
                    "nameplate_role": "name",
                    "nameplate_id": len(slots),
                }
            )
        return slots

    def _dense_crafting_slots(self, block_count: int, rng: random.Random) -> List[Dict[str, Any]]:
        left_panel = (26, 12, 298, 586)
        right_panel = (310, 12, 620, 586)
        slots: List[Dict[str, Any]] = [
            {"box": left_panel, "x": 56, "y": 18, "font_size": 13, "color": (190, 190, 185), "max_lines": 1, "box_fill": (18, 16, 14), "box_outline": (94, 94, 86)},
            {"box": left_panel, "x": 48, "y": 48, "font_size": 14, "color": (255, 204, 86), "max_lines": 1, "box_fill": (18, 16, 14), "box_outline": (94, 94, 86)},
            {"box": left_panel, "x": 68, "y": 78, "font_size": 15, "color": (235, 228, 204), "max_lines": 1, "box_fill": (18, 16, 14), "box_outline": (94, 94, 86)},
            {"box": left_panel, "x": 68, "y": 108, "font_size": 15, "color": (235, 228, 204), "max_lines": 1, "box_fill": (18, 16, 14), "box_outline": (94, 94, 86)},
            {"box": left_panel, "x": 68, "y": 138, "font_size": 15, "color": (235, 228, 204), "max_lines": 1, "box_fill": (18, 16, 14), "box_outline": (94, 94, 86)},
            {"box": left_panel, "x": 48, "y": 318, "font_size": 14, "color": (255, 204, 86), "max_lines": 1, "box_fill": (18, 16, 14), "box_outline": (94, 94, 86)},
            {"box": left_panel, "x": 68, "y": 352, "font_size": 15, "color": (235, 228, 204), "max_lines": 1, "box_fill": (18, 16, 14), "box_outline": (94, 94, 86)},
            {"box": left_panel, "x": 68, "y": 382, "font_size": 15, "color": (235, 228, 204), "max_lines": 1, "box_fill": (18, 16, 14), "box_outline": (94, 94, 86)},
            {"box": right_panel, "x": 394, "y": 34, "font_size": 16, "color": (218, 86, 255), "max_lines": 1, "box_fill": (28, 22, 18), "box_outline": (112, 106, 94)},
            {"box": right_panel, "x": 394, "y": 60, "font_size": 13, "color": (230, 210, 180), "max_lines": 1, "box_fill": (28, 22, 18), "box_outline": (112, 106, 94)},
            {"box": right_panel, "x": 354, "y": 114, "font_size": 16, "color": (255, 220, 108), "max_lines": 1, "box_fill": (28, 22, 18), "box_outline": (112, 106, 94)},
            {"box": right_panel, "x": 376, "y": 184, "font_size": 14, "color": (238, 232, 210), "max_lines": 1, "box_fill": (28, 22, 18), "box_outline": (112, 106, 94)},
            {"box": right_panel, "x": 376, "y": 250, "font_size": 14, "color": (238, 232, 210), "max_lines": 1, "box_fill": (28, 22, 18), "box_outline": (112, 106, 94)},
            {"box": right_panel, "x": 376, "y": 316, "font_size": 14, "color": (238, 232, 210), "max_lines": 1, "box_fill": (28, 22, 18), "box_outline": (112, 106, 94)},
            {"box": right_panel, "x": 338, "y": 516, "font_size": 13, "color": (220, 220, 204), "max_lines": 1, "box_fill": (28, 22, 18), "box_outline": (112, 106, 94)},
        ]
        while len(slots) < block_count and len(slots) < 22:
            x = rng.choice([68, 376, 394])
            y = rng.randint(420, 540) if x == 68 else rng.randint(92, 480)
            slots.append(
                {
                    "box": left_panel if x == 68 else right_panel,
                    "x": x,
                    "y": y,
                    "font_size": rng.randint(13, 15),
                    "color": rng.choice([(235, 228, 204), (255, 204, 86), (238, 232, 210)]),
                    "max_lines": 1,
                    "box_fill": (18, 16, 14) if x == 68 else (28, 22, 18),
                    "box_outline": (94, 94, 86) if x == 68 else (112, 106, 94),
                }
            )
        for slot in slots:
            slot["draw_box"] = False
        return slots

    def _dense_battle_slots(self, block_count: int, rng: random.Random) -> List[Dict[str, Any]]:
        slots: List[Dict[str, Any]] = [
            {"box": (70, 28, 570, 84), "x": 92, "y": 46, "font_size": 17, "color": (255, 210, 112), "max_lines": 1, "box_fill": (42, 18, 24), "box_outline": (218, 92, 72)},
            {"box": (38, 96, 226, 206), "x": 58, "y": 116, "font_size": 16, "color": (220, 255, 210), "max_lines": 1, "box_fill": (18, 34, 28)},
            {"box": (38, 96, 226, 206), "x": 58, "y": 146, "font_size": 16, "color": (178, 228, 255), "max_lines": 1, "box_fill": (18, 34, 28)},
            {"box": (38, 96, 226, 206), "x": 58, "y": 176, "font_size": 15, "color": (255, 232, 166), "max_lines": 1, "box_fill": (18, 34, 28)},
            {"box": (408, 92, 604, 210), "x": 430, "y": 112, "font_size": 16, "color": (255, 236, 184), "max_lines": 1, "box_fill": (34, 28, 18)},
            {"box": (408, 92, 604, 210), "x": 430, "y": 142, "font_size": 15, "color": (230, 244, 255), "max_lines": 1, "box_fill": (34, 28, 18)},
            {"box": (34, 468, 606, 612), "x": 58, "y": 492, "font_size": 18, "color": (245, 246, 238), "max_lines": 1, "box_fill": (10, 12, 18), "box_outline": (230, 210, 160)},
            {"box": (34, 468, 606, 612), "x": 58, "y": 524, "font_size": 18, "color": (255, 226, 142), "max_lines": 1, "box_fill": (10, 12, 18), "box_outline": (230, 210, 160)},
            {"box": (34, 468, 606, 612), "x": 58, "y": 556, "font_size": 17, "color": (190, 236, 255), "max_lines": 1, "box_fill": (10, 12, 18), "box_outline": (230, 210, 160)},
            {"box": None, "x": 254, "y": 284, "font_size": 18, "color": (255, 76, 76), "max_lines": 1},
            {"box": None, "x": 380, "y": 278, "font_size": 17, "color": (86, 255, 112), "max_lines": 1, "nameplate_role": "name", "nameplate_id": 0},
            {"box": None, "x": 146, "y": 322, "font_size": 17, "color": (86, 255, 112), "max_lines": 1, "nameplate_role": "name", "nameplate_id": 1},
        ]
        while len(slots) < block_count and len(slots) < 22:
            slots.append(
                {
                    "box": None,
                    "x": rng.randint(60, 500),
                    "y": rng.randint(230, 430),
                    "font_size": rng.randint(14, 17),
                    "color": rng.choice([(255, 76, 76), (255, 232, 166), (86, 255, 112), (210, 240, 255)]),
                    "max_lines": 1,
                }
            )
        return slots

    def _dense_vendor_slots(self, block_count: int, rng: random.Random) -> List[Dict[str, Any]]:
        shop_panel = (26, 330, 614, 616)
        slots: List[Dict[str, Any]] = [
            {"box": None, "x": 212, "y": 208, "font_size": 18, "color": (48, 255, 70), "max_lines": 1, "nameplate_role": "name", "nameplate_id": 0},
            {"box": None, "x": 198, "y": 234, "font_size": 15, "color": (48, 255, 70), "max_lines": 1, "nameplate_role": "title", "nameplate_id": 0},
            {"box": None, "x": 430, "y": 282, "font_size": 16, "color": (48, 255, 70), "max_lines": 1, "nameplate_role": "name", "nameplate_id": 1},
            {"box": shop_panel, "x": 54, "y": 354, "font_size": 18, "color": (255, 214, 104), "max_lines": 1, "box_fill": (18, 14, 10), "box_outline": (194, 154, 82)},
            {"box": shop_panel, "x": 54, "y": 386, "font_size": 17, "color": (236, 232, 204), "max_lines": 1, "box_fill": (18, 14, 10), "box_outline": (194, 154, 82)},
            {"box": shop_panel, "x": 54, "y": 418, "font_size": 17, "color": (236, 232, 204), "max_lines": 1, "box_fill": (18, 14, 10), "box_outline": (194, 154, 82)},
            {"box": shop_panel, "x": 54, "y": 450, "font_size": 17, "color": (236, 232, 204), "max_lines": 1, "box_fill": (18, 14, 10), "box_outline": (194, 154, 82)},
            {"box": (368, 350, 586, 528), "x": 392, "y": 374, "font_size": 16, "color": (166, 232, 255), "max_lines": 1, "box_fill": (20, 30, 36), "box_outline": (132, 188, 210)},
            {"box": (368, 350, 586, 528), "x": 392, "y": 406, "font_size": 16, "color": (255, 228, 178), "max_lines": 1, "box_fill": (20, 30, 36), "box_outline": (132, 188, 210)},
            {"box": (42, 34, 240, 108), "x": 62, "y": 56, "font_size": 15, "color": (230, 244, 255), "max_lines": 1, "box_fill": (18, 24, 28)},
            {"box": None, "x": 382, "y": 74, "font_size": 17, "color": (255, 232, 166), "max_lines": 1},
            {"box": None, "x": 82, "y": 270, "font_size": 16, "color": (210, 240, 255), "max_lines": 1},
        ]
        while len(slots) < block_count and len(slots) < 22:
            slots.append(
                {
                    "box": shop_panel if rng.random() < 0.65 else None,
                    "x": rng.choice([54, 392, rng.randint(80, 470)]),
                    "y": rng.randint(360, 560),
                    "font_size": rng.randint(14, 16),
                    "color": rng.choice([(236, 232, 204), (255, 214, 104), (166, 232, 255), (210, 240, 255)]),
                    "max_lines": 1,
                    "box_fill": (18, 14, 10),
                    "box_outline": (194, 154, 82),
                }
            )
        return slots

    def _dense_map_slots(self, block_count: int, rng: random.Random) -> List[Dict[str, Any]]:
        map_panel = (42, 52, 430, 512)
        quest_panel = (444, 72, 616, 512)
        slots: List[Dict[str, Any]] = [
            {"box": map_panel, "x": 66, "y": 78, "font_size": 16, "color": (72, 44, 24), "max_lines": 1, "box_fill": (214, 184, 122), "box_outline": (92, 64, 36)},
            {"box": None, "x": 136, "y": 180, "font_size": 15, "color": (84, 52, 28), "max_lines": 1},
            {"box": None, "x": 274, "y": 256, "font_size": 15, "color": (84, 52, 28), "max_lines": 1},
            {"box": None, "x": 94, "y": 376, "font_size": 15, "color": (84, 52, 28), "max_lines": 1},
            {"box": quest_panel, "x": 466, "y": 98, "font_size": 16, "color": (255, 232, 166), "max_lines": 1, "box_fill": (18, 24, 32), "box_outline": (148, 174, 194)},
            {"box": quest_panel, "x": 466, "y": 132, "font_size": 15, "color": (230, 244, 255), "max_lines": 1, "box_fill": (18, 24, 32), "box_outline": (148, 174, 194)},
            {"box": quest_panel, "x": 466, "y": 166, "font_size": 15, "color": (230, 244, 255), "max_lines": 1, "box_fill": (18, 24, 32), "box_outline": (148, 174, 194)},
            {"box": quest_panel, "x": 466, "y": 200, "font_size": 15, "color": (230, 244, 255), "max_lines": 1, "box_fill": (18, 24, 32), "box_outline": (148, 174, 194)},
            {"box": (62, 534, 580, 612), "x": 84, "y": 556, "font_size": 17, "color": (245, 246, 238), "max_lines": 1, "box_fill": (10, 12, 18), "box_outline": (220, 220, 210)},
            {"box": None, "x": 468, "y": 540, "font_size": 16, "color": (52, 255, 74), "max_lines": 1, "nameplate_role": "name", "nameplate_id": 0},
            {"box": None, "x": 480, "y": 566, "font_size": 14, "color": (52, 255, 74), "max_lines": 1, "nameplate_role": "title", "nameplate_id": 0},
        ]
        while len(slots) < block_count and len(slots) < 21:
            slots.append(
                {
                    "box": rng.choice([map_panel, quest_panel, None]),
                    "x": rng.choice([rng.randint(76, 330), 466, rng.randint(80, 500)]),
                    "y": rng.randint(110, 500),
                    "font_size": rng.randint(13, 16),
                    "color": rng.choice([(84, 52, 28), (230, 244, 255), (255, 232, 166), (52, 255, 74)]),
                    "max_lines": 1,
                    "box_fill": (18, 24, 32),
                    "box_outline": (148, 174, 194),
                }
            )
        return slots

    def _dense_party_slots(self, block_count: int, rng: random.Random) -> List[Dict[str, Any]]:
        slots: List[Dict[str, Any]] = []
        card_boxes = [(30, 52, 294, 188), (346, 52, 610, 188), (30, 224, 294, 360), (346, 224, 610, 360)]
        for idx, box in enumerate(card_boxes):
            x = box[0] + 84
            y = box[1] + 22
            slots.append({"box": box, "x": x, "y": y, "font_size": 16, "color": (52, 255, 74), "max_lines": 1, "nameplate_role": "name", "nameplate_id": idx, "box_fill": (18, 24, 32), "box_outline": (126, 154, 174)})
            slots.append({"box": box, "x": x, "y": y + 30, "font_size": 14, "color": (255, 232, 166), "max_lines": 1, "box_fill": (18, 24, 32), "box_outline": (126, 154, 174)})
        slots.extend(
            [
                {"box": (32, 412, 608, 610), "x": 58, "y": 438, "font_size": 18, "color": (245, 246, 238), "max_lines": 1, "box_fill": (10, 12, 18), "box_outline": (220, 220, 210)},
                {"box": (32, 412, 608, 610), "x": 58, "y": 472, "font_size": 17, "color": (230, 244, 255), "max_lines": 1, "box_fill": (10, 12, 18), "box_outline": (220, 220, 210)},
                {"box": (32, 412, 608, 610), "x": 58, "y": 506, "font_size": 17, "color": (255, 228, 178), "max_lines": 1, "box_fill": (10, 12, 18), "box_outline": (220, 220, 210)},
                {"box": (32, 412, 608, 610), "x": 58, "y": 540, "font_size": 17, "color": (220, 255, 210), "max_lines": 1, "box_fill": (10, 12, 18), "box_outline": (220, 220, 210)},
            ]
        )
        while len(slots) < block_count and len(slots) < 22:
            box = rng.choice(card_boxes)
            slots.append(
                {
                    "box": box,
                    "x": box[0] + rng.randint(86, 150),
                    "y": box[1] + rng.randint(64, 98),
                    "font_size": rng.randint(13, 15),
                    "color": rng.choice([(230, 244, 255), (255, 232, 166), (220, 255, 210)]),
                    "max_lines": 1,
                    "box_fill": (18, 24, 32),
                    "box_outline": (126, 154, 174),
                }
            )
        return slots

    def _jitter_dense_slots(self, slots: Sequence[Dict[str, Any]], rng: random.Random) -> None:
        for slot in slots:
            slot["x"] = max(12, min(self.width - 34, int(slot["x"]) + rng.randint(-8, 8)))
            slot["y"] = max(12, min(self.height - 26, int(slot["y"]) + rng.randint(-6, 6)))
            if rng.random() < 0.18:
                color = slot.get("color", (230, 230, 230))
                slot["color"] = tuple(max(32, min(255, int(c) + rng.randint(-16, 16))) for c in color)

    def _html_for_layout(self, layout: Sequence[Dict[str, Any]]) -> str:
        box_html = []
        line_html = []
        emitted_boxes = set()
        scene_style = str(layout[0].get("scene_style", "hud_overlay")) if layout else "hud_overlay"
        scene_variant = str(layout[0].get("scene_variant", scene_style)) if layout else scene_style
        decor_html = self._html_scene_decor(scene_style, scene_variant)
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
        scene_class = f"{'dense' if self.difficulty == 'dense' else ''} scene-{scene_style} variant-{scene_variant}".strip()
        dense_css = """
            #scene.dense:after {
              content: "";
              position: absolute;
              inset: 0;
              background:
                repeating-linear-gradient(90deg, rgba(255,255,255,.04) 0 1px, transparent 1px 14px),
                linear-gradient(12deg, transparent 0 58%, rgba(255,255,255,.12) 59% 61%, transparent 62%);
              pointer-events: none;
              z-index: 3;
            }
            .sprite, .prop, .map-mark, .slash, .shop-item, .portrait {
              position: absolute;
              z-index: 1;
              pointer-events: none;
            }
            .sprite .head {
              position: absolute;
              width: 34px;
              height: 34px;
              left: 23px;
              top: 0;
              border-radius: 50%;
              background: var(--head, #87909a);
              border: 2px solid rgba(230,238,245,.72);
            }
            .sprite .body {
              position: absolute;
              width: 78px;
              height: 92px;
              left: 0;
              top: 34px;
              clip-path: polygon(18% 0, 82% 0, 100% 100%, 0 100%);
              background: var(--body, #44546a);
              border: 2px solid rgba(210,220,232,.62);
            }
            .portrait {
              width: 58px;
              height: 72px;
              border-radius: 9px;
              background: radial-gradient(circle at 50% 24%, #b7bec8 0 15%, transparent 16%),
                          linear-gradient(155deg, #384454, #141820);
              border: 2px solid rgba(220,230,240,.74);
              box-shadow: inset 0 -18px 0 rgba(255,255,255,.07);
            }
            .prop {
              border: 2px solid rgba(230,230,220,.7);
              background: rgba(90,118,132,.42);
              box-shadow: 0 6px 18px rgba(0,0,0,.24);
            }
            .slash {
              height: 4px;
              background: rgba(255,220,100,.74);
              transform: rotate(-18deg);
              box-shadow: 0 0 12px rgba(255,220,100,.55);
            }
            .map-mark {
              width: 16px;
              height: 16px;
              border-radius: 50%;
              background: #d43c34;
              border: 2px solid #fff2b0;
              box-shadow: 0 0 0 5px rgba(212,60,52,.24);
            }
            .shop-item {
              width: 34px;
              height: 34px;
              border-radius: 7px;
              background: linear-gradient(135deg, #e0bc52, #4e78d6);
              border: 2px solid rgba(245,238,210,.8);
            }
        """ if self.difficulty == "dense" else ""
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
              z-index: 2;
              border: 2px solid rgba(210,225,235,.88);
              background: rgba(16, 24, 36, .84);
              border-radius: 8px;
              box-shadow: 0 8px 24px rgba(0,0,0,.35);
            }}
            .line {{
              position: absolute;
              z-index: 4;
              font-weight: 700;
              line-height: 1.16;
              white-space: pre;
              text-shadow: 0 2px 2px rgba(0,0,0,.9), 0 0 5px rgba(0,0,0,.65);
            }}
            {dense_css}
          </style>
        </head>
        <body><div id="scene" class="{scene_class}">{decor_html}{''.join(box_html)}{''.join(line_html)}</div></body>
        </html>
        """

    def _html_scene_decor(self, scene_style: str, scene_variant: str) -> str:
        sprites = {
            "dialogue_scene": [
                (284, 284, "#6d6178", "#b6bac4"),
                (412, 250, "#405069", "#aeb6c0"),
            ],
            "nameplate_scene": [
                (82, 340, "#4f5f72", "#abb4be"),
                (294, 288, "#6a514d", "#b8b1a6"),
                (486, 318, "#50684f", "#b7c5b0"),
            ],
            "crafting_menu": [
                (452, 342, "#58506a", "#b8b0c8"),
                (192, 372, "#5f513d", "#c2b294"),
            ],
            "hud_overlay": [
                (300, 282, "#405069", "#aeb6c0"),
                (184, 348, "#584b3e", "#b8ad9d"),
            ],
            "battle_arena": [
                (226, 286, "#354762", "#b7c0cc"),
                (392, 246, "#63343a", "#c5a5a5"),
                (478, 310, "#26333d", "#93a3ae"),
            ],
            "vendor_shop": [
                (210, 178, "#6a4e35", "#c4b194"),
                (438, 252, "#334c64", "#aebac6"),
            ],
            "map_screen": [
                (494, 454, "#43566d", "#b7c0ca"),
            ],
            "party_status": [
                (54, 82, "#465872", "#b7c0cc"),
                (370, 82, "#675040", "#c2b099"),
                (54, 254, "#4f684e", "#b8c8b2"),
                (370, 254, "#654661", "#c6b2c8"),
            ],
        }.get(scene_style, [(300, 282, "#405069", "#aeb6c0")])
        html_parts = [
            f"<div class='sprite' style='left:{x}px;top:{y}px;--body:{body};--head:{head}'><span class='head'></span><span class='body'></span></div>"
            for x, y, body, head in sprites
        ]
        if scene_style == "battle_arena":
            html_parts.extend(
                [
                    "<div class='slash' style='left:250px;top:236px;width:150px'></div>",
                    "<div class='slash' style='left:166px;top:386px;width:116px;transform:rotate(21deg)'></div>",
                ]
            )
        elif scene_style == "vendor_shop":
            for idx, x in enumerate([84, 128, 172, 498, 542]):
                html_parts.append(f"<div class='shop-item' style='left:{x}px;top:{126 + (idx % 2) * 38}px'></div>")
        elif scene_style == "map_screen":
            html_parts.extend(
                [
                    "<div class='map-mark' style='left:160px;top:210px'></div>",
                    "<div class='map-mark' style='left:306px;top:312px'></div>",
                    "<div class='prop' style='left:78px;top:92px;width:310px;height:380px;background:rgba(210,178,116,.34)'></div>",
                ]
            )
        elif scene_style == "party_status":
            for x, y in [(54, 76), (370, 76), (54, 248), (370, 248)]:
                html_parts.append(f"<div class='portrait' style='left:{x}px;top:{y}px'></div>")
        else:
            html_parts.append("<div class='prop' style='left:474px;top:80px;width:86px;height:86px;border-radius:50%'></div>")
        return "".join(html_parts)

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

    def _scene_actor_count(self, scene_style: str) -> int:
        return {
            "dialogue_scene": 2,
            "nameplate_scene": 5 if self.difficulty == "dense" else 3,
            "crafting_menu": 2,
            "hud_overlay": 2 if self.difficulty == "dense" else 1,
            "battle_arena": 3,
            "vendor_shop": 2,
            "map_screen": 1,
            "party_status": 4,
        }.get(scene_style, 1)

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

    def _draw_normal_game_clutter(self, draw: ImageDraw.ImageDraw, rng: random.Random, scene_style: str) -> None:
        if scene_style == "dialogue_scene":
            self._draw_dialogue_scene_clutter(draw, rng, dense=False)
        elif scene_style == "nameplate_scene":
            self._draw_nameplate_scene_clutter(draw, rng, dense=False)
        else:
            self._draw_hud_scene_clutter(draw, rng, dense=False)

    def _draw_dense_game_clutter(self, draw: ImageDraw.ImageDraw, rng: random.Random, scene_style: str) -> None:
        if scene_style == "crafting_menu":
            self._draw_crafting_scene_clutter(draw, rng)
        elif scene_style == "dialogue_scene":
            self._draw_dialogue_scene_clutter(draw, rng, dense=True)
        elif scene_style == "nameplate_scene":
            self._draw_nameplate_scene_clutter(draw, rng, dense=True)
        elif scene_style == "battle_arena":
            self._draw_battle_scene_clutter(draw, rng)
        elif scene_style == "vendor_shop":
            self._draw_vendor_scene_clutter(draw, rng)
        elif scene_style == "map_screen":
            self._draw_map_scene_clutter(draw, rng)
        elif scene_style == "party_status":
            self._draw_party_scene_clutter(draw, rng)
        else:
            self._draw_hud_scene_clutter(draw, rng, dense=True)

    def _draw_dialogue_scene_clutter(self, draw: ImageDraw.ImageDraw, rng: random.Random, dense: bool) -> None:
        for y in range(0, 260, 22):
            shade = 48 + y // 12
            draw.line((0, y, self.width, max(0, y - 56)), fill=(shade, shade + 8, shade + 14), width=6)
        draw.polygon([(0, 366), (180, 288), (392, 336), (640, 250), (640, 640), (0, 640)], fill=(66, 58, 58))
        for x in range(-40, 680, 90):
            draw.line((x, 470, x + 132, 640), fill=(88, 76, 68), width=4)
        fire_x, fire_y = 164, 210
        for radius, color in [(64, (126, 62, 34)), (42, (220, 116, 42)), (22, (255, 214, 84))]:
            draw.ellipse((fire_x - radius, fire_y - radius, fire_x + radius, fire_y + radius), outline=color, width=4)
        for _ in range(12 if dense else 7):
            x = fire_x + rng.randint(-34, 34)
            y = fire_y + rng.randint(-76, -12)
            draw.polygon([(x, y), (x + rng.randint(-14, 14), y + 44), (x + rng.randint(-22, 22), y + 18)], fill=(255, rng.randint(130, 210), 42))
        self._draw_game_character(draw, 324, 456, scale=1.05, fill=(46, 54, 68))
        self._draw_game_character(draw, 428, 430, scale=0.95, fill=(86, 82, 98))

    def _draw_nameplate_scene_clutter(self, draw: ImageDraw.ImageDraw, rng: random.Random, dense: bool) -> None:
        draw.rectangle((0, 0, 640, 250), fill=(78, 54, 38))
        for x in range(36, 640, 124):
            draw.rectangle((x, 0, x + 24, 330), fill=(54, 38, 30))
        for y in range(54, 250, 58):
            for x in range(0, 640, 96):
                shade = rng.randint(72, 100)
                draw.rounded_rectangle((x, y, x + 88, y + 44), radius=8, fill=(shade, shade - 16, shade - 22), outline=(44, 34, 30))
        draw.polygon([(0, 338), (640, 294), (640, 640), (0, 640)], fill=(76, 60, 46))
        for y in range(332, 640, 38):
            draw.line((0, y, 640, y - 48), fill=(106, 82, 58), width=3)
        characters = [(118, 494, 1.08), (326, 438, 1.0), (510, 468, 0.88)]
        if dense:
            characters.extend([(212, 552, 0.72), (434, 550, 0.7)])
        for cx, base, scale in characters:
            self._draw_game_character(draw, cx, base, scale=scale, fill=rng.choice([(58, 62, 78), (76, 62, 58), (62, 76, 66)]))

    def _draw_hud_scene_clutter(self, draw: ImageDraw.ImageDraw, rng: random.Random, dense: bool) -> None:
        draw.ellipse((496, 58, 594, 156), outline=(112, 160, 158), width=3)
        for angle in range(0, 360, 45):
            x = 545 + int(math.cos(math.radians(angle)) * 42)
            y = 107 + int(math.sin(math.radians(angle)) * 42)
            draw.line((545, 107, x, y), fill=(72, 104, 112), width=1)
        for i in range(8 if dense else 5):
            x = 50 + i * 26
            y = 146
            fill = rng.choice([(76, 92, 110), (88, 70, 52), (56, 94, 78)])
            draw.rectangle((x, y, x + 18, y + 18), fill=fill, outline=(160, 174, 184))
        self._draw_game_character(draw, rng.randint(270, 350), rng.randint(330, 390), scale=1.0, fill=(50, 58, 70))
        for y in range(16, self.height, 18):
            draw.line((0, y, self.width, y), fill=(42, 48, 58), width=1)
        for _ in range(9 if dense else 5):
            x = rng.randint(24, self.width - 90)
            y = rng.randint(54, 430)
            draw.line((x, y, x + rng.randint(36, 92), y + rng.randint(-8, 8)), fill=(80, 92, 104), width=2)

    def _draw_crafting_scene_clutter(self, draw: ImageDraw.ImageDraw, rng: random.Random) -> None:
        draw.rectangle((0, 0, 640, 640), fill=(36, 28, 22))
        draw.rectangle((26, 12, 298, 586), fill=(18, 16, 14), outline=(94, 94, 86), width=2)
        draw.rectangle((310, 12, 620, 586), fill=(28, 22, 18), outline=(112, 106, 94), width=2)
        draw.rounded_rectangle((38, 14, 196, 32), radius=4, fill=(8, 9, 10), outline=(74, 74, 70))
        draw.rounded_rectangle((206, 14, 286, 32), radius=4, fill=(22, 22, 20), outline=(90, 88, 82))
        for y in [70, 100, 130, 160, 190, 220, 350, 380, 410, 440, 470, 500]:
            draw.line((48, y, 272, y), fill=(68, 62, 48), width=1)
        draw.rectangle((282, 42, 290, 560), fill=(58, 56, 54))
        draw.rectangle((282, rng.randint(60, 230), 290, rng.randint(260, 500)), fill=(140, 140, 132))
        icon_colors = [(72, 204, 84), (84, 122, 218), (224, 198, 82), (164, 84, 210)]
        for idx, y in enumerate([172, 238, 304]):
            draw.rounded_rectangle((334, y, 370, y + 36), radius=5, fill=(12, 14, 18), outline=(150, 150, 142))
            draw.rectangle((340, y + 6, 364, y + 30), fill=icon_colors[idx % len(icon_colors)])
        for x in [334, 376, 418]:
            draw.rounded_rectangle((x, 370, x + 36, 406), radius=5, fill=(14, 14, 12), outline=(118, 118, 108))
            draw.line((x + 18, 382, x + 18, 398), fill=(42, 230, 80), width=3)
            draw.line((x + 10, 390, x + 26, 390), fill=(42, 230, 80), width=3)
        draw.rounded_rectangle((50, 594, 144, 626), radius=4, fill=(98, 76, 18), outline=(245, 220, 70), width=2)
        draw.rounded_rectangle((152, 594, 246, 626), radius=4, fill=(20, 20, 18), outline=(86, 86, 78), width=1)
        draw.rounded_rectangle((252, 594, 346, 626), radius=4, fill=(20, 20, 18), outline=(86, 86, 78), width=1)
        draw.rounded_rectangle((430, 336, 582, 538), radius=8, fill=(34, 30, 32), outline=(130, 128, 120), width=2)
        self._draw_game_character(draw, 506, 500, scale=0.78, fill=(70, 62, 86))
        self._draw_game_character(draw, 190, 552, scale=0.58, fill=(82, 66, 48))
        for x in [456, 494, 532]:
            draw.ellipse((x - 9, 182, x + 9, 200), fill=(210, 180, 76), outline=(80, 72, 44))

    def _draw_battle_scene_clutter(self, draw: ImageDraw.ImageDraw, rng: random.Random) -> None:
        draw.rectangle((0, 0, 640, 240), fill=(42, 28, 38))
        draw.polygon([(0, 254), (160, 212), (376, 244), (640, 198), (640, 640), (0, 640)], fill=(64, 54, 48))
        for y in range(280, 640, 34):
            draw.line((0, y, 640, y - rng.randint(24, 54)), fill=(90, 74, 62), width=3)
        for _ in range(16):
            x = rng.randint(50, 590)
            y = rng.randint(210, 430)
            draw.line((x, y, x + rng.randint(-48, 48), y + rng.randint(-18, 22)), fill=(138, 104, 72), width=2)
        self._draw_game_character(draw, 236, 424, scale=1.0, fill=(44, 58, 78))
        self._draw_game_character(draw, 392, 396, scale=0.95, fill=(88, 50, 58))
        self._draw_game_character(draw, 492, 442, scale=0.82, fill=(42, 48, 52))
        for rect, color in [((238, 238, 414, 246), (255, 210, 88)), ((138, 360, 276, 368), (100, 220, 255)), ((374, 304, 528, 312), (255, 94, 84))]:
            draw.line((rect[0], rect[1], rect[2], rect[3]), fill=color, width=4)

    def _draw_vendor_scene_clutter(self, draw: ImageDraw.ImageDraw, rng: random.Random) -> None:
        draw.rectangle((0, 0, 640, 310), fill=(76, 52, 34))
        for x in range(34, 640, 118):
            draw.rectangle((x, 22, x + 92, 184), fill=(48, 36, 28), outline=(106, 78, 48), width=2)
            for y in [60, 104, 148]:
                draw.line((x + 8, y, x + 84, y), fill=(134, 98, 58), width=2)
                for ix in range(x + 12, x + 78, 24):
                    color = rng.choice([(196, 154, 64), (82, 128, 204), (126, 190, 92), (182, 94, 148)])
                    draw.rounded_rectangle((ix, y - 28, ix + 16, y - 8), radius=3, fill=color, outline=(42, 36, 30))
        draw.polygon([(0, 310), (640, 276), (640, 640), (0, 640)], fill=(62, 46, 34))
        draw.rounded_rectangle((54, 272, 586, 360), radius=8, fill=(84, 58, 34), outline=(154, 116, 66), width=3)
        self._draw_game_character(draw, 238, 288, scale=0.9, fill=(92, 70, 50))
        self._draw_game_character(draw, 462, 346, scale=0.76, fill=(42, 62, 82))
        for x in [100, 140, 520, 558]:
            draw.ellipse((x - 14, 238, x + 14, 266), fill=(210, 178, 76), outline=(64, 54, 34))

    def _draw_map_scene_clutter(self, draw: ImageDraw.ImageDraw, rng: random.Random) -> None:
        draw.rectangle((0, 0, 640, 640), fill=(34, 42, 48))
        draw.rounded_rectangle((42, 52, 430, 512), radius=12, fill=(214, 184, 122), outline=(92, 64, 36), width=3)
        for _ in range(9):
            x = rng.randint(72, 390)
            y = rng.randint(86, 470)
            draw.line((x, y, x + rng.randint(-80, 90), y + rng.randint(-48, 48)), fill=(126, 88, 48), width=2)
        for x, y, color in [(160, 210, (210, 52, 44)), (306, 312, (52, 92, 210)), (118, 386, (54, 150, 70))]:
            draw.ellipse((x - 10, y - 10, x + 10, y + 10), fill=color, outline=(255, 240, 180), width=2)
            draw.line((x, y + 10, x + rng.randint(-16, 16), y + 34), fill=color, width=3)
        draw.rounded_rectangle((444, 72, 616, 512), radius=8, fill=(18, 24, 32), outline=(148, 174, 194), width=2)
        self._draw_game_character(draw, 530, 612, scale=0.74, fill=(58, 72, 88))
        draw.rounded_rectangle((468, 520, 594, 622), radius=8, outline=(138, 160, 176), width=2)

    def _draw_party_scene_clutter(self, draw: ImageDraw.ImageDraw, rng: random.Random) -> None:
        draw.rectangle((0, 0, 640, 640), fill=(22, 28, 38))
        card_boxes = [(30, 52, 294, 188), (346, 52, 610, 188), (30, 224, 294, 360), (346, 224, 610, 360)]
        fills = [(48, 64, 86), (88, 64, 48), (52, 82, 56), (82, 52, 78)]
        for box, fill in zip(card_boxes, fills):
            draw.rounded_rectangle(box, radius=9, fill=(18, 24, 32), outline=(126, 154, 174), width=2)
            px, py = box[0] + 24, box[1] + 24
            draw.rounded_rectangle((px, py, px + 58, py + 74), radius=8, fill=(26, 30, 38), outline=(170, 182, 194), width=2)
            self._draw_game_character(draw, px + 29, py + 76, scale=0.34, fill=fill)
            bar_y = box[3] - 34
            draw.rectangle((box[0] + 100, bar_y, box[2] - 24, bar_y + 8), fill=(46, 58, 68), outline=(120, 132, 142))
            draw.rectangle((box[0] + 100, bar_y, rng.randint(box[0] + 150, box[2] - 24), bar_y + 8), fill=(64, 210, 96))
        draw.rounded_rectangle((32, 412, 608, 610), radius=9, fill=(10, 12, 18), outline=(220, 220, 210), width=2)
        for x in range(64, 590, 54):
            draw.rectangle((x, 384, x + 28, 406), fill=rng.choice([(76, 92, 110), (88, 70, 52), (56, 94, 78)]), outline=(150, 160, 170))

    def _draw_game_character(self, draw: ImageDraw.ImageDraw, cx: int, base: int, scale: float, fill: Tuple[int, int, int]) -> None:
        head_r = max(10, int(20 * scale))
        body_w = max(28, int(58 * scale))
        body_h = max(58, int(112 * scale))
        draw.ellipse((cx - head_r, base - body_h - head_r * 2, cx + head_r, base - body_h), fill=tuple(min(255, c + 28) for c in fill), outline=(120, 120, 130))
        draw.polygon(
            [
                (cx - body_w, base - body_h),
                (cx + body_w, base - body_h),
                (cx + body_w // 2, base),
                (cx - body_w // 2, base),
            ],
            fill=fill,
            outline=(118, 124, 136),
        )


def _rect_area(rect: Rect) -> int:
    return max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])


def _noise_metadata(patterns: Sequence[str], panel_count: int) -> Dict[str, Any]:
    return {
        "enabled": True,
        "panel_count": panel_count,
        "patterns": sorted(set(patterns)),
    }


def _fit_rect_in_panel(rect: Rect, panel: Rect, pad: int = 18) -> Rect:
    x1, y1, x2, y2 = rect
    px1, py1, px2, py2 = panel
    width = x2 - x1
    height = y2 - y1
    max_x1 = max(px1 + pad, px2 - pad - width)
    max_y1 = max(py1 + pad, py2 - pad - height)
    nx1 = min(max(px1 + pad, x1), max_x1)
    ny1 = min(max(py1 + pad, y1), max_y1)
    return (nx1, ny1, nx1 + width, ny1 + height)


def _max_overlap_with(rect: Rect, others: Sequence[Rect]) -> float:
    if not others:
        return 0.0
    return max(_overlap_ratio(rect, other) for other in others)


def _max_overlap_ratio(rects: Sequence[Rect]) -> float:
    max_overlap = 0.0
    for idx, rect in enumerate(rects):
        max_overlap = max(max_overlap, _max_overlap_with(rect, rects[idx + 1 :]))
    return max_overlap


def _intersection_area(a: Rect, b: Rect) -> int:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    return max(0, x2 - x1) * max(0, y2 - y1)


def _overlap_ratio(a: Rect, b: Rect) -> float:
    base = min(_rect_area(a), _rect_area(b))
    if base <= 0:
        return 0.0
    return _intersection_area(a, b) / base
