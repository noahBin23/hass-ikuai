"""Validate the HACS package; write a new versioned archive only with --output."""

from __future__ import annotations

import argparse
import ast
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "ikuai"
SOURCE = ROOT / "custom_components" / DOMAIN


def integration_files(root: Path = ROOT) -> list[Path]:
    """Only allow installable source, translations and PNG brand assets."""
    source = root / "custom_components" / DOMAIN
    files = []
    for item in sorted(source.rglob("*")):
        if not item.is_file() or "__pycache__" in item.parts:
            continue
        relative = item.relative_to(source)
        allowed = (
            len(relative.parts) == 1
            and (item.suffix in {".py", ".json"} or item.name in {"LICENSE", "NOTICE"})
            or relative.parts[0] == "translations"
            and item.suffix == ".json"
            or relative.parts[0] == "brand"
            and item.suffix == ".png"
        )
        if not allowed or item.is_symlink():
            raise ValueError(f"Unexpected integration file: {relative}")
        files.append(item)
    return files


def validate(root: Path = ROOT) -> tuple[str, list[Path]]:
    """Check the repository shape and parse every installable source file."""
    source = root / "custom_components" / DOMAIN
    directories = sorted(p.name for p in (root / "custom_components").iterdir() if p.is_dir())
    assert directories == [DOMAIN], "HACS repository must contain one integration"
    manifest = json.loads((source / "manifest.json").read_text())
    assert manifest["domain"] == DOMAIN
    for key in ("name", "version", "documentation", "issue_tracker", "codeowners"):
        assert manifest.get(key), f"Missing manifest field: {key}"
    assert manifest["config_flow"] is True
    hacs = json.loads((root / "hacs.json").read_text())
    assert hacs["name"] and hacs["homeassistant"] == "2026.10.0"
    assert not hacs.get("content_in_root") and not hacs.get("zip_release")
    assert (root / "README.md").is_file() and (root / "LICENSE").is_file()
    assert (source / "brand/icon.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    files = integration_files(root)
    for item in files:
        if item.suffix == ".py":
            ast.parse(item.read_text(), filename=str(item.relative_to(root)))
        elif item.suffix == ".json":
            json.loads(item.read_text())
    return manifest["version"], files


def package(output: Path, root: Path = ROOT) -> int:
    """Create an archive with the manual-install custom_components/ikuai prefix."""
    _, files = validate(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in files:
            archive.write(item, item.relative_to(root))
    return len(files)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, help="Create a new ZIP; existing files are never replaced"
    )
    args = parser.parse_args()
    version, files = validate()
    count = package(args.output) if args.output else len(files)
    print(json.dumps({"version": version, "files": count, "created": bool(args.output)}))


if __name__ == "__main__":
    main()
