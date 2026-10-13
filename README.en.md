# iKuai for Home Assistant

[简体中文](README.md) | [English](README.en.md)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=noahBin23&repository=hass-ikuai&category=integration)
[![Release](https://img.shields.io/github/v/release/noahBin23/hass-ikuai)](https://github.com/noahBin23/hass-ikuai/releases)
[![HACS validation](https://github.com/noahBin23/hass-ikuai/actions/workflows/action.yml/badge.svg)](https://github.com/noahBin23/hass-ikuai/actions/workflows/action.yml)
[![hassfest](https://github.com/noahBin23/hass-ikuai/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/noahBin23/hass-ikuai/actions/workflows/hassfest.yaml)

Monitor your iKuai router in Home Assistant. **For iKuai 4.x, this integration uses the native REST API and an API token to provide read-only sensors.**

This repository is maintained as a fork of [dscao/ikuai](https://github.com/dscao/ikuai). It preserves the original `ikuai` integration domain and entity unique IDs to support upgrades from existing installations.

## Compatibility

| Item | Support |
| --- | --- |
| Home Assistant | 2026.10.0 or later; this release was tested on 2026.10.0 |
| iKuai 4.x | Verified on `4.0.313 x64 Build202609281457`; API compatibility with other 4.x firmware versions must be checked separately |
| iKuai 3.x | Legacy username/password and cookie authentication retained; simulated protocol regression tests pass, but physical 3.x hardware has not been retested |
| Installation | HACS custom repository or manual installation |
| Polling interval | 10 seconds by default; configurable in the integration options, with a minimum of 5 seconds |

### The 13 sensor types available on 4.x

| Sensor | Unit / meaning |
| --- | --- |
| CPU | Usage, % |
| CPU temperature | °C |
| Memory | Usage, % |
| Online clients | Count |
| Online access points | Count |
| Connections | Count |
| Upload speed | MB/s |
| Download speed | MB/s |
| Total upload | GB |
| Total download | GB |
| WAN IPv4 | IPv4 address of the WAN interface identified by the unique default route |
| Device uptime | Formatted duration |
| WAN uptime | Formatted duration |

Traffic conversion follows the original integration: rates are divided by `1024²`, and totals by `1024³`. Totals come from the router; **they are not monthly totals calculated by Home Assistant**. Uptime values are duration strings, not timestamps.

On 4.x, the integration does not expose MAC control, trackers, router reboot, WAN reconnect, ARP binding switches, smart traffic control, IPv6 addresses or custom RPC switches. It does not query MAC rules or client details, and it does not send write requests to the 4.x API. The original 3.x features remain in a separate compatibility implementation.

## Install through HACS

This repository supports installation as a **HACS custom repository**. It is not included in the HACS default repository list.

1. Open HACS and select **Custom repositories** from its menu.
2. Add `https://github.com/noahBin23/hass-ikuai` with the type **Integration**.
3. Find **iKuai** and download the latest stable release.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration** and search for **iKuai**.

You can also use [this HACS link](https://my.home-assistant.io/redirect/hacs_repository/?owner=noahBin23&repository=hass-ikuai&category=integration) to open the repository.

### Manual installation

Download `ikuai-<version>.zip` from [Releases](https://github.com/noahBin23/hass-ikuai/releases) and extract it into your Home Assistant configuration directory. The resulting path must be:

```text
<config>/custom_components/ikuai/manifest.json
```

The archive already includes the `custom_components/ikuai/` directory structure. Back up the existing integration directory before replacing it, then restart Home Assistant. Do not copy the entire GitHub repository into `custom_components`.

## Configure iKuai 4.x

1. Enable the 4.x API on your router and obtain an API token. The location of these settings and the available permission options may vary by firmware; refer to your device's administration interface.
2. Make sure the **host or container running Home Assistant** can reach the router's management address.
3. When adding the integration, select **iKuai 4.x (API token)** and enter the management address, token and certificate verification setting.

Example address: `https://router.example:8443`. An API root ending in `/api/v4.0` is also accepted. URLs containing a username, password or query parameters are rejected.

Only read access to the following endpoints is required:

```text
GET /api/v4.0/monitoring/system
GET /api/v4.0/interfaces/wan-config
GET /api/v4.0/monitoring/interfaces-status
GET /api/v4.0/monitoring/wireless-statistics
```

HTTPS certificate verification is enabled by default. Disable it only when you have confirmed that you are connecting to a trusted device with a self-signed certificate. This setting affects only connections made by this integration.

An invalid token prompts reauthentication. You can also select **Reconfigure** from the integration menu to change the connection address or token. Changing the connection address preserves the existing device and entity identities. Never include your token in issues, screenshots or logs.

## Upgrade from an older version or the upstream repository

1. Back up the existing integration directory and your Home Assistant configuration.
2. Stop using the original `dscao/ikuai` repository in HACS to manage this integration, then add this repository. Both repositories use the same `ikuai` directory and must not manage its updates at the same time. **Keep the existing iKuai configuration entry under Home Assistant's Devices & services; do not delete it and add it again.**
3. If you use Const Tracker on 3.x, save your personal `DEVICE_TRACKERS` configuration separately: updating replaces `const.py`. Prefer the existing UI configuration method where possible.
4. Install this repository's version and restart Home Assistant. After upgrading your router to 4.x, select **Reconfigure** from the existing integration entry's menu and enter the new management address and token.
5. Check the sensor states and your existing disabled-entity settings. Enable the device and WAN uptime sensors in their entity settings if you need them.
6. Old control entities that are no longer loaded on 4.x may remain in the entity registry. Remove references to them from dashboards and automations before deleting the obsolete records in entity settings. The integration does not automatically delete registry entries, statistics or history, and it does not change the router's MAC rules.

## Troubleshooting

- **All sensors are unavailable:** Check connectivity from Home Assistant to the management address, whether the API is enabled, the token and certificate settings.
- **Only WAN or access point sensors are unavailable:** Check read permissions for the corresponding endpoints and the firmware's response data. An endpoint failure should not affect valid readings such as CPU usage.
- **The WAN address is empty:** The default WAN must be uniquely identifiable. The integration does not guess an address when there are multiple default routes or the interface is disconnected.
- **Old buttons or MAC controls are still visible:** Make sure Home Assistant has restarted and loaded the new version, then follow the upgrade steps to clean up obsolete registry entries.
- **Entity IDs changed after updating:** Check whether the configuration entry was deleted and recreated, or whether two repositories are managing the same integration directory. Report sanitized details in [Issues](https://github.com/noahBin23/hass-ikuai/issues).

When reporting a problem, include the Home Assistant version, router firmware version, integration version and a sanitized error summary. Do not upload complete `.storage` files, configuration backups, tokens, cookies, real MAC addresses or responses containing credentials.

## Development and validation

Use Python 3.14:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m ruff check custom_components tests scripts
python -m ruff format --check custom_components tests scripts
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider
python scripts/package.py
python scripts/package.py --output dist/ikuai-2026.10.13.4.zip
```

Tests connect only to local mock services. They cover Bearer authentication, pagination, missing values, partial failures, blocking write requests, configuration flows, reauthentication, entity identity, loading and unloading, and preservation of disabled-entity settings. The packaging script includes only the installable integration directory and refuses to overwrite existing files. HACS and hassfest validation use the repository's existing GitHub Actions workflows.

```text
custom_components/ikuai/  Integration runtime code, translations and brand assets
tests/                   Fictional data and local mock-service tests
scripts/                 Local validation and release packaging
```

Published files do not include production configuration, real credentials, deployment scripts or private screenshots.

## Credits and license

- The integration is based on [dscao/ikuai](https://github.com/dscao/ikuai) and distributed under [Apache-2.0](LICENSE). See [CHANGELOG.md](CHANGELOG.md) for changes and [NOTICE](NOTICE) for attribution.
- The 4.x API implementation references [iKuai-Console OpenAPI](https://github.com/adminlby/iKuai-Console/tree/main/openapi).
- Brand assets come from [Home Assistant Brands](https://github.com/home-assistant/brands/tree/master/custom_integrations/ikuai) and are used to identify the connected product. Trademarks belong to their respective owners. This is not an official iKuai project.
