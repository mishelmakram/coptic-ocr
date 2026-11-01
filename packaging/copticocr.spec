# PyInstaller recipe for the installed and portable program: python packaging/build.py
from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src" / "copticocr"

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=[(str(SRC / "assets"), "copticocr/assets"), (str(SRC / "legacy" / "maps"), "copticocr/legacy/maps")],
    hiddenimports=["copticocr.recog.reader"],
    # Training and the PyTorch reader stay out: the program reads with ONNX Runtime.
    excludes=["torch", "torchvision", "tkinter", "matplotlib", "IPython", "pytest", "rapidfuzz", "fontTools.ttx",
              "onnx", "sympy", "pymupdf.layout", "pymupdf4llm"],  # with PyMuPDF's optional layout add-on
    noarchive=False,
)
# Unused weight: software OpenGL (nothing is drawn with OpenGL) and Qt's other languages.
a.binaries = [b for b in a.binaries if not b[0].endswith("opengl32sw.dll")]
a.datas = [d for d in a.datas if "translations" not in d[0].replace("\\", "/")
           or Path(d[0]).name.split("_")[-1].split(".")[0] in ("ar", "en")]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="CopticOCR", icon=str(SRC / "assets" / "copticocr.ico"),
          console=False, upx=False, version=str(ROOT / "packaging" / "version.txt"))
coll = COLLECT(exe, a.binaries, a.datas, name="CopticOCR", upx=False)
