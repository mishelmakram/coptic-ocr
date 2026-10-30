"""CRNN line recognizer: a CNN reads the line image into a sequence of
columns, a BiLSTM adds context, and CTC aligns the output with the text."""

from __future__ import annotations

import torch
from torch import nn

HEIGHT = 48  # input line height in pixels
STRIDE = 4   # image columns per output frame


def _conv(cin: int, cout: int, kernel=3, padding=1) -> list[nn.Module]:
    return [nn.Conv2d(cin, cout, kernel, padding=padding, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True)]


class CRNN(nn.Module):
    def __init__(self, num_classes: int, hidden: int = 256):
        super().__init__()
        self.cnn = nn.Sequential(
            *_conv(1, 64), nn.MaxPool2d(2),                              # 24 x W/2
            *_conv(64, 128), nn.MaxPool2d(2),                            # 12 x W/4
            *_conv(128, 256), *_conv(256, 256), nn.MaxPool2d((2, 1)),    # 6 x W/4
            *_conv(256, 384), *_conv(384, 384), nn.MaxPool2d((2, 1)),    # 3 x W/4
            *_conv(384, 384, kernel=(3, 1), padding=0),                  # 1 x W/4
            nn.Dropout2d(0.1),
        )
        self.rnn = nn.LSTM(384, hidden, num_layers=2, bidirectional=True, batch_first=True, dropout=0.2)
        self.head = nn.Linear(2 * hidden, num_classes)

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        """(B, 1, HEIGHT, W) -> logits (B, W / STRIDE, classes)."""
        features = self.cnn(images).squeeze(2).transpose(1, 2)
        features, _ = self.rnn(features)
        return self.head(features)
