"""The ikuai integration."""

from __future__ import annotations

import asyncio
import datetime
import logging
import time
from asyncio import timeout

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.core_config import Config
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api_v4 import IkuaiV4AuthError, IkuaiV4Client, IkuaiV4Error, IkuaiV4Fetcher
from .const import (
    CONF_API_TOKEN,
    CONF_CONNECTION_URL,
    CONF_CUSTOM_SWITCHES,
    CONF_HOST,
    CONF_PASS,
    CONF_PASSWD,
    CONF_SOURCE_MODE,
    CONF_TRACKER_CONFIG,
    CONF_UPDATE_INTERVAL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    COORDINATOR,
    DOMAIN,
    MODE_CONST,
    UNDO_UPDATE_LISTENER,
)
from .data_fetcher import DataFetcher

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.DEVICE_TRACKER,
]


# Configuration schema for custom switches
CUSTOM_SWITCH_SCHEMA = vol.Schema(
    {
        vol.Required("label"): cv.string,
        vol.Required("name"): cv.string,
        vol.Optional("icon", default="mdi:toggle-switch"): cv.string,
        vol.Required("turn_on_body"): dict,
        vol.Required("turn_off_body"): dict,
        vol.Optional("show_body"): dict,
        vol.Optional("show_on"): dict,
        vol.Optional("show_off"): dict,
    }
)

# Configuration schema for the domain
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_CUSTOM_SWITCHES, default={}): vol.Schema(
                    {cv.string: CUSTOM_SWITCH_SCHEMA}
                )
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: Config) -> bool:
    """Set up the iKuai component."""
    hass.data.setdefault(DOMAIN, {})

    # Get configuration from configuration.yaml
    conf = config.get(DOMAIN, {})
    custom_switches_config = conf.get(CONF_CUSTOM_SWITCHES, {})

    if custom_switches_config:
        _LOGGER.info(
            "Loaded %d custom switches from configuration.yaml", len(custom_switches_config)
        )
    else:
        _LOGGER.info("No custom switches configured in configuration.yaml.")
    # Store the configurations in hass.data
    hass.data[DOMAIN]["custom_switches"] = custom_switches_config
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up iKuai from a config entry."""
    host = entry.data[CONF_HOST]
    username = entry.data.get(CONF_USERNAME, "")
    passwd = entry.data.get(CONF_PASSWD, "")
    pas = entry.data.get(CONF_PASS, "")
    update_interval_seconds = entry.options.get(
        CONF_UPDATE_INTERVAL, entry.data.get(CONF_UPDATE_INTERVAL, 10)
    )

    if CONF_API_TOKEN in entry.data:
        tracker_config = {}
    elif entry.data.get(CONF_SOURCE_MODE) == MODE_CONST:
        try:
            from .const import DEVICE_TRACKERS

            tracker_config = {}
            for key, info in DEVICE_TRACKERS.items():
                target = info.get("mac_address") or info.get("ip_address")
                if target:
                    tracker_config[target] = {
                        "name": info.get("name", key),
                        "buffer": info.get("disconnect_refresh_times", 2),
                        "mac_address": info.get("mac_address"),
                        "ip_address": info.get("ip_address"),
                    }
        except ImportError:
            _LOGGER.warning("DEVICE_TRACKERS not found in const.py, skipping tracker setup")
            tracker_config = {}
    else:
        tracker_config = entry.data.get(CONF_TRACKER_CONFIG, {})

    custom_switches_config = hass.data[DOMAIN].get("custom_switches", {})

    coordinator = IKUAIDataUpdateCoordinator(
        hass,
        host,
        username,
        passwd,
        pas,
        update_interval_seconds,
        tracker_config,
        custom_switches_config,
        api_token=entry.data.get(CONF_API_TOKEN),
        connection_url=entry.data.get(CONF_CONNECTION_URL, host),
        verify_ssl=entry.data.get(CONF_VERIFY_SSL, True),
    )
    await coordinator.async_config_entry_first_refresh()

    undo_listener = entry.add_update_listener(update_listener)

    platforms = [Platform.SENSOR] if coordinator.is_v4 else PLATFORMS
    hass.data[DOMAIN][entry.entry_id] = {
        COORDINATOR: coordinator,
        "platforms": platforms,
        UNDO_UPDATE_LISTENER: undo_listener,
    }

    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    return True


async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in hass.data[DOMAIN][entry.entry_id]["platforms"]
            ]
        )
    )

    if unload_ok:
        hass.data[DOMAIN][entry.entry_id][UNDO_UPDATE_LISTENER]()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def update_listener(hass, entry):
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


class IKUAIDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching iKuai data."""

    def __init__(
        self,
        hass,
        host,
        username,
        passwd,
        pas,
        update_interval_seconds,
        tracker_config,
        custom_switches_config,
        *,
        api_token=None,
        connection_url=None,
        verify_ssl=True,
    ):
        """Initialize the coordinator."""
        update_interval = datetime.timedelta(seconds=update_interval_seconds)
        self._token = ""
        self._token_expire_time = 0
        self._allow_login = True

        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)

        self.is_v4 = api_token is not None
        if self.is_v4:
            self._fetcher = IkuaiV4Fetcher(
                IkuaiV4Client(
                    async_get_clientsession(hass, verify_ssl=verify_ssl),
                    connection_url or host,
                    api_token,
                    verify_ssl,
                )
            )
        else:
            self._fetcher = DataFetcher(
                hass, host, username, passwd, pas, tracker_config, custom_switches_config
            )
        # Entity identity stays at the original host even when the connection URL changes.
        self.host = host

    async def get_access_token(self):
        """Get or refresh the access token."""
        if time.time() < self._token_expire_time:
            return self._token
        else:
            if self._allow_login:
                self._token = await self._fetcher._login_ikuai()
                if not isinstance(self._token, str):
                    if self._token == 10001:
                        self._allow_login = False
                    return None

                self._token_expire_time = time.time() + 60 * 60 * 2
                return self._token
            else:
                _LOGGER.error(
                    "The username or password has been incorrect, please reconfigure the ikuai integration."
                )
                return

    async def _async_update_data(self):
        """Update data via DataFetcher."""
        if self.is_v4:
            try:
                return await self._fetcher.get_data()
            except IkuaiV4AuthError as error:
                raise ConfigEntryAuthFailed(str(error)) from None
            except IkuaiV4Error as error:
                raise UpdateFailed(str(error)) from None
        _LOGGER.debug("token_expire_time=%s", self._token_expire_time)
        if self._allow_login:
            sess_key = await self.get_access_token()
            if not sess_key:
                raise UpdateFailed("Failed to get access token")

            try:
                async with timeout(60):
                    data = await self._fetcher.get_data(sess_key)
                    if data == 401:
                        self._token_expire_time = 0
                        raise UpdateFailed("iKuai session expired")
                    if not data:
                        raise UpdateFailed("failed in getting data")
                    return data
            except Exception as error:
                raise UpdateFailed(error) from error

    async def async_control_device(self, action_body):
        """Execute action for iKuai devices."""
        if self.is_v4:
            raise HomeAssistantError("iKuai 4.x is sensor-only; device control is unavailable")
        if self._allow_login:
            sess_key = await self.get_access_token()
            if not sess_key:
                return
            result = await self._fetcher.async_execute_action(sess_key, action_body)
            if result == 401:
                self._token_expire_time = 0
            return result
