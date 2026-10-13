# hass-ikuai repository conventions

This public repository maintains the `ikuai` Home Assistant integration. Keep its domain, config entry identity and existing entity unique IDs stable.

## Layout

- `custom_components/ikuai/`: installable integration only; keep 4.x sensor-only and retain the separate legacy 3.x implementation.
- `custom_components/ikuai/brand/`: upstream brand assets with attribution in `NOTICE`.
- `tests/`: protocol, configuration flow, entity lifecycle and packaging tests using fictional data and loopback HTTP servers only.
- `scripts/`: local validation and reproducible release packaging; never include production deployment or private connection helpers.
- `dist/`: locally generated versioned archives; ignored by Git and never automatically cleaned.
- `README.md` (Chinese), `README.en.md` (English), `CHANGELOG.md`, `LICENSE`, `NOTICE`, `hacs.json`, `pyproject.toml`, `requirements-dev.txt`: public documentation, attribution, installation metadata and developer tooling. Keep both README files linked and their installation steps, supported features and compatibility limits aligned.
- `.github/workflows/`: existing HACS and hassfest validation; workflow changes require explicit maintainer authorization.

## Rules

- No credentials, real hosts, MAC addresses, Home Assistant configuration, private reports, screenshots or backups in this repository.
- 4.x requests are read-only. Never add implicit control endpoints or remove users' registry entries/history during setup.
- Preserve upstream attribution and document compatibility limits. Do not describe HACS custom-repository support as inclusion in the default store.
- Keep release tags and `manifest.json` versions aligned. Release archives contain only the integration directory, without tests or tooling.
- Do not overwrite existing releases, rewrite Git history or deploy to a live Home Assistant instance as part of repository maintenance.

## Validation

Use Python 3.14 and the Home Assistant version pinned in `requirements-dev.txt`:

```sh
python -m pip install -r requirements-dev.txt
python -m ruff check custom_components tests scripts
python -m ruff format --check custom_components tests scripts
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider
python scripts/package.py
```

Packaging validates by default; `python scripts/package.py --output dist/ikuai-<version>.zip` creates a new archive and refuses to overwrite it. Run the existing GitHub HACS and hassfest workflows after publishing a commit.
