"""Train the Coptic line recognizer.

    python -m copticocr.recog.train --data data/synth/v1 --out models/coptic-crnn

Saves ``best.pt`` (lowest validation CER) and ``last.pt`` in ``--out``.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader

from .charset import Charset
from .dataset import LineDataset, WidthBucketSampler, collate, read_labels
from .metrics import cer
from .model import CRNN, STRIDE


def frame_lengths(widths: torch.Tensor, frames: int) -> torch.Tensor:
    return torch.clamp(torch.div(widths, STRIDE, rounding_mode="floor"), max=frames)


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


def save(path: Path, model, charset, args, epoch: int, val_cer: float) -> None:
    torch.save({
        "model": model.state_dict(),
        "symbols": charset.symbols,
        "hidden": args.hidden,
        "epoch": epoch,
        "val_cer": val_cer,
    }, path)


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", nargs="+", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--hidden", type=int, default=256)
    parser.add_argument("--val-size", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--resume", type=Path, help="checkpoint to start from")
    parser.add_argument("--limit", type=int, help="use only this many training lines (smoke tests)")
    args = parser.parse_args(argv)

    torch.manual_seed(0)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    charset = Charset.coptic()

    items = [item for root in args.data for item in read_labels(root)]
    random.Random(0).shuffle(items)
    val_items, train_items = items[:args.val_size], items[args.val_size:]
    if args.limit:
        train_items = train_items[:args.limit]
    print(f"device {device}, {len(train_items)} train / {len(val_items)} val lines, {len(charset)} classes")

    train_set = LineDataset(train_items, charset)
    val_set = LineDataset(val_items, charset)
    loader_args = dict(collate_fn=collate, num_workers=args.workers, pin_memory=True,
                       persistent_workers=args.workers > 0)
    train_loader = DataLoader(train_set, batch_sampler=WidthBucketSampler(
        [len(text) for _, text in train_items], args.batch_size), **loader_args)
    val_loader = DataLoader(val_set, batch_sampler=WidthBucketSampler(
        [len(text) for _, text in val_items], args.batch_size), **loader_args)

    model = CRNN(len(charset), args.hidden).to(device)
    if args.resume:
        model.load_state_dict(torch.load(args.resume, map_location=device)["model"])
    print(f"{sum(p.numel() for p in model.parameters()) / 1e6:.1f}M parameters")

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer, max_lr=args.lr, total_steps=args.epochs * len(train_loader), pct_start=0.1)
    ctc = nn.CTCLoss(blank=0, zero_infinity=True)
    scaler = torch.amp.GradScaler(enabled=device.type == "cuda")

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "config.json").write_text(json.dumps(
        {k: str(v) for k, v in vars(args).items()}, indent=2), encoding="utf-8")
    best = float("inf")
    for epoch in range(1, args.epochs + 1):
        started, running = time.time(), 0.0
        for step, (images, widths, targets, lengths, _) in enumerate(train_loader, 1):
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
                print(f"epoch {epoch} step {step}/{len(train_loader)} loss {running / 200:.3f}", flush=True)
                running = 0.0

        val_cer = evaluate(model, val_loader, charset, device, show=3)
        print(f"epoch {epoch} done in {time.time() - started:.0f}s, val CER {val_cer:.2%}", flush=True)
        save(args.out / "last.pt", model, charset, args, epoch, val_cer)
        if val_cer < best:
            best = val_cer
            save(args.out / "best.pt", model, charset, args, epoch, val_cer)


if __name__ == "__main__":
    main()
