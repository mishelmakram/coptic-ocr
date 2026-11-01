# Building the Windows program

The installed program reads with ONNX Runtime, not PyTorch, so it is about 160 MB instead of
several GB. Build it from a separate environment that has no PyTorch:

```
python -m venv .venv-build
.venv-build\Scripts\python -m pip install PySide6-Essentials pymupdf numpy pillow scipy potracer python-docx onnxruntime pyinstaller
```

1. Export the models (from the training environment, which has PyTorch):
   `python tools/export_onnx.py models/coptic-crnn-v4/best.pt models/arabic-crnn-v2/best.pt`
   (it checks that both readers agree). Set the folders in `MODELS` in `build.py` when they change.
2. After changing the icon's drawing, run `python tools/make_icon.py`.
3. `.venv-build\Scripts\python packaging\build.py` writes to `dist/`:
   - `CopticOCR/`: the program folder
   - `CopticOCR-<version>-portable.zip`: runs from any folder or USB stick. Its settings stay in a
     `settings` folder beside the program because of the `portable` file there.
   - `CopticOCR-<version>-setup.exe`: the installer, when [Inno Setup 6](https://jrsoftware.org/isinfo.php)
     is installed (`packaging/installer.iss`).

The version comes from `pyproject.toml`. The program is not code-signed, so Windows SmartScreen
warns the first time it is run.
