import hashlib

import pytest

from copticocr.app import update


def test_versions_compare_as_numbers():
    assert update.version_numbers("v0.10.2") == (0, 10, 2)
    assert update.is_newer("v0.10.0", "0.9.3")
    assert update.is_newer("0.2.0", "0.1.0")
    assert not update.is_newer("v0.1.0", "0.1.0")
    assert not update.is_newer("v0.1.0", "0.2.0")
    assert not update.is_newer("nightly", "0.1.0")


def test_the_installer_is_picked_from_the_release():
    release = {"assets": [{"name": "CopticOCR-0.2.0-portable.zip"}, {"name": "CopticOCR-0.2.0-setup.exe"}]}
    assert update.installer_asset(release)["name"] == "CopticOCR-0.2.0-setup.exe"
    assert update.installer_asset({"assets": []}) is None


def published(tmp_path, content: bytes, digest: str | None = None) -> dict:
    source = tmp_path / "source" / "CopticOCR-0.2.0-setup.exe"
    source.parent.mkdir()
    source.write_bytes(content)
    return {"name": source.name, "size": len(content), "browser_download_url": source.as_uri(),
            "digest": "sha256:" + (digest or hashlib.sha256(content).hexdigest())}


def test_the_download_is_kept_only_if_it_matches_the_release(tmp_path):
    folder = tmp_path / "updates"
    good = update.download(published(tmp_path, b"installer"), folder)
    assert good.read_bytes() == b"installer"

    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(ValueError):
        update.download(published(other, b"tampered", digest=hashlib.sha256(b"x").hexdigest()), folder / "2")
    assert not any((folder / "2").iterdir())  # nothing left behind


def test_installed_updates_are_cleared(tmp_path):
    for name in ("CopticOCR-0.0.9-setup.exe", f"CopticOCR-{update.__version__}-setup.exe", "CopticOCR-99.0.0-setup.exe"):
        (tmp_path / name).write_bytes(b"x")
    update.clear_installed(tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["CopticOCR-99.0.0-setup.exe"]
