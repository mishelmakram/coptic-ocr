"""Export a trained checkpoint for the installed program, which reads with ONNX Runtime
instead of PyTorch:

    python tools/export_onnx.py models/coptic-crnn-v4/best.pt

writes ``model.onnx`` (the network) and ``model.json`` (its letters) beside the checkpoint,
then checks that both readers agree on random lines.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from copticocr.recog.charset import Charset  # noqa: E402
from copticocr.recog.lines import HEIGHT  # noqa: E402
from copticocr.recog.model import CRNN  # noqa: E402


def export(checkpoint: Path) -> Path:
    state = torch.load(checkpoint, map_location="cpu")
    model = CRNN(len(Charset(state["symbols"])), state["hidden"]).eval()
    model.load_state_dict(state["model"])
    out = checkpoint.with_name("model.onnx")
    torch.onnx.export(model, torch.rand(2, 1, HEIGHT, 256), str(out), dynamo=False, opset_version=17,
                      input_names=["images"], output_names=["logits"],
                      dynamic_axes={"images": {0: "lines", 3: "width"}, "logits": {0: "lines", 1: "frames"}})
    out.with_suffix(".json").write_text(json.dumps(
        {"symbols": state["symbols"], "script": state.get("script", "coptic"), "from": checkpoint.parent.name},
        ensure_ascii=False), encoding="utf-8")
    return out


def check(checkpoint: Path, onnx_path: Path) -> float:
    import onnxruntime as ort

    state = torch.load(checkpoint, map_location="cpu")
    model = CRNN(len(Charset(state["symbols"])), state["hidden"]).eval()
    model.load_state_dict(state["model"])
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    worst = 0.0
    for width in (64, 448, 1600):
        images = np.random.rand(3, 1, HEIGHT, width).astype(np.float32)
        with torch.no_grad():
            expected = model(torch.from_numpy(images)).numpy()
        got = session.run(None, {"images": images})[0]
        worst = max(worst, float(np.abs(expected - got).max()))
    return worst


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoints", nargs="+", type=Path)
    args = parser.parse_args(argv)
    for checkpoint in args.checkpoints:
        out = export(checkpoint)
        print(f"{out}  ({out.stat().st_size / 2 ** 20:.1f} MB), largest difference {check(checkpoint, out):.2e}")


if __name__ == "__main__":
    main()
