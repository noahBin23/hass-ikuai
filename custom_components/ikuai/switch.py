"""IKUAI Entities"""

import logging

from homeassistant.components.switch import (
    SwitchEntity,
)
from homeassistant.exceptions import HomeAssistantError

from .const import (
    COORDINATOR,
    DOMAIN,
    SWITCH_TYPES,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up iKuai switch entities from a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]

    switchs = []

    if SWITCH_TYPES and not coordinator.is_v4:
        for switch in SWITCH_TYPES:
            switchs.append(IKUAISwitch(hass, switch, coordinator, is_custom=False))

    custom_switches_config = hass.data[DOMAIN].get("custom_switches", {})
    if custom_switches_config and not coordinator.is_v4:
        _LOGGER.debug("setup custom switches")
        for switch_key, switch_config in custom_switches_config.items():
            switchs.append(
                IKUAISwitch(
                    hass, switch_key, coordinator, is_custom=True, custom_config=switch_config
                )
            )
            _LOGGER.debug(switch_config["name"])

    if not coordinator.is_v4 and coordinator.data.get("mac_control"):
        listmacdata = coordinator.data.get("mac_control")
        if isinstance(listmacdata, list):
            for mac in listmacdata:
                switchs.append(IKUAISwitchmac(hass, coordinator, mac["id"]))

    async_add_entities(switchs, False)


class IKUAIBaseSwitch(SwitchEntity):
    """Base class for iKuai switches."""

    _attr_has_entity_name = True

    def __init__(self, hass, coordinator):
        """Initialize the base switch."""
        super().__init__()
        self.coordinator = coordinator
        self._hass = hass
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": self.coordinator.data["device_name"],
            "manufacturer": "iKuai",
            "model": "iKuai Router",
            "sw_version": self.coordinator.data["sw_version"],
        }

    async def async_added_to_hass(self):
        """Handle entity which will be added."""
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    @property
    def available(self):
        return self.coordinator.last_update_success


class IKUAISwitch(IKUAIBaseSwitch):
    """Define a static iKuai switch entity."""

    def __init__(self, hass, kind, coordinator, is_custom=False, custom_config=None):
        """Initialize the switch."""
        super().__init__(hass, coordinator)
        self.kind = kind

        # Set properties based on whether it's custom or built-in
        if is_custom and custom_config:
            self._attr_icon = custom_config.get("icon", "mdi:toggle-switch")
            self._name = custom_config["name"]
            self._turn_on_body = custom_config["turn_on_body"]
            self._turn_off_body = custom_config["turn_off_body"]
        else:
            self._attr_icon = SWITCH_TYPES[self.kind]["icon"]
            self._name = SWITCH_TYPES[self.kind]["name"]
            self._turn_on_body = SWITCH_TYPES[self.kind]["turn_on_body"]
            self._turn_off_body = SWITCH_TYPES[self.kind]["turn_off_body"]

    @property
    def name(self):
        """Return the name of the switch."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"{DOMAIN}_{self.kind}_{self.coordinator.host}"

    @property
    def icon(self):
        """Return the icon of the switch."""
        return self._attr_icon

    @property
    def is_on(self):
        """Return true if switch is on based on coordinator data."""
        if self.coordinator.data.get("switch"):
            for item in self.coordinator.data["switch"]:
                if item["name"] == self._name:
                    return item["onoff"] == "on"
        return None

    @property
    def available(self):
        return super().available and self.is_on is not None

    @property
    def extra_state_attributes(self):
        if self.coordinator.is_v4:
            return {
                "unavailable_reason": "Legacy/custom RPC control has no verified 4.0 REST mapping"
            }
        return {}

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self.coordinator.async_control_device(self._turn_on_body)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self.coordinator.async_control_device(self._turn_off_body)
        await self.coordinator.async_request_refresh()


class IKUAISwitchmac(IKUAIBaseSwitch):
    """Define an iKuai MAC access control switch entity."""

    def __init__(self, hass, coordinator, macid):
        """Initialize the MAC control switch."""
        super().__init__(hass, coordinator)
        self._macid = macid
        self._attr_icon = "mdi:network-pos"
        self._attr_device_class = "switch"
        self._update_from_coordinator()

    def _update_from_coordinator(self):
        """Update the internal state from coordinator data."""
        listmacswitch = self.coordinator.data.get("mac_control")
        if isinstance(listmacswitch, list):
            for macswitch in listmacswitch:
                if macswitch["id"] == self._macid:
                    self._mac_address = macswitch["mac"]
                    self._mac = str(self._mac_address).replace(":", "")

                    if macswitch.get("comment"):
                        self._name = f"Mac_control_{self._mac[-6:]}({macswitch['comment']})"
                    else:
                        self._name = f"Mac_control_{self._mac[-6:]}(未备注)"

                    self._is_on = macswitch["enabled"] == "yes"
                    break

    @property
    def name(self):
        """Return the name of the switch."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"{DOMAIN}_switch_{self.coordinator.host}_{self._mac}"

    @property
    def is_on(self):
        """Return true if the MAC control is enabled."""
        if self.coordinator.is_v4:
            row = self._current_rule()
            return row["enabled"] == "yes" if row and row.get("enabled") in ("yes", "no") else None
        return self._is_on

    def _current_rule(self):
        matches = [
            row
            for row in (self.coordinator.data or {}).get("mac_control", [])
            if str(row.get("mac", "")).replace(":", "").lower() == self._mac.lower()
        ]
        return matches[0] if len(matches) == 1 else None

    @property
    def available(self):
        return super().available and (not self.coordinator.is_v4 or self.is_on is not None)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {"mac_address": getattr(self, "_mac_address", None)}

    async def async_turn_on(self, **kwargs):
        """Turn the MAC control switch on."""
        if self.coordinator.is_v4:
            if not self.available:
                raise HomeAssistantError("MAC rule is unavailable")
            self._macid = self._current_rule()["id"]
        mac_json_body = {"func_name": "acl_mac", "action": "up", "param": {"id": str(self._macid)}}
        await self.coordinator.async_control_device(mac_json_body)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn the MAC control switch off."""
        if self.coordinator.is_v4:
            if not self.available:
                raise HomeAssistantError("MAC rule is unavailable")
            self._macid = self._current_rule()["id"]
        mac_json_body = {
            "func_name": "acl_mac",
            "action": "down",
            "param": {"id": str(self._macid)},
        }
        await self.coordinator.async_control_device(mac_json_body)
        await self.coordinator.async_request_refresh()

    async def async_update(self):
        """Update the entity state."""
        self._update_from_coordinator()
