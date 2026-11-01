"""Pack line images into one memory-mapped file for fast, low-memory training.

Decoding hundreds of thousands of PNGs in loader processes is slow and, on
Windows, every loader process holds its own copy of torch. A packed dataset is
read by slicing a memory map in the main process instead.

    python -m copticocr.recog.packed data/synth/v1 data/synth/v2 --out data/packed/synth-v1v2

Layout of ``--out``: ``lines.u8`` (all lines side by side, HEIGHT rows each,
stored column-major so a line is one contiguous slice), ``offsets.npy``,
``widths.npy`` and ``texts.txt``.
"""

from __future__ import annotations

import argparse
import multiprocessing
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset

from .charset import Charset
from .dataset import MAX_WIDTH, read_labels
from .model import HEIGHT


def _load(path: Path) -> np.ndarray:
    """(width, HEIGHT) uint8 array, ink = 255."""
    with Image.open(path) as img:
        img = img.convert("L")
        width = min(MAX_WIDTH, max(HEIGHT, round(img.width * HEIGHT / img.height)))
        pixels = 255 - np.asarray(img.resize((width, HEIGHT), Image.BILINEAR), dtype=np.uint8)
    return np.ascontiguousarray(pixels.T)


def pack(roots: list[Path], out: Path, workers: int = 0) -> int:
    items = [item for root in roots for item in read_labels(root)]
    out.mkdir(parents=True, exist_ok=True)
    widths = np.zeros(len(items), dtype=np.int32)
    with open(out / "lines.u8", "wb") as data, multiprocessing.Pool(workers or None) as pool:
        for i, columns in enumerate(pool.imap(_load, [path for path, _ in items], chunksize=256)):
            widths[i] = columns.shape[0]
            data.write(columns.tobytes())
            if (i + 1) % 50000 == 0:
                print(f"{i + 1}/{len(items)}", file=sys.stderr, flush=True)
    offsets = np.concatenate([[0], np.cumsum(widths[:-1], dtype=np.int64)])
    np.save(out / "widths.npy", widths)
    np.save(out / "offsets.npy", offsets)
    (out / "texts.txt").write_text("\n".join(text for _, text in items) + "\n", encoding="utf-8")
    return len(items)


def is_packed(path: Path) -> bool:
    return (path / "lines.u8").exists()


def read_texts(root: Path) -> list[str]:
    return (root / "texts.txt").read_text(encoding="utf-8").splitlines()


class PackedLineDataset(Dataset):
    def __init__(self, root: Path, indices: list[int], charset: Charset):
        self.root = root
        self.indices = indices
        self.charset = charset
        self.texts = read_texts(root)
        self.widths = np.load(root / "widths.npy")
        self.offsets = np.load(root / "offsets.npy")
        self._lines = None  # opened lazily so the dataset stays picklable

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, i: int):
        if self._lines is None:
            self._lines = np.memmap(self.root / "lines.u8", dtype=np.uint8, mode="r").reshape(-1, HEIGHT)
        j = self.indices[i]
        start, width = int(self.offsets[j]), int(self.widths[j])
        columns = np.array(self._lines[start:start + width], dtype=np.float32) / 255.0
        if self.charset.rtl:
            columns = columns[::-1]  # read a right-to-left line from its first letter
        image = torch.from_numpy(columns.T.copy()).unsqueeze(0)
        text = self.texts[j]
        return image, torch.tensor(self.charset.encode(text), dtype=torch.long), text


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("roots", nargs="+", type=Path, help="folders with labels.tsv")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=0)
    args = parser.parse_args(argv)
    print(f"packed {pack(args.roots, args.out, args.workers)} lines into {args.out}")


if __name__ == "__main__":
    main()
