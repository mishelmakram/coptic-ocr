"""Write the program's icon file (for the .exe, the installer and shortcuts) from the same
drawing the window uses:

    python tools/make_icon.py        -> src/copticocr/assets/copticocr.ico
"""

import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer  # noqa: E402
from PySide6.QtGui import QFontDatabase, QGuiApplication  # noqa: E402

from copticocr.app import icons, theme  # noqa: E402
from copticocr.export import bundled_font  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "src" / "copticocr" / "assets" / "copticocr.ico"


def main() -> None:
    app = QGuiApplication([])  # noqa: F841 - fonts and painting need one
    family = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(str(bundled_font())))[0]
    images = []
    for size in icons.ICON_SIZES:
        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        icons.paint_tile(size, theme.LIGHT.accent, family).save(buffer, "PNG")
        images.append(Image.open(BytesIO(bytes(buffer.data()))).convert("RGBA"))
    images[-1].save(OUT, sizes=[(i.width, i.height) for i in images], append_images=images[:-1])
    images[-1].save(OUT.with_suffix(".png"))
    print(OUT, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
