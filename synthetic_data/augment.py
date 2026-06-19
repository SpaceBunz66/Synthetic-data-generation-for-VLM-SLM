"""BBox-aware image augmentation."""

from __future__ import annotations

import io
import random
from typing import Any, Dict, List, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from synthetic_data.layout import clamp_bbox
from synthetic_data.schema import LineAnnotation


class Augmentor:
    """Apply mild domain-gap augmentations and transform line boxes."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def apply(
        self,
        image: Image.Image,
        lines: Sequence[LineAnnotation],
        rng: random.Random,
    ) -> Tuple[Image.Image, List[LineAnnotation], Dict[str, Any]]:
        if not self.enabled:
            return image, list(lines), {"enabled": False}

        width, height = image.size
        metadata: Dict[str, Any] = {"enabled": True}

        brightness = rng.uniform(0.82, 1.18)
        contrast = rng.uniform(0.86, 1.22)
        image = ImageEnhance.Brightness(image).enhance(brightness)
        image = ImageEnhance.Contrast(image).enhance(contrast)
        metadata.update({"brightness": round(brightness, 4), "contrast": round(contrast, 4)})

        if rng.random() < 0.35:
            radius = rng.uniform(0.25, 0.9)
            image = image.filter(ImageFilter.GaussianBlur(radius=radius))
            metadata["blur_radius"] = round(radius, 4)

        array = np.array(image).astype(np.float32)
        sigma = rng.uniform(0, 7.5)
        if sigma > 1.0:
            noise = rng_numpy(rng).normal(0, sigma, array.shape)
            array = np.clip(array + noise, 0, 255)
            metadata["gaussian_noise_sigma"] = round(sigma, 4)

        image = Image.fromarray(array.astype(np.uint8), mode="RGB")
        image, lines, affine_meta = self._affine(image, lines, rng)
        metadata.update(affine_meta)

        if rng.random() < 0.45:
            quality = rng.randint(68, 94)
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=quality)
            buffer.seek(0)
            image = Image.open(buffer).convert("RGB")
            metadata["jpeg_quality"] = quality

        return image, lines, metadata

    def _affine(
        self,
        image: Image.Image,
        lines: Sequence[LineAnnotation],
        rng: random.Random,
    ) -> Tuple[Image.Image, List[LineAnnotation], Dict[str, Any]]:
        width, height = image.size
        angle = rng.uniform(-2.0, 2.0)
        scale = rng.uniform(0.985, 1.02)
        tx = rng.uniform(-8, 8)
        ty = rng.uniform(-8, 8)
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, scale)
        matrix[0, 2] += tx
        matrix[1, 2] += ty

        warped = cv2.warpAffine(
            np.array(image),
            matrix,
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )
        transformed_lines = [
            line.with_bbox(_transform_bbox(line.bbox_2d, matrix, width, height))
            for line in lines
        ]
        return (
            Image.fromarray(warped, mode="RGB"),
            transformed_lines,
            {
                "affine": {
                    "angle": round(angle, 4),
                    "scale": round(scale, 4),
                    "translate": [round(tx, 4), round(ty, 4)],
                    "matrix": [[round(float(v), 6) for v in row] for row in matrix.tolist()],
                }
            },
        )


def _transform_bbox(
    bbox: Sequence[int],
    matrix: np.ndarray,
    width: int,
    height: int,
) -> List[int]:
    x1, y1, x2, y2 = bbox
    points = np.array(
        [
            [x1, y1, 1],
            [x2, y1, 1],
            [x2, y2, 1],
            [x1, y2, 1],
        ],
        dtype=np.float32,
    )
    transformed = points @ matrix.T
    xs = transformed[:, 0]
    ys = transformed[:, 1]
    return clamp_bbox([xs.min(), ys.min(), xs.max(), ys.max()], width, height)


def rng_numpy(rng: random.Random) -> np.random.Generator:
    return np.random.default_rng(rng.randint(0, 2**32 - 1))
