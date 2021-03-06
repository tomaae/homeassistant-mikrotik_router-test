"""Support for the Mikrotik Router device tracker."""

import logging
from datetime import timedelta

from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.components.device_tracker.const import SOURCE_TYPE_ROUTER
from homeassistant.const import (
    CONF_NAME,
    ATTR_ATTRIBUTION,
)
from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util.dt import get_age, utcnow

from .const import (
    DOMAIN,
    DATA_CLIENT,
    ATTRIBUTION,
    CONF_TRACK_HOSTS,
    DEFAULT_TRACK_HOSTS,
    CONF_TRACK_HOSTS_TIMEOUT,
    DEFAULT_TRACK_HOST_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

DEVICE_ATTRIBUTES_IFACE = [
    "running",
    "enabled",
    "comment",
    "client-ip-address",
    "client-mac-address",
    "port-mac-address",
    "last-link-down-time",
    "last-link-up-time",
    "link-downs",
    "actual-mtu",
    "type",
    "name",
    "default-name",
]

DEVICE_ATTRIBUTES_HOST = [
    "host-name",
    "address",
    "mac-address",
    "interface",
    "source",
    "last-seen",
]


# ---------------------------
#   format_attribute
# ---------------------------
def format_attribute(attr):
    res = attr.replace("-", " ")
    res = res.capitalize()
    res = res.replace(" ip ", " IP ")
    res = res.replace(" mac ", " MAC ")
    res = res.replace(" mtu", " MTU")
    return res


# ---------------------------
#   format_value
# ---------------------------
def format_value(res):
    res = res.replace("dhcp", "DHCP")
    res = res.replace("dns", "DNS")
    res = res.replace("capsman", "CAPsMAN")
    res = res.replace("wireless", "Wireless")
    res = res.replace("restored", "Restored")
    return res


# ---------------------------
#   async_setup_entry
# ---------------------------
async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up device tracker for Mikrotik Router component."""
    inst = config_entry.data[CONF_NAME]
    mikrotik_controller = hass.data[DOMAIN][DATA_CLIENT][config_entry.entry_id]
    tracked = {}

    @callback
    def update_controller():
        """Update the values of the controller."""
        update_items(
            inst, config_entry, mikrotik_controller, async_add_entities, tracked
        )

    mikrotik_controller.listeners.append(
        async_dispatcher_connect(
            hass, mikrotik_controller.signal_update, update_controller
        )
    )

    update_controller()


# ---------------------------
#   update_items
# ---------------------------
@callback
def update_items(inst, config_entry, mikrotik_controller, async_add_entities, tracked):
    """Update tracked device state from the controller."""
    new_tracked = []

    # Add switches
    for sid, sid_uid, sid_func in zip(
        ["interface", "host"],
        ["default-name", "mac-address"],
        [MikrotikControllerPortDeviceTracker, MikrotikControllerHostDeviceTracker],
    ):
        for uid in mikrotik_controller.data[sid]:

            # No device tracker for wlan
            if (
                sid == "interface"
                and mikrotik_controller.data[sid][uid]["type"] == "wlan"
            ):
                continue

            if (
                not config_entry.options.get(CONF_TRACK_HOSTS, DEFAULT_TRACK_HOSTS)
                and sid == "host"
            ):
                continue
            item_id = f"{inst}-{sid}-{mikrotik_controller.data[sid][uid][sid_uid]}"
            _LOGGER.debug("Updating device_tracker %s", item_id)
            if item_id in tracked:
                if tracked[item_id].enabled:
                    tracked[item_id].async_schedule_update_ha_state()
                continue

            tracked[item_id] = sid_func(inst, uid, mikrotik_controller, config_entry)
            new_tracked.append(tracked[item_id])

    if new_tracked:
        async_add_entities(new_tracked)


# ---------------------------
#   MikrotikControllerPortDeviceTracker
# ---------------------------
class MikrotikControllerPortDeviceTracker(ScannerEntity):
    """Representation of a network port."""

    def __init__(self, inst, uid, mikrotik_controller, _):
        """Set up tracked port."""
        self._inst = inst
        self._ctrl = mikrotik_controller
        self._data = mikrotik_controller.data["interface"][uid]

        self._attrs = {
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

    @property
    def entity_registry_enabled_default(self):
        """Return if the entity should be enabled when first added to the entity registry."""
        return True

    async def async_added_to_hass(self):
        """Port entity created."""
        _LOGGER.debug(
            "New port tracker %s (%s %s)",
            self._inst,
            self._data["default-name"],
            self._data["port-mac-address"],
        )

    async def async_update(self):
        """Synchronize state with controller."""

    @property
    def is_connected(self):
        """Return true if the port is connected to the network."""
        return self._data["running"]

    @property
    def source_type(self):
        """Return the source type of the port."""
        return SOURCE_TYPE_ROUTER

    @property
    def name(self):
        """Return the name of the port."""
        return f"{self._inst} {self._data['default-name']}"

    @property
    def unique_id(self):
        """Return a unique identifier for this port."""
        return f"{self._inst.lower()}-interface-{self._data['port-mac-address']}"

    @property
    def available(self) -> bool:
        """Return if controller is available."""
        return self._ctrl.connected()

    @property
    def icon(self):
        """Return the icon."""
        if self._data["running"]:
            icon = "mdi:lan-connect"
        else:
            icon = "mdi:lan-pending"

        if not self._data["enabled"]:
            icon = "mdi:lan-disconnect"

        return icon

    @property
    def device_info(self):
        """Return a port description for device registry."""
        info = {
            "connections": {(CONNECTION_NETWORK_MAC, self._data["port-mac-address"])},
            "manufacturer": self._ctrl.data["resource"]["platform"],
            "model": self._ctrl.data["resource"]["board-name"],
            "name": f"{self._inst} {self._data['default-name']}",
        }
        return info

    @property
    def device_state_attributes(self):
        """Return the port state attributes."""
        attributes = self._attrs
        for variable in DEVICE_ATTRIBUTES_IFACE:
            if variable in self._data:
                attributes[format_attribute(variable)] = self._data[variable]

        return attributes


# ---------------------------
#   MikrotikControllerHostDeviceTracker
# ---------------------------
class MikrotikControllerHostDeviceTracker(ScannerEntity):
    """Representation of a network device."""

    def __init__(self, inst, uid, mikrotik_controller, config_entry):
        """Set up tracked port."""
        self._inst = inst
        self._ctrl = mikrotik_controller
        self._data = mikrotik_controller.data["host"][uid]
        self._config_entry = config_entry

        self._attrs = {
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

    @property
    def option_track_network_hosts(self):
        """Config entry option to not track ARP."""
        return self._config_entry.options.get(CONF_TRACK_HOSTS, DEFAULT_TRACK_HOSTS)

    @property
    def option_track_network_hosts_timeout(self):
        """Config entry option scan interval."""
        track_network_hosts_timeout = self._config_entry.options.get(
            CONF_TRACK_HOSTS_TIMEOUT, DEFAULT_TRACK_HOST_TIMEOUT
        )
        return timedelta(seconds=track_network_hosts_timeout)

    @property
    def entity_registry_enabled_default(self):
        """Return if the entity should be enabled when first added to the entity registry."""
        return True

    async def async_added_to_hass(self):
        """Host entity created."""
        _LOGGER.debug(
            "New host tracker %s (%s - %s)",
            self._inst,
            self._data["host-name"],
            self._data["mac-address"],
        )

    async def async_update(self):
        """Synchronize state with controller."""

    @property
    def is_connected(self):
        """Return true if the host is connected to the network."""
        if not self.option_track_network_hosts:
            return False

        if self._data["source"] in ["capsman", "wireless"]:
            return self._data["available"]

        if (
            self._data["last-seen"]
            and (utcnow() - self._data["last-seen"])
            < self.option_track_network_hosts_timeout
        ):
            return True
        return False

    @property
    def source_type(self):
        """Return the source type of the host."""
        return SOURCE_TYPE_ROUTER

    @property
    def name(self):
        """Return the name of the host."""
        return f"{self._data['host-name']}"

    @property
    def unique_id(self):
        """Return a unique identifier for this host."""
        return f"{self._inst.lower()}-host-{self._data['mac-address']}"

    @property
    def available(self) -> bool:
        """Return if controller is available."""
        if not self.option_track_network_hosts:
            return False

        return self._ctrl.connected()

    @property
    def icon(self):
        """Return the icon."""
        if self._data["source"] in ["capsman", "wireless"]:
            if self._data["available"]:
                return "mdi:lan-connect"
            else:
                return "mdi:lan-disconnect"

        if (
            self._data["last-seen"]
            and (utcnow() - self._data["last-seen"])
            < self.option_track_network_hosts_timeout
        ):
            return "mdi:lan-connect"
        return "mdi:lan-disconnect"

    @property
    def device_info(self):
        """Return a host description for device registry."""
        info = {
            "connections": {(CONNECTION_NETWORK_MAC, self._data["mac-address"])},
            "manufacturer": self._ctrl.data["resource"]["platform"],
            "model": self._ctrl.data["resource"]["board-name"],
            "name": self._data["host-name"],
        }
        return info

    @property
    def device_state_attributes(self):
        """Return the host state attributes."""
        attributes = self._attrs
        for variable in DEVICE_ATTRIBUTES_HOST:
            if variable in self._data:
                if variable == "last-seen":
                    if self._data[variable]:
                        attributes[format_attribute(variable)] = get_age(
                            self._data[variable]
                        )
                    else:
                        attributes[format_attribute(variable)] = "unknown"
                else:
                    if self._data[variable] in [
                        "dhcp",
                        "dns",
                        "capsman",
                        "wireless",
                        "restored",
                    ]:
                        attributes[format_attribute(variable)] = format_value(
                            self._data[variable]
                        )
                    else:
                        attributes[format_attribute(variable)] = self._data[variable]

        return attributes
