"""Open a line recognizer: an exported ``model.onnx`` (the installed program, no PyTorch) or a
training checkpoint ``best.pt`` (PyTorch)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from PIL import Image

from .charset import Charset
from .lines import STRIDE, batch


def open_recognizer(checkpoint: str | Path, device: str | None = None):
    if Path(checkpoint).suffix == ".onnx":
        return OnnxRecognizer(checkpoint)
    from .infer import Recognizer  # torch is slow to import

    return Recognizer(checkpoint, device)


class OnnxRecognizer:
    """The exported model run by ONNX Runtime on the processor, with all its cores. (Through
    DirectML a graphics card read no faster: the network's LSTM runs poorly there.)"""

    device = "cpu"

    def __init__(self, path: str | Path):
        import onnxruntime as ort

        path = Path(path)
        info = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        self.charset = Charset(info["symbols"], info.get("script", "coptic"))
        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, (os.cpu_count() or 2) - 1)
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")  # idle threads would starve the other reader
        self.session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])

    def recognize(self, image: Image.Image) -> str:
        return self.recognize_batch([image])[0][0]

    def recognize_batch(self, images: list[Image.Image]) -> list[tuple[str, list[float]]]:
        """(text, per-letter confidence) for each line image."""
        pixels, widths = batch(images, self.charset.rtl)
        logits = self.session.run(None, {"images": pixels})[0]
        logits = logits - logits.max(-1, keepdims=True)
        probs = np.exp(logits)
        probs /= probs.sum(-1, keepdims=True)
        index, best = probs.argmax(-1), probs.max(-1)
        results = []
        for i, width in enumerate(widths):
            n = min(width // STRIDE, probs.shape[1])
            results.append(self.charset.decode_scored(index[i, :n], best[i, :n]))
        return results
