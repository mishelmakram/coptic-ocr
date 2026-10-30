"""Line-image datasets in the ``labels.tsv`` layout written by copticocr-synth."""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset, Sampler

from .charset import Charset
from .model import HEIGHT

MAX_WIDTH = 1600
PAD_TO = 64


def load_image(img: Image.Image) -> torch.Tensor:
    """Grayscale line -> (1, HEIGHT, W) float tensor, ink = 1, paper = 0."""
    img = img.convert("L")
    width = min(MAX_WIDTH, max(HEIGHT, round(img.width * HEIGHT / img.height)))
    img = img.resize((width, HEIGHT), Image.BILINEAR)
    pixels = 1.0 - np.asarray(img, dtype=np.float32) / 255.0
    return torch.from_numpy(pixels).unsqueeze(0)


def read_labels(root: Path) -> list[tuple[Path, str]]:
    items = []
    for line in (root / "labels.tsv").read_text(encoding="utf-8").splitlines():
        name, text = line.split("\t")[:2]
        items.append((root / name, text))
    return items


class LineDataset(Dataset):
    def __init__(self, items: list[tuple[Path, str]], charset: Charset):
        self.items = items
        self.charset = charset

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, i: int):
        path, text = self.items[i]
        with Image.open(path) as img:
            return load_image(img), torch.tensor(self.charset.encode(text), dtype=torch.long), text


def collate(batch):
    images, targets, texts = zip(*batch)
    # Few distinct batch shapes: cuDNN re-plans (slowly) for every new width.
    width = -(-max(img.shape[-1] for img in images) // PAD_TO) * PAD_TO
    padded = torch.zeros(len(images), 1, HEIGHT, width)
    for i, img in enumerate(images):
        padded[i, :, :, : img.shape[-1]] = img
    widths = torch.tensor([img.shape[-1] for img in images])
    lengths = torch.tensor([len(t) for t in targets])
    return padded, widths, torch.cat(targets), lengths, list(texts)


class WidthBucketSampler(Sampler):
    """Batches of similar width, so little compute is spent on padding.

    ``widths`` are approximate (label length is a good proxy for line width).
    """

    def __init__(self, widths: list[int], batch_size: int, seed: int = 0):
        self.widths = widths
        self.batch_size = batch_size
        self.seed = seed
        self.epoch = 0
        self.skip = 0  # batches to leave out at the start (resuming mid-epoch)

    def __iter__(self):
        rng = random.Random(self.seed + self.epoch)
        self.epoch += 1
        order = sorted(range(len(self.widths)), key=lambda i: (self.widths[i], rng.random()))
        batches = [order[i:i + self.batch_size] for i in range(0, len(order), self.batch_size)]
        rng.shuffle(batches)
        return iter(batches[self.skip:])

    def __len__(self) -> int:
        return (len(self.widths) + self.batch_size - 1) // self.batch_size
