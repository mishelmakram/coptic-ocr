"""Line images as the recognizer sees them, without PyTorch (the installed program reads with
ONNX Runtime; training and the PyTorch reader share these too)."""

from __future__ import annotations

import numpy as np
from PIL import Image

HEIGHT = 48      # input line height in pixels
STRIDE = 4       # image columns per output frame
MAX_WIDTH = 1600
PAD_TO = 64      # few distinct batch widths: back ends re-plan for every new shape


def line_pixels(img: Image.Image, mirror: bool = False) -> np.ndarray:
    """Grayscale line -> (HEIGHT, W) float32, ink = 1, paper = 0.

    ``mirror`` flips a right-to-left line so it is read from its first letter.
    """
    img = img.convert("L")
    if mirror:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    width = min(MAX_WIDTH, max(HEIGHT, round(img.width * HEIGHT / img.height)))
    img = img.resize((width, HEIGHT), Image.BILINEAR)
    return 1.0 - np.asarray(img, dtype=np.float32) / 255.0


def batch(images: list[Image.Image], mirror: bool = False) -> tuple[np.ndarray, list[int]]:
    """Line images padded to one width: (B, 1, HEIGHT, W) and each line's own width."""
    lines = [line_pixels(img, mirror) for img in images]
    width = -(-max(line.shape[-1] for line in lines) // PAD_TO) * PAD_TO
    out = np.zeros((len(lines), 1, HEIGHT, width), dtype=np.float32)
    for i, line in enumerate(lines):
        out[i, 0, :, : line.shape[-1]] = line
    return out, [line.shape[-1] for line in lines]
