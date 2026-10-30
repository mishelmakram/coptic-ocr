"""Make clean rendered lines look like lines cut from old scanned books."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageFilter


def degrade(img: Image.Image, rng: np.random.Generator) -> Image.Image:
    """Apply a random mix of scan artefacts to a black-on-white grayscale line."""
    img = _pad(img, rng)

    if rng.random() < 0.7:
        img = img.rotate(rng.uniform(-1.2, 1.2), resample=Image.BICUBIC, expand=True, fillcolor=255)

    # Ink spread or worn type.
    roll = rng.random()
    if roll < 0.2:
        img = img.filter(ImageFilter.MinFilter(3))
    elif roll < 0.35:
        img = img.filter(ImageFilter.MaxFilter(3))

    # Low scan resolution: shrink and blow back up.
    if rng.random() < 0.5:
        scale = rng.uniform(0.35, 0.8)
        small = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.BILINEAR)
        img = small.resize(img.size, Image.BILINEAR)

    if rng.random() < 0.5:
        img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.3)))

    pixels = np.asarray(img, dtype=np.float32) / 255.0
    pixels = _paper(pixels, rng)
    if rng.random() < 0.6:
        pixels += rng.normal(0, rng.uniform(0.01, 0.08), pixels.shape)
    if rng.random() < 0.3:
        pixels = _speckles(pixels, rng)
    pixels = np.clip(pixels, 0, 1)

    # Many old scans are bilevel.
    if rng.random() < 0.3:
        pixels = (pixels > rng.uniform(0.45, 0.65)).astype(np.float32)

    img = Image.fromarray((pixels * 255).astype(np.uint8), "L")
    if rng.random() < 0.3:
        img = _jpeg(img, int(rng.integers(30, 80)))
    return img


def _pad(img: Image.Image, rng: np.random.Generator) -> Image.Image:
    """Uneven margins, as a line cropped by a segmenter would have."""
    h = img.height
    left, right = (int(rng.integers(0, h // 2 + 1)) for _ in range(2))
    top, bottom = (int(rng.integers(0, h // 6 + 1)) for _ in range(2))
    out = Image.new("L", (img.width + left + right, img.height + top + bottom), 255)
    out.paste(img, (left, top))
    return out


def _paper(pixels: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Darker, uneven paper and faded ink."""
    h, w = pixels.shape
    coarse = rng.uniform(0, 1, (max(2, h // 16), max(2, w // 16))).astype(np.float32)
    field = np.asarray(Image.fromarray(coarse).resize((w, h), Image.BICUBIC))
    paper = rng.uniform(0.75, 1.0) - rng.uniform(0, 0.15) * field
    ink = rng.uniform(0.0, 0.3)
    return ink + (paper - ink) * pixels


def _speckles(pixels: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    mask = rng.random(pixels.shape) < rng.uniform(0.0005, 0.004)
    pixels = pixels.copy()
    pixels[mask] = rng.uniform(0, 0.4)
    return pixels


def _jpeg(img: Image.Image, quality: int) -> Image.Image:
    buffer = io.BytesIO()
    img.save(buffer, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buffer.getvalue())).convert("L")
