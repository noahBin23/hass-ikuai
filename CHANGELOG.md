# Changelog

## 2026.10.13.4

First public release of the 4.x sensor-only implementation, based on the previously validated 2026.10.13.3 source.

- Add native iKuai 4.x REST / Bearer authentication and 13 sensor types.
- Keep 4.x read-only: no MAC control, tracker, reboot, WAN reconnect or undocumented controls.
- Preserve existing entity identifiers, configuration entries and user-disabled settings when reconfiguring the management address or token.
- Retain the legacy 3.x protocol separately; do not automatically delete old entity registry records or history.
- Update repository ownership, documentation and HACS metadata; include brand assets, Apache-2.0 attribution, isolated tests and release packaging.
- Normalize Python formatting and imports without changing the validated sensor behavior.

Compatibility: tested with Home Assistant 2026.10.0 and iKuai 4.0.313 x64. Other firmware versions are not claimed as verified.
