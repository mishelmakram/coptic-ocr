"""Train the Coptic line recognizer.

    python -m copticocr.recog.train --data data/packed/synth-v1v2 --out models/coptic-crnn

``--data`` is either one packed dataset (see ``copticocr.recog.packed``, much
faster) or folders with ``labels.tsv``. Writes to ``--out``:

- ``best.pt``: lowest validation CER, for inference
- ``last.pt``: latest weights, for inference
- ``state.pt``: everything needed to continue an interrupted run (``--resume``)
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import ConcatDataset, DataLoader, Subset

from .charset import Charset
from .dataset import LineDataset, WidthBucketSampler, collate, read_labels
from .metrics import cer
from .model import CRNN, STRIDE
from .packed import PackedLineDataset, is_packed


def frame_lengths(widths: torch.Tensor, frames: int) -> torch.Tensor:
    return torch.clamp(torch.div(widths, STRIDE, rounding_mode="floor"), max=frames)


def keep_system_awake() -> None:
    """Stop Windows from idle-sleeping until this process exits (no settings change)."""
    if sys.platform == "win32":
        import ctypes

        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


def load_set(root: Path, charset):
    """(dataset, approximate widths) of one packed dataset or ``labels.tsv`` folder."""
    if is_packed(root):
        widths = np.load(root / "widths.npy")
        return PackedLineDataset(root, list(range(len(widths))), charset), [int(w) for w in widths]
    items = read_labels(root)
    # Label length is a good proxy for line width.
    return LineDataset(items, charset), [len(t) * 19 for _, t in items]  # ~19 px per character at line height 48


def subset(data, widths, indices):
    return Subset(data, indices), [widths[i] for i in indices]


def build_datasets(args, charset):
    """(train set, val set, train widths, val widths); widths drive batch bucketing.

    Each ``--data`` entry may end in ``@K`` to use only K random lines of it,
    and/or ``*N`` to repeat it N times (oversampling scarce real lines), as in
    ``data/packed/synth@150000`` or ``data/packed/nt*3``. Without ``--val``,
    ``--val-size`` lines of the first entry are held out.
    """
    train_sets, train_widths = [], []
    val_sets, val_widths = [], []
    for k, spec in enumerate(args.data):
        spec, _, repeat = str(spec).partition("*")
        path, _, take = spec.partition("@")
        data, widths = load_set(Path(path), charset)
        order = list(range(len(widths)))
        if take:
            order = sorted(random.Random(k).sample(order, min(int(take), len(order))))
        if k == 0 and not args.val:
            random.Random(0).shuffle(order)
            held, order = order[:args.val_size], sorted(order[args.val_size:])
            v, vw = subset(data, widths, held)
            val_sets.append(v)
            val_widths += vw
        if args.limit:
            order = order[:args.limit]
        t, tw = subset(data, widths, order)
        for _ in range(int(repeat or 1)):
            train_sets.append(t)
            train_widths += tw
    for root in args.val or []:
        v, vw = load_set(root, charset)
        val_sets.append(v)
        val_widths += vw
    return ConcatDataset(train_sets), ConcatDataset(val_sets), train_widths, val_widths


@torch.no_grad()
def evaluate(model, loader, charset, device, show: int = 0) -> float:
    model.eval()
    refs, hyps = [], []
    for images, widths, _, _, texts in loader:
        logits = model(images.to(device, non_blocking=True))
        best = logits.argmax(-1).cpu()
        for row, n, text in zip(best, frame_lengths(widths, logits.shape[1]), texts):
            hyps.append(charset.decode(row[:n]))
            refs.append(text)
    for ref, hyp in list(zip(refs, hyps))[:show]:
        print(f"  ref: {ref}\n  hyp: {hyp}")
    model.train()
    return cer(refs, hyps)


def save_weights(path: Path, model, charset, args, epoch: int, val_cer: float | None) -> None:
    torch.save({
        "model": model.state_dict(),
        "symbols": charset.symbols,
        "script": charset.script,
        "hidden": args.hidden,
        "epoch": epoch,
        "val_cer": val_cer,
    }, path)


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", nargs="+", required=True, help="datasets, each optionally PATH@K (K random lines) and/or *N (repeat N times)")
    parser.add_argument("--val", nargs="+", type=Path, help="validation sets (default: held out from the first --data)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=4)
    # 32 keeps a 6 GB laptop GPU well inside its memory; spilling into shared memory is very slow.
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--hidden", type=int, default=256)
    parser.add_argument("--val-size", type=int, default=2000)
    # Each Windows loader process holds its own copy of torch (~1 GB); packed data needs none.
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--save-every", type=int, default=2000, help="steps between resumable checkpoints")
    parser.add_argument("--resume", action="store_true", help="continue from --out/state.pt")
    parser.add_argument("--init", type=Path, help="start from these weights (fine-tuning)")
    parser.add_argument("--limit", type=int, help="use only this many training lines (smoke tests)")
    parser.add_argument("--script", choices=["coptic", "arabic"], default="coptic")
    args = parser.parse_args(argv)

    keep_system_awake()
    torch.manual_seed(0)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    charset = Charset.for_script(args.script)

    train_set, val_set, train_widths, val_widths = build_datasets(args, charset)
    print(f"device {device}, {len(train_set)} train / {len(val_set)} val lines, {len(charset)} classes")
    loader_args = dict(collate_fn=collate, num_workers=args.workers, pin_memory=True,
                       persistent_workers=args.workers > 0)
    sampler = WidthBucketSampler(train_widths, args.batch_size)
    train_loader = DataLoader(train_set, batch_sampler=sampler, **loader_args)
    val_loader = DataLoader(val_set, batch_sampler=WidthBucketSampler(val_widths, args.batch_size), **loader_args)

    model = CRNN(len(charset), args.hidden).to(device)
    if args.init:
        model.load_state_dict(torch.load(args.init, map_location=device)["model"])
    print(f"{sum(p.numel() for p in model.parameters()) / 1e6:.1f}M parameters")

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer, max_lr=args.lr, total_steps=args.epochs * len(train_loader), pct_start=0.1)
    ctc = nn.CTCLoss(blank=0, zero_infinity=True)
    scaler = torch.amp.GradScaler(enabled=device.type == "cuda")

    args.out.mkdir(parents=True, exist_ok=True)
    state_path = args.out / "state.pt"
    start_epoch, skip, best = 1, 0, float("inf")
    if args.resume and state_path.exists():
        state = torch.load(state_path, map_location=device)
        model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        scheduler.load_state_dict(state["scheduler"])
        scaler.load_state_dict(state["scaler"])
        start_epoch, skip, best = state["epoch"], state["step"], state["best"]
        print(f"resuming at epoch {start_epoch}, step {skip}")
    (args.out / "config.json").write_text(json.dumps(
        {k: str(v) for k, v in vars(args).items()}, indent=2), encoding="utf-8")

    def save_state(epoch: int, step: int) -> None:
        torch.save({"model": model.state_dict(), "optimizer": optimizer.state_dict(),
                    "scheduler": scheduler.state_dict(), "scaler": scaler.state_dict(),
                    "epoch": epoch, "step": step, "best": best}, state_path)
        save_weights(args.out / "last.pt", model, charset, args, epoch, None)

    for epoch in range(start_epoch, args.epochs + 1):
        sampler.epoch = epoch - 1  # same batch order as an uninterrupted run
        sampler.skip = skip
        started, running, tick = time.time(), 0.0, time.time()
        for step, (images, widths, targets, lengths, _) in enumerate(train_loader, skip + 1):
            images = images.to(device, non_blocking=True)
            with torch.autocast(device.type, enabled=device.type == "cuda"):
                logits = model(images)
            log_probs = logits.float().log_softmax(-1).transpose(0, 1)  # (T, B, C) for CTC
            loss = ctc(log_probs, targets, frame_lengths(widths, logits.shape[1]), lengths)

            optimizer.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()

            running += loss.item()
            if step % 200 == 0:
                rate = (time.time() - tick) / 200
                print(f"epoch {epoch} step {step}/{len(train_loader)} loss {running / 200:.3f} "
                      f"{rate * 1000:.0f} ms/step", flush=True)
                running, tick = 0.0, time.time()
            if step % args.save_every == 0:
                save_state(epoch, step)
        skip = 0

        val_cer = evaluate(model, val_loader, charset, device, show=3)
        print(f"epoch {epoch} done in {time.time() - started:.0f}s, val CER {val_cer:.2%}", flush=True)
        if val_cer < best:
            best = val_cer
            save_weights(args.out / "best.pt", model, charset, args, epoch, val_cer)
        save_state(epoch + 1, 0)
    print("training finished", flush=True)


if __name__ == "__main__":
    main()
