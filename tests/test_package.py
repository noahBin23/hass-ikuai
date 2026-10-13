"""Validate distributable contents without any external services."""

import importlib.util
import shutil
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ikuai_package", ROOT / "scripts/package.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def test_archive_is_installable_and_keeps_attribution(tmp_path):
    output = tmp_path / "ikuai.zip"
    count = package.package(output)
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert len(names) == count
        assert all(name.startswith("custom_components/ikuai/") for name in names)
        assert "custom_components/ikuai/manifest.json" in names
        assert "custom_components/ikuai/brand/icon.png" in names
        assert "custom_components/ikuai/LICENSE" in names
        assert "custom_components/ikuai/NOTICE" in names
        assert not any(".env" in name or "tests/" in name for name in names)
    with pytest.raises(FileExistsError):
        package.package(output)


def test_private_or_unexpected_files_cannot_enter_package(tmp_path):
    destination = tmp_path / "custom_components/ikuai"
    shutil.copytree(ROOT / "custom_components/ikuai", destination)
    (destination / ".env").write_text("FAKE_TOKEN=not-a-real-credential\n")
    with pytest.raises(ValueError, match="Unexpected integration file"):
        package.integration_files(tmp_path)
