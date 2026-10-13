"""iKuai 4.x REST API. No Home Assistant imports or implicit write retries."""

from __future__ import annotations

import asyncio
import ipaddress
import math
import time
from urllib.parse import urlsplit, urlunsplit

import aiohttp


class IkuaiV4Error(Exception):
    """Safe protocol error; never include response bodies or credentials."""


class IkuaiV4AuthError(IkuaiV4Error):
    """The configured API token is invalid."""


class IkuaiV4PermissionError(IkuaiV4Error):
    """The API token cannot read or modify this resource."""


def normalize_url(value: str) -> str:
    """Accept an origin or the documented API root, without URL credentials."""
    u = urlsplit(value.strip())
    if (
        u.scheme not in ("http", "https")
        or not u.hostname
        or u.username
        or u.password
        or u.query
        or u.fragment
        or u.path.rstrip("/") not in ("", "/api/v4.0")
    ):
        raise ValueError("invalid_url")
    try:
        u.port
    except ValueError:
        raise ValueError("invalid_url") from None
    return urlunsplit((u.scheme, u.netloc, "", "", ""))


def number(value):
    """Missing, malformed and non-finite numbers remain missing."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(str(value).rstrip("%"))
        return result if math.isfinite(result) and result >= 0 else None
    except ValueError, TypeError:
        return None


def duration(value):
    seconds = number(value)
    if seconds is None:
        return None
    seconds = int(seconds)
    days, hours = seconds // 86400, seconds // 3600 % 24
    minutes, seconds = seconds // 60 % 60, seconds % 60
    if days:
        return f"{days}天{hours}小时{minutes}分钟"
    if hours:
        return f"{hours}小时{minutes}分钟"
    if minutes:
        return f"{minutes}分钟{seconds}秒"
    return f"{seconds}秒"


def ipv4(value):
    try:
        address = ipaddress.IPv4Address(value)
        return str(address) if not address.is_unspecified else None
    except ValueError, TypeError, ipaddress.AddressValueError:
        return None


def normalize_system(payload):
    """Preserve the existing entity keys and binary MB/GB conversion factors."""
    system = payload.get("sysinfo") if isinstance(payload, dict) else None
    if not isinstance(system, dict) or not system:
        raise IkuaiV4Error("System response is missing sysinfo")
    cpu = system.get("cpu")
    temp = system.get("cputemp")
    memory = system.get("memory") if isinstance(system.get("memory"), dict) else {}
    stream = system.get("stream") if isinstance(system.get("stream"), dict) else {}
    users = system.get("online_user") if isinstance(system.get("online_user"), dict) else {}
    ver = system.get("verinfo") if isinstance(system.get("verinfo"), dict) else {}
    data = {
        "device_name": system.get("hostname") or "iKuai Router",
        "sw_version": ver.get("verstring") or "Unknown",
        "ikuai_uptime": duration(system.get("uptime")),
        "ikuai_cpu": number(cpu[0]) if isinstance(cpu, list) and cpu else None,
        "ikuai_cputemp": number(temp[0]) if isinstance(temp, list) and temp else None,
        "ikuai_memory": number(memory.get("used")),
        "ikuai_online_user": number(users.get("count")),
        "ikuai_connect_num": number(stream.get("connect_num")),
    }
    for source, target, divisor, digits in (
        ("upload", "ikuai_upload", 1024**2, 3),
        ("download", "ikuai_download", 1024**2, 3),
        ("total_up", "ikuai_total_up", 1024**3, 2),
        ("total_down", "ikuai_total_down", 1024**3, 2),
    ):
        value = number(stream.get(source))
        data[target] = round(value / divisor, digits) if value is not None else None
    return data


def normalize_wan(config, status):
    """Choose the unique default route; never silently select the first WAN."""
    defaults = [row for row in config if str(row.get("default_route")) == "1"]
    if len(defaults) != 1:
        return {"ikuai_wan_ip": None, "ikuai_wan_uptime": None}
    wan = defaults[0]
    rows = status.get("iface_check")
    if not isinstance(rows, list):
        return {"ikuai_wan_ip": None, "ikuai_wan_uptime": None}
    matches = [
        row
        for row in rows
        if isinstance(row, dict)
        and (
            (wan.get("id") is not None and str(row.get("id")) == str(wan["id"]))
            or (wan.get("name") and row.get("interface") == wan["name"])
        )
    ]
    if len(matches) != 1 or matches[0].get("result") != "success":
        return {"ikuai_wan_ip": None, "ikuai_wan_uptime": None}
    current = matches[0]
    started = number(current.get("updatetime"))
    elapsed = time.time() - started if started is not None else -1
    return {
        "ikuai_wan_ip": ipv4(current.get("ip_addr")),
        "ikuai_wan_uptime": duration(elapsed) if elapsed >= 0 else None,
        "ikuai_wan_ip_attrs": {"interface": current.get("interface")},
    }


class IkuaiV4Client:
    """Use the HA-owned HTTP session; do not close it from this client."""

    def __init__(self, session, url, token, verify_ssl=True):
        self.session = session
        self.url = normalize_url(url)
        if not isinstance(token, str) or not token.strip() or any(c in token for c in "\r\n"):
            raise ValueError("invalid_auth")
        self._token = token.strip()
        self.verify_ssl = verify_ssl

    async def request(self, method, path, *, params=None, body=None):
        if not path.startswith("/") or ".." in path or "?" in path or "#" in path:
            raise ValueError("invalid_path")
        if method != "GET":
            raise IkuaiV4Error("Unsupported control operation: iKuai 4.x is read-only")
        try:
            async with self.session.request(
                method,
                self.url + "/api/v4.0" + path,
                headers={"Authorization": "Bearer " + self._token, "Accept": "application/json"},
                params=params,
                json=body,
                ssl=self.verify_ssl,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status == 401:
                    raise IkuaiV4AuthError("API token is invalid")
                if response.status == 403:
                    raise IkuaiV4PermissionError("API permission denied")
                if response.status != 200:
                    raise IkuaiV4Error(f"API HTTP {response.status}")
                try:
                    envelope = await response.json(content_type=None)
                except ValueError, UnicodeError:
                    raise IkuaiV4Error("Invalid API JSON") from None
        except aiohttp.ClientError, asyncio.TimeoutError:
            raise IkuaiV4Error("Cannot connect to iKuai API") from None
        if not isinstance(envelope, dict):
            raise IkuaiV4Error("Invalid API response")
        code = envelope.get("code")
        if code in (3007, 1008):
            raise IkuaiV4AuthError("API token is invalid")
        if not (type(code) is int and code == 0) and not (
            code is None and envelope.get("message") == "Success"
        ):
            raise IkuaiV4Error("API operation failed")
        payload = envelope.get("results", envelope.get("data"))
        if not isinstance(payload, dict):
            raise IkuaiV4Error("API payload is missing")
        return payload

    async def rows(self, path):
        rows, page, seen = [], 1, set()
        while True:
            payload = await self.request("GET", path, params={"page": page, "limit": 100})
            batch, total = payload.get("data"), payload.get("total")
            if not isinstance(batch, list) or any(not isinstance(row, dict) for row in batch):
                raise IkuaiV4Error("Invalid API list")
            if not isinstance(total, int) or isinstance(total, bool) or total < 0:
                raise IkuaiV4Error("Invalid API total")
            identifiers = [row.get("id") for row in batch]
            if any(item in seen for item in identifiers) or len(set(identifiers)) != len(
                identifiers
            ):
                raise IkuaiV4Error("API pagination repeated records")
            seen.update(identifiers)
            rows.extend(batch)
            if len(rows) >= total:
                return rows
            if not batch:
                raise IkuaiV4Error("API pagination is incomplete")
            page += 1


class IkuaiV4Fetcher:
    """Map independent API resources onto the existing integration data model."""

    def __init__(self, api):
        self.api = api

    async def get_data(self):
        data = normalize_system(await self.api.request("GET", "/monitoring/system"))
        data.update(
            {
                "switch": [],
                "mac_control": [],
                "tracker": [],
                "tracker_available": False,
                "ikuai_ap_online": None,
                "ikuai_wan_ip": None,
                "ikuai_wan_uptime": None,
                "ikuai_wan6_ip": None,
                "ikuai_lan6_ip": None,
                "querytime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "read_errors": {},
                "unsupported": [
                    "ikuai_restart",
                    "ikuai_restart_reconnect_wan",
                    "ikuai_arp_filter",
                    "ikuai_stream_control",
                    "ikuai_wan6_ip",
                    "ikuai_lan6_ip",
                ],
            }
        )
        jobs = {
            "wan_config": self.api.rows("/interfaces/wan-config"),
            "interfaces": self.api.request("GET", "/monitoring/interfaces-status"),
            "wireless": self.api.request("GET", "/monitoring/wireless-statistics"),
        }
        results = dict(zip(jobs, await asyncio.gather(*jobs.values(), return_exceptions=True)))
        for name, value in results.items():
            if isinstance(value, IkuaiV4AuthError):
                raise value
            if isinstance(value, Exception):
                data["read_errors"][name] = type(value).__name__
        if isinstance(results["wan_config"], list) and isinstance(results["interfaces"], dict):
            data.update(normalize_wan(results["wan_config"], results["interfaces"]))
        if isinstance(results["wireless"], dict):
            ap = results["wireless"].get("ap_status")
            data["ikuai_ap_online"] = number(ap.get("ap_online")) if isinstance(ap, dict) else None
        return data
