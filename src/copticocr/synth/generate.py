"""Generate a synthetic dataset of Coptic text-line images.

    copticocr-synth --corpus data/corpus/bohairic_ot.txt data/corpus/lessons.txt \\
        --fonts fonts data/fonts_unicode --count 100000 --out data/synth/v1

Writes ``images/*.png`` and ``labels.tsv`` (image path, Unicode text, font).
Sample ``i`` depends only on ``--seed`` and ``i``, so a dataset can be
regenerated or extended exactly.
"""

from __future__ import annotations

import argparse
import multiprocessing
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from ..data.corpus import load_corpus
from .degrade import degrade
from .render import LineFont, LineSampler, discover_fonts, render_line

_state: dict = {}


def _init(corpus: list[str], fonts: list[LineFont], out: Path, height: int, seed: int) -> None:
    _state.update(corpus=corpus, fonts=fonts, out=out, height=height, seed=seed)


def make_sample(index: int) -> tuple[str, str, str]:
    s = _state
    rng = random.Random(f"{s['seed']}-{index}")
    np_rng = np.random.default_rng([s["seed"], index])

    text = LineSampler(s["corpus"], rng).sample()
    font = rng.choice(s["fonts"])
    img = render_line(text, font, size=rng.randint(36, 64), word_gap=rng.uniform(0.25, 0.9))
    img = degrade(img, np_rng)
    width = max(1, round(img.width * s["height"] / img.height))
    img = img.resize((width, s["height"]), Image.LANCZOS)

    name = f"images/{index:07d}.png"
    img.save(s["out"] / name)
    return name, text, font.family


def generate(corpus: list[str], fonts: list[LineFont], out: Path, count: int,
             start: int = 0, height: int = 64, seed: int = 0, workers: int = 0) -> None:
    (out / "images").mkdir(parents=True, exist_ok=True)
    workers = workers or max(1, multiprocessing.cpu_count() - 1)
    args = (corpus, fonts, out, height, seed)
    indices = range(start, start + count)
    with open(out / "labels.tsv", "a", encoding="utf-8") as labels:
        if workers == 1:
            _init(*args)
            results = map(make_sample, indices)
        else:
            pool = multiprocessing.Pool(workers, _init, args)
            results = pool.imap(make_sample, indices, chunksize=64)
        for done, (name, text, family) in enumerate(results, 1):
            labels.write(f"{name}\t{text}\t{family}\n")
            if done % 1000 == 0:
                print(f"{done}/{count}", file=sys.stderr)
        if workers != 1:
            pool.close()
            pool.join()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="copticocr-synth", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", nargs="+", type=Path, required=True)
    parser.add_argument("--fonts", nargs="+", type=Path, required=True, help="font directories")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--start", type=int, default=0, help="first sample index (to extend a dataset)")
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=0, help="0 = all CPUs but one")
    args = parser.parse_args(argv)

    fonts = discover_fonts(*args.fonts)
    if not fonts:
        parser.error("no usable Coptic fonts found")
    print("fonts:", ", ".join(f.family for f in fonts), file=sys.stderr)
    generate(load_corpus(*args.corpus), fonts, args.out, args.count,
             args.start, args.height, args.seed, args.workers)


if __name__ == "__main__":
    main()
