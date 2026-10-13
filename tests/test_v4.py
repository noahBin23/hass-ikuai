"""Protocol and HA entity regressions; all HTTP goes to a local fake router."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest
from aiohttp import web

from custom_components.ikuai.api_v4 import (
    IkuaiV4AuthError,
    IkuaiV4Client,
    IkuaiV4Error,
    IkuaiV4Fetcher,
    IkuaiV4PermissionError,
    normalize_system,
    normalize_url,
    normalize_wan,
)
from custom_components.ikuai.button import IKUAIButton
from custom_components.ikuai.button import async_setup_entry as setup_buttons
from custom_components.ikuai.const import BUTTON_TYPES, SENSOR_TYPES, SWITCH_TYPES
from custom_components.ikuai.sensor import IKUAISensor
from custom_components.ikuai.sensor import async_setup_entry as setup_sensors
from custom_components.ikuai.switch import IKUAISwitchmac
from custom_components.ikuai.switch import async_setup_entry as setup_switches

SYSTEM = {
    "sysinfo": {
        "hostname": "Fake router",
        "verinfo": {"version": "4.0.313", "verstring": "4.0.313 test"},
        "cpu": ["12.5%"],
        "cputemp": [45],
        "uptime": 90061,
        "memory": {"used": "25%"},
        "online_user": {"count": 3},
        "stream": {
            "connect_num": 40,
            "upload": 1048576,
            "download": 2097152,
            "total_up": 1073741824,
            "total_down": 2147483648,
        },
    }
}
MAC = "02:00:00:00:00:01"


@asynccontextmanager
async def router(handler):
    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    url = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"
    try:
        async with aiohttp.ClientSession() as session:
            yield IkuaiV4Client(session, url, "fake-test-token"), url
    finally:
        await runner.cleanup()


@pytest.mark.parametrize(
    "url",
    [
        "https://u:p@example.com",
        "ftp://example.com",
        "https://example.com/?token=x",
        "https://example.com/path",
        "https://example.com:invalid",
    ],
)
def test_rejects_unsafe_url(url):
    with pytest.raises(ValueError):
        normalize_url(url)


def test_system_preserves_units_and_missing_values():
    d = normalize_system(SYSTEM)
    assert (d["ikuai_cpu"], d["ikuai_memory"], d["ikuai_upload"], d["ikuai_total_down"]) == (
        12.5,
        25,
        1,
        2,
    )
    assert d["ikuai_uptime"] == "1天1小时1分钟"
    assert normalize_system({"sysinfo": {"cpu": []}})["ikuai_cpu"] is None
    assert normalize_system({"sysinfo": {"stream": {"upload": "NaN"}}})["ikuai_upload"] is None


def test_wan_does_not_pick_first_or_leak_config():
    configs = [
        {"id": 2, "default_route": 0},
        {"id": 7, "default_route": 1, "username": "fake", "passwd": "fake-secret"},
    ]
    status = {
        "iface_check": [{"id": 7, "interface": "wan7", "ip_addr": "192.0.2.7", "result": "success"}]
    }
    assert normalize_wan(configs, status)["ikuai_wan_ip"] == "192.0.2.7"
    assert "fake-secret" not in str(normalize_wan(configs, status))
    configs[0]["default_route"] = 1
    assert normalize_wan(configs, status)["ikuai_wan_ip"] is None


@pytest.mark.asyncio
async def test_bearer_headers_and_payload():
    async def handle(request):
        assert request.method == "GET"
        assert request.path == "/api/v4.0/monitoring/system"
        assert request.headers["Authorization"] == "Bearer fake-test-token"
        assert "Cookie" not in request.headers
        return web.json_response({"code": 0, "results": SYSTEM})

    async with router(handle) as (api, _):
        assert await api.request("GET", "/monitoring/system") == SYSTEM


@pytest.mark.parametrize(
    "status,body,error",
    [
        (401, {}, IkuaiV4AuthError),
        (403, {}, IkuaiV4PermissionError),
        (200, {"code": 3007}, IkuaiV4AuthError),
        (200, {"code": 9, "message": "fake-secret"}, IkuaiV4Error),
        (200, {"results": {}}, IkuaiV4Error),
        (302, {}, IkuaiV4Error),
        (200, {"code": False, "results": {}}, IkuaiV4Error),
    ],
)
@pytest.mark.asyncio
async def test_errors_do_not_expose_body_or_follow_redirect(status, body, error):
    calls = []

    async def handle(request):
        calls.append(request.path)
        return web.json_response(body, status=status, headers={"Location": "/do-not-follow"})

    async with router(handle) as (api, _):
        with pytest.raises(error) as caught:
            await api.request("GET", "/monitoring/system")
        assert "fake-secret" not in str(caught.value)
    assert calls == ["/api/v4.0/monitoring/system"]


@pytest.mark.asyncio
async def test_pagination_collects_all_pages():
    async def handle(request):
        page = int(request.query["page"])
        return web.json_response({"code": 0, "results": {"total": 2, "data": [{"id": page}]}})

    async with router(handle) as (api, _):
        assert await api.rows("/security/mac-rules") == [{"id": 1}, {"id": 2}]


@pytest.mark.asyncio
async def test_pagination_repetition_is_failure():
    async def handle(request):
        return web.json_response({"code": 0, "results": {"total": 2, "data": [{"id": 1}]}})

    async with router(handle) as (api, _):
        with pytest.raises(IkuaiV4Error, match="repeated"):
            await api.rows("/security/mac-rules")


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", "/system/reboot", None),
        ("PATCH", "/security/mac-rules/1", {"enabled": "no"}),
        ("DELETE", "/security/mac-rules/1", None),
    ],
)
@pytest.mark.asyncio
async def test_all_writes_are_rejected_before_network(method, path, body):
    api = IkuaiV4Client(SimpleNamespace(), "http://router.example", "fake-token")
    with pytest.raises(IkuaiV4Error, match="read-only"):
        await api.request(method, path, body=body)


def fake_api():
    async def request(method, path, **kwargs):
        if path == "/monitoring/system":
            return SYSTEM
        if path == "/monitoring/wireless-statistics":
            return {"ap_status": {"ap_online": 2}}
        return {"iface_check": []}

    async def rows(path):
        return []

    return SimpleNamespace(request=AsyncMock(side_effect=request), rows=AsyncMock(side_effect=rows))


@pytest.mark.asyncio
async def test_partial_read_failure_keeps_system_sensors():
    api = fake_api()
    api.rows.side_effect = IkuaiV4PermissionError("denied")
    data = await IkuaiV4Fetcher(api).get_data()
    assert data["ikuai_cpu"] == 12.5 and data["ikuai_ap_online"] == 2
    assert data["ikuai_wan_ip"] is None
    assert data["read_errors"] == {"wan_config": "IkuaiV4PermissionError"}


@pytest.mark.asyncio
async def test_any_auth_failure_enters_reauth():
    api = fake_api()
    api.rows.side_effect = IkuaiV4AuthError("invalid")
    with pytest.raises(IkuaiV4AuthError):
        await IkuaiV4Fetcher(api).get_data()


@pytest.mark.asyncio
async def test_sensor_polling_never_reads_mac_rules_or_clients():
    api = fake_api()
    data = await IkuaiV4Fetcher(api).get_data()
    assert {call.args[1] for call in api.request.await_args_list} == {
        "/monitoring/system",
        "/monitoring/interfaces-status",
        "/monitoring/wireless-statistics",
    }
    assert [call.args[0] for call in api.rows.await_args_list] == ["/interfaces/wan-config"]
    assert data["mac_control"] == [] and data["tracker"] == []


def test_all_entity_keys_and_identity_hosts_are_unchanged():
    coordinator = SimpleNamespace(
        host="http://router.example",
        is_v4=True,
        last_update_success=True,
        data={
            "device_name": "Fake",
            "sw_version": "4.0.313",
            "ikuai_cpu": 12,
            "mac_control": [{"id": 1, "mac": MAC, "enabled": "yes"}],
        },
    )
    assert len(SENSOR_TYPES) == 15 and len(BUTTON_TYPES) == 2 and len(SWITCH_TYPES) == 2
    for kind in SENSOR_TYPES:
        assert IKUAISensor(kind, coordinator).unique_id == f"ikuai_{kind}_http://router.example"
    entity = IKUAISwitchmac(None, coordinator, 1)
    assert entity.unique_id == "ikuai_switch_http://router.example_020000000001"
    assert entity.is_on is True
    coordinator.data["mac_control"][0]["enabled"] = "no"
    assert entity.is_on is False
    coordinator.data["mac_control"] = []
    assert not entity.available and entity.is_on is None
    assert (
        IKUAIButton(None, "ikuai_restart", coordinator).unique_id
        == "ikuai_ikuai_restart_http://router.example"
    )


def test_missing_sensor_is_unavailable_instead_of_zero():
    coordinator = SimpleNamespace(
        host="http://router.example", is_v4=True, last_update_success=True, data={}
    )
    sensor = IKUAISensor("ikuai_cpu", coordinator)
    assert not sensor.available and sensor.state is None


@pytest.mark.asyncio
async def test_legacy_cookie_protocol_is_retained():
    from custom_components.ikuai.data_fetcher import DataFetcher

    async def handle(request):
        assert request.method == "POST"
        assert "Authorization" not in request.headers
        body = await request.json()
        if request.path == "/Action/login":
            assert body == {"username": "fake-user", "passwd": "fake-hash", "pass": "fake-base64"}
            response = web.json_response({"Result": 10000})
            response.set_cookie("sess_key", "fake-session")
            return response
        assert "sess_key=fake-session" in request.headers["Cookie"]
        assert body == {
            "func_name": "homepage",
            "action": "show",
            "param": {"TYPE": "sysstat,ac_status"},
        }
        return web.json_response(
            {"Result": 30000, "Data": {"sysstat": SYSTEM["sysinfo"], "ac_status": {"ap_online": 2}}}
        )

    async with router(handle) as (api, url):
        with patch(
            "custom_components.ikuai.data_fetcher.async_get_clientsession", return_value=api.session
        ):
            fetcher = DataFetcher(None, url, "fake-user", "fake-hash", "fake-base64", {})
            session_key = await fetcher._login_ikuai()
            assert session_key == "fake-session"
            data = {}
            await fetcher._get_ikuai_status(session_key, data)
            assert data["ikuai_cpu"] == "12.5" and data["ikuai_ap_online"] == 2


@pytest.mark.asyncio
async def test_malformed_optional_fields_do_not_break_system():
    api = fake_api()

    async def request(method, path, **kwargs):
        if path == "/monitoring/system":
            return SYSTEM
        if path == "/monitoring/wireless-statistics":
            return {"ap_status": None}
        return {"iface_check": None}

    async def rows(path):
        if path == "/interfaces/wan-config":
            return [{"id": 1, "default_route": 1}]
        return [{"id": 1, "mac": None, "enabled": "yes"}]

    api.request.side_effect = request
    api.rows.side_effect = rows
    data = await IkuaiV4Fetcher(api).get_data()
    assert data["ikuai_cpu"] == 12.5
    assert data["ikuai_ap_online"] is None and data["ikuai_wan_ip"] is None
    assert data["mac_control"] == []


@pytest.mark.parametrize("is_v4", [True, False])
@pytest.mark.asyncio
async def test_only_supported_entities_are_created_in_v4(is_v4):
    coordinator = SimpleNamespace(
        host="http://router.example",
        is_v4=is_v4,
        last_update_success=True,
        data={
            "device_name": "Fake router",
            "sw_version": "test",
            "mac_control": [{"id": 1, "mac": MAC, "enabled": "yes"}],
            "unsupported": [
                "ikuai_restart",
                "ikuai_restart_reconnect_wan",
                "ikuai_arp_filter",
                "ikuai_stream_control",
                "ikuai_wan6_ip",
                "ikuai_lan6_ip",
            ],
        },
    )
    hass = SimpleNamespace(
        data={
            "ikuai": {
                "test-entry": {"coordinator": coordinator},
                "custom_switches": {
                    "fake_custom": {"name": "Fake custom", "turn_on_body": {}, "turn_off_body": {}}
                },
            }
        }
    )
    config = SimpleNamespace(entry_id="test-entry")
    sensors, buttons, switches = Mock(), Mock(), Mock()
    await setup_sensors(hass, config, sensors)
    await setup_buttons(hass, config, buttons)
    await setup_switches(hass, config, switches)
    assert len(sensors.call_args.args[0]) == (13 if is_v4 else 15)
    assert len(buttons.call_args.args[0]) == (0 if is_v4 else 2)
    assert len(switches.call_args.args[0]) == (0 if is_v4 else 4)
    if is_v4:
        assert {sensor.kind for sensor in sensors.call_args.args[0]}.isdisjoint(
            coordinator.data["unsupported"]
        )
        assert all(isinstance(entity, IKUAISwitchmac) for entity in switches.call_args.args[0])
