"""Keeping the program up to date from its releases on GitHub.

The installed program looks for a newer release now and then, downloads its installer in the
background, checks it against the digest GitHub publishes, and installs it silently when the
program is closed (or at once, if asked). The portable copy cannot install itself, and is only
told that a newer version is out.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Callable

from .. import __version__

REPO = "mishelmakram/coptic-ocr"
# Where the latest release is described; COPTICOCR_UPDATE_FEED points it at a test file instead.
LATEST = os.environ.get("COPTICOCR_UPDATE_FEED", f"https://api.github.com/repos/{REPO}/releases/latest")
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
CHECK_EVERY = 24 * 3600  # seconds between looks for a new release
CHUNK = 1 << 20


def version_numbers(text: str) -> tuple[int, ...]:
    """(0, 2, 1) for "v0.2.1" or "0.2.1"."""
    match = re.match(r"\d+(\.\d+)*", text.strip().lstrip("vV"))
    return tuple(int(part) for part in match.group().split(".")) if match else ()


def is_newer(tag: str, current: str = __version__) -> bool:
    return version_numbers(tag) > version_numbers(current)


def installer_asset(release: dict) -> dict | None:
    """The release's installer (its ``-setup.exe``), if it has one."""
    return next((a for a in release.get("assets", []) if a.get("name", "").endswith("-setup.exe")), None)


def latest_release(timeout: float = 15) -> dict:
    request = urllib.request.Request(LATEST, headers={"Accept": "application/vnd.github+json",
                                                      "User-Agent": f"CopticOCR/{__version__}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def installed_copy() -> bool:
    """Whether this is the copy the installer put in place (it can then be updated by the next one)."""
    home = Path(sys.executable).parent
    return bool(getattr(sys, "frozen", False)) and (home / "unins000.exe").exists() \
        and not (home / "portable").exists()


def updates_folder() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "CopticOCR" / "updates"


def download(asset: dict, folder: Path, progress: Callable[[int, int], bool] | None = None) -> Path:
    """The installer saved in ``folder``, checked against the SHA-256 GitHub gives for it.

    Raises ValueError if the file is not what was published, and leaves nothing behind then.
    """
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / asset["name"]
    expected = (asset.get("digest") or "").removeprefix("sha256:").lower()
    if target.exists() and expected and _sha256(target) == expected:
        return target  # already downloaded
    partial = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    request = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": f"CopticOCR/{__version__}"})
    total, done = int(asset.get("size") or 0), 0
    try:
        with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as out:
            while chunk := response.read(CHUNK):
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress is not None and progress(done, total) is False:
                    raise InterruptedError
        if not expected or digest.hexdigest() != expected or (total and done != total):
            raise ValueError("the downloaded installer does not match the release")
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    for old in folder.glob("*-setup.exe"):  # earlier updates, already installed
        if old != target:
            old.unlink(missing_ok=True)
    return target


def clear_installed(folder: Path | None = None) -> None:
    """Remove downloaded installers of this version or older: they have been installed."""
    for setup in (folder or updates_folder()).glob("*-setup.exe"):
        number = re.search(r"-(\d+(?:\.\d+)*)-setup\.exe$", setup.name)
        if number and not is_newer(number.group(1)):
            setup.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def install(setup: Path, relaunch: bool) -> None:
    """Start the installer silently, for the same scope as this copy; the caller then quits.

    The installer waits for this program to close (it would otherwise find its files in use),
    and with ``relaunch`` starts the new version when it is done.
    """
    home = Path(sys.executable).parent
    local = Path(os.environ.get("LOCALAPPDATA", "")).resolve()
    scope = "/CURRENTUSER" if local in home.resolve().parents else "/ALLUSERS"
    arguments = [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", scope,
                 f"/DIR={home}", f"/RELAUNCH={1 if relaunch else 0}"]
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(arguments, creationflags=flags, close_fds=True)
