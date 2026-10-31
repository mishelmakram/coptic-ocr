"""Page recognition on a background thread, so the window stays responsive."""

from __future__ import annotations

import queue
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..pipeline import Document, Engine


class Reader(QThread):
    """Reads queued pages one at a time with its own copy of the document."""

    ready = Signal(str)            # device the model runs on
    failed_to_start = Signal(str)
    page_read = Signal(int, object)  # page index, PageResult
    page_failed = Signal(int, str)

    def __init__(self, paths: list[Path], checkpoint: Path, device: str | None):
        super().__init__()
        self.paths, self.checkpoint, self.device = paths, checkpoint, device
        self._queue: queue.Queue[int | None] = queue.Queue()

    def submit(self, indices: list[int]) -> None:
        for index in indices:
            self._queue.put(index)

    def cancel(self) -> None:
        """Forget the pages not started yet."""
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    def stop(self) -> None:
        self.cancel()
        self._queue.put(None)
        self.wait()

    def run(self) -> None:
        try:
            engine = Engine(self.checkpoint, self.device)
        except Exception as error:  # noqa: BLE001 - shown to the user
            self.failed_to_start.emit(str(error))
            return
        self.ready.emit(engine.device)
        doc = Document(self.paths)
        try:
            while (index := self._queue.get()) is not None:
                try:
                    self.page_read.emit(index, engine.read(doc.page_image(index)))
                except Exception as error:  # noqa: BLE001
                    self.page_failed.emit(index, str(error))
        finally:
            doc.close()
