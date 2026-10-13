"""Load the real HA integration against a local fake router, without production access."""

from __future__ import annotations

from contextlib import AsyncExitStack
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web
from homeassistant import bootstrap, loader
from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from test_v4 import MAC, SYSTEM, router

from custom_components.ikuai import IKUAIDataUpdateCoordinator
from custom_components.ikuai.api_v4 import IkuaiV4AuthError, IkuaiV4Error
from custom_components.ikuai.config_flow import IkuaiConfigFlow, IkuaiOptionsFlowHandler
from custom_components.ikuai.const import (
    BUTTON_TYPES,
    CONF_API_TOKEN,
    CONF_CONNECTION_URL,
    CONF_VERIFY_SSL,
    SENSOR_TYPES,
    SWITCH_TYPES,
)


def entry(data):
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain="ikuai",
        title="Fake router",
        source="user",
        data=data,
        options={},
        unique_id="ikuai-http://router.example",
        discovery_keys=MappingProxyType({}),
        subentries_data=[],
    )


@pytest.mark.asyncio
async def test_reconfigure_preserves_identity_and_existing_data(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    flow = IkuaiConfigFlow()
    flow.hass = hass
    original = entry(
        {
            "host": "http://router.example",
            "username": "fake-user",
            "passwd": "fake-hash",
            "pas": "fake-base64",
            "tracker_config": {MAC: {"buffer": 3}},
        }
    )

    async def handle(request):
        return web.json_response({"code": 0, "results": SYSTEM})

    try:
        async with router(handle) as (api, url):
            with (
                patch.object(flow, "async_update_reload_and_abort") as update,
                patch(
                    "custom_components.ikuai.config_flow.async_get_clientsession",
                    return_value=api.session,
                ),
            ):
                await flow._async_v4_connection(
                    {
                        CONF_CONNECTION_URL: url,
                        CONF_API_TOKEN: "fake-test-token",
                        CONF_VERIFY_SSL: True,
                    },
                    original,
                    "reconfigure",
                )
                updates = update.call_args.kwargs["data_updates"]
                assert "host" not in updates and updates[CONF_CONNECTION_URL] == url
                assert original.data["tracker_config"] == {MAC: {"buffer": 3}}
                assert original.unique_id == "ikuai-http://router.example"
        form = await flow._async_v4_connection(None, original, "reconfigure")
        assert form["step_id"] == "reconfigure"
        assert "fake-hash" not in str(form) and "fake-test-token" not in str(form)
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("preexisting", [False, True])
async def test_real_ha_setup_entities_unload_and_reload(tmp_path, preexisting):
    custom = tmp_path / "custom_components"
    custom.mkdir()
    (custom / "ikuai").symlink_to(
        Path(__file__).resolve().parents[1] / "custom_components/ikuai", target_is_directory=True
    )
    hass = HomeAssistant(str(tmp_path))
    loader.async_setup(hass)
    hass.config_entries = ConfigEntries(hass, {})
    assert await bootstrap.async_load_base_functionality(hass)
    methods, paths = [], []

    async def handle(request):
        methods.append(request.method)
        p = request.path
        paths.append(p)
        if p.endswith("/monitoring/system"):
            payload = SYSTEM
        elif p.endswith("/monitoring/interfaces-status"):
            payload = {
                "iface_check": [
                    {"id": 1, "interface": "wan1", "result": "success", "ip_addr": "192.0.2.7"}
                ]
            }
        elif p.endswith("/monitoring/wireless-statistics"):
            payload = {"ap_status": {"ap_online": 2}}
        elif p.endswith("/interfaces/wan-config"):
            payload = {"total": 1, "data": [{"id": 1, "name": "wan1", "default_route": 1}]}
        else:
            payload = {
                "total": 1,
                "data": [{"id": 1, "mac": MAC, "enabled": "yes", "comment": "Fake camera"}],
            }
        return web.json_response({"code": 0, "results": payload})

    try:
        async with router(handle) as (api, url):
            with patch("custom_components.ikuai.async_get_clientsession", return_value=api.session):
                assert await async_setup_component(hass, "ikuai", {})
                cfg = entry(
                    {
                        "host": "http://router.example",
                        CONF_CONNECTION_URL: url,
                        CONF_API_TOKEN: "fake-test-token",
                        CONF_VERIFY_SSL: True,
                        "update_interval_seconds": 30,
                        "tracker_config": {MAC: {"buffer": 2}},
                    }
                )
                registry = er.async_get(hass)
                if preexisting:
                    with patch.object(
                        hass.config_entries, "async_setup", AsyncMock(return_value=True)
                    ):
                        await hass.config_entries.async_add(cfg)
                    for platform, kinds in (
                        ("sensor", SENSOR_TYPES),
                        ("button", BUTTON_TYPES),
                        ("switch", SWITCH_TYPES),
                    ):
                        for kind in kinds:
                            registry.async_get_or_create(
                                platform,
                                "ikuai",
                                f"ikuai_{kind}_http://router.example",
                                config_entry=cfg,
                            )
                    registry.async_get_or_create(
                        "switch",
                        "ikuai",
                        "ikuai_switch_http://router.example_020000000001",
                        config_entry=cfg,
                    )
                    old_ids = {
                        e.unique_id: e.entity_id
                        for e in registry.entities.values()
                        if e.config_entry_id == cfg.entry_id
                    }
                    assert await hass.config_entries.async_setup(cfg.entry_id)
                else:
                    await hass.config_entries.async_add(cfg)
                await hass.async_block_till_done()
                assert cfg.state is ConfigEntryState.LOADED
                assert hass.data["ikuai"][cfg.entry_id]["platforms"] == ["sensor"]
                before = {
                    e.unique_id: (e.entity_id, e.device_id)
                    for e in registry.entities.values()
                    if e.config_entry_id == cfg.entry_id
                }
                assert len(before) == (20 if preexisting else 13)
                if preexisting:
                    assert old_ids == {uid: eid for uid, (eid, _) in before.items()}
                else:
                    assert not any(
                        "wan6_ip" in uid
                        or "lan6_ip" in uid
                        or "restart" in uid
                        or "arp_filter" in uid
                        or "stream_control" in uid
                        for uid in before
                    )
                cpu_id = registry.async_get_entity_id(
                    "sensor", "ikuai", "ikuai_ikuai_cpu_http://router.example"
                )
                assert hass.states.get(cpu_id).state == "12.5"
                disabled_id = registry.async_get_entity_id(
                    "sensor", "ikuai", "ikuai_ikuai_uptime_http://router.example"
                )
                registry.async_update_entity(disabled_id, disabled_by=er.RegistryEntryDisabler.USER)
                assert await hass.config_entries.async_reload(cfg.entry_id)
                await hass.async_block_till_done()
                after = {
                    e.unique_id: (e.entity_id, e.device_id)
                    for e in registry.entities.values()
                    if e.config_entry_id == cfg.entry_id
                }
                assert before == after
                assert registry.async_get(disabled_id).disabled_by is er.RegistryEntryDisabler.USER
                assert await hass.config_entries.async_unload(cfg.entry_id)
                assert cfg.entry_id not in hass.data["ikuai"]
        assert methods and set(methods) == {"GET"}
        assert not any("mac-rules" in p or "clients-online" in p for p in paths)
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
async def test_flow_auth_errors_and_sensor_only_options(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    flow = IkuaiConfigFlow()
    flow.hass = hass

    async def handle(request):
        if request.path.endswith("/monitoring/system"):
            return web.json_response({"code": 3007}, status=200)
        return web.json_response(
            {
                "code": 0,
                "results": {
                    "total": 1,
                    "data": [
                        {"id": 1, "mac": MAC, "ip_addr": "192.0.2.1", "termname": "Fake phone"}
                    ],
                },
            }
        )

    try:
        async with router(handle) as (api, url), AsyncExitStack() as stack:
            stack.enter_context(
                patch(
                    "custom_components.ikuai.config_flow.async_get_clientsession",
                    return_value=api.session,
                )
            )
            form = await flow.async_step_v4(
                {CONF_CONNECTION_URL: url, CONF_API_TOKEN: "fake-token", CONF_VERIFY_SSL: True}
            )
            assert form["errors"] == {"base": "invalid_auth"}
            cfg = entry(
                {
                    "host": "http://router.example",
                    CONF_CONNECTION_URL: url,
                    CONF_API_TOKEN: "fake-token",
                }
            )
            options = IkuaiOptionsFlowHandler(cfg)
            options.hass = hass
            form = await options.async_step_init()
            assert form["step_id"] == "sensors"
            assert [str(key) for key in form["data_schema"].schema] == ["update_interval_seconds"]
            bad = await options.async_step_sensors({"update_interval_seconds": 4})
            assert bad["errors"] == {"update_interval_seconds": "interval_too_small"}
            saved = await options.async_step_sensors({"update_interval_seconds": 15})
            assert (
                saved["type"] == "create_entry" and saved["data"]["update_interval_seconds"] == 15
            )
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
async def test_coordinator_recovery_reauth_and_rejected_control(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    try:
        with patch("custom_components.ikuai.async_get_clientsession", return_value=None):
            coordinator = IKUAIDataUpdateCoordinator(
                hass,
                "http://router.example",
                "",
                "",
                "",
                30,
                {},
                {},
                api_token="fake-token",
                connection_url="http://127.0.0.1",
            )
        coordinator._fetcher.get_data = AsyncMock(
            side_effect=[IkuaiV4Error("offline"), {"ikuai_cpu": 12}]
        )
        await coordinator.async_refresh()
        assert not coordinator.last_update_success
        await coordinator.async_refresh()
        assert coordinator.last_update_success and coordinator.data["ikuai_cpu"] == 12
        coordinator._fetcher.get_data = AsyncMock(side_effect=IkuaiV4AuthError("invalid"))
        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()
        coordinator._fetcher.api.request = AsyncMock()
        for body in (
            {"func_name": "acl_mac", "action": "up", "param": {"id": "1"}},
            {"func_name": "reboot", "action": "up"},
        ):
            with pytest.raises(HomeAssistantError, match="sensor-only"):
                await coordinator.async_control_device(body)
        coordinator._fetcher.api.request.assert_not_awaited()
    finally:
        await hass.async_stop()
