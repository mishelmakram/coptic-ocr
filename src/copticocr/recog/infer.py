"""Read Coptic text from line images with a trained checkpoint.

    python -m copticocr.recog.infer models/coptic-crnn/best.pt line1.png line2.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
from PIL import Image

from .charset import Charset
from .dataset import PAD_TO, load_image
from .model import CRNN, HEIGHT, STRIDE


class Recognizer:
    def __init__(self, checkpoint: str | Path, device: str | None = None):
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        state = torch.load(checkpoint, map_location=self.device)
        self.charset = Charset(state["symbols"])
        self.model = CRNN(len(self.charset), state["hidden"]).to(self.device).eval()
        self.model.load_state_dict(state["model"])

    @torch.no_grad()
    def recognize(self, image: Image.Image) -> str:
        logits = self.model(load_image(image).unsqueeze(0).to(self.device))
        return self.charset.decode(logits[0].argmax(-1).cpu())

    @torch.no_grad()
    def recognize_batch(self, images: list[Image.Image]) -> list[tuple[str, list[float]]]:
        """(text, per-letter confidence) for each line image."""
        tensors = [load_image(img) for img in images]
        width = -(-max(t.shape[-1] for t in tensors) // PAD_TO) * PAD_TO
        batch = torch.zeros(len(tensors), 1, HEIGHT, width)
        for i, t in enumerate(tensors):
            batch[i, :, :, : t.shape[-1]] = t
        probs = self.model(batch.to(self.device)).float().softmax(-1)
        best, index = probs.max(-1)
        results = []
        for i, t in enumerate(tensors):
            n = min(t.shape[-1] // STRIDE, probs.shape[1])
            results.append(self.charset.decode_scored(index[i, :n].cpu(), best[i, :n].cpu()))
        return results


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("images", nargs="+", type=Path)
    args = parser.parse_args(argv)
    recognizer = Recognizer(args.checkpoint)
    for path in args.images:
        with Image.open(path) as img:
            print(f"{path.name}\t{recognizer.recognize(img)}")


if __name__ == "__main__":
    main()
