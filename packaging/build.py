"""Build the Windows program: the folder, the portable zip and (with Inno Setup) the installer.

    .venv-build\Scripts\python packaging\build.py

Run from an environment without PyTorch (see packaging/README.md); the models must be exported
first with tools/export_onnx.py. Everything lands in dist/.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
APP = DIST / "CopticOCR"
MODELS = {"coptic": "coptic-crnn-v4", "arabic": "arabic-crnn-v2"}
ISCC = [Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"), Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        Path.home() / r"AppData\Local\Programs\Inno Setup 6\ISCC.exe"]


def version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def main() -> None:
    try:
        import torch  # noqa: F401
        sys.exit("Build from an environment without PyTorch (it would be bundled, 3 GB).")
    except ImportError:
        pass
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(DIST),
                    "--workpath", str(ROOT / "build"), str(ROOT / "packaging" / "copticocr.spec")], check=True)

    # Beside the program, where it looks for models/<script>-*/model.onnx.
    for name in MODELS.values():
        target = APP / "models" / name
        target.mkdir(parents=True, exist_ok=True)
        for file in ("model.onnx", "model.json"):
            shutil.copy2(ROOT / "models" / name / file, target / file)
        json.loads((target / "model.json").read_text(encoding="utf-8"))  # exported whole
    shutil.copy2(ROOT / "LICENSE", APP / "LICENSE.txt")

    portable = DIST / f"CopticOCR-{version()}-portable.zip"
    with zipfile.ZipFile(portable, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:
        for path in sorted(APP.rglob("*")):
            zip_file.write(path, Path("CopticOCR") / path.relative_to(APP))
        # Settings beside the program, not in the registry (see app/main.py).
        zip_file.writestr("CopticOCR/portable", "Settings are kept in the settings folder beside the program.\n")
    print(f"{portable}  {portable.stat().st_size / 2 ** 20:.0f} MB")

    iscc = next((p for p in ISCC if p.exists()), None)
    if iscc is None:
        print("Inno Setup 6 not found: the installer was not built.")
        return
    subprocess.run([str(iscc), f"/DAppVersion={version()}", str(ROOT / "packaging" / "installer.iss")], check=True)


if __name__ == "__main__":
    main()
