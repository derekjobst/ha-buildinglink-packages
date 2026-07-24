"""The BuildingLink integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BuildingLinkClient
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
from .coordinator import BuildingLinkCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

type BuildingLinkConfigEntry = ConfigEntry[BuildingLinkRuntimeData]


@dataclass
class BuildingLinkRuntimeData:
    """Data stored on the config entry at runtime."""

    client: BuildingLinkClient
    coordinator: BuildingLinkCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: BuildingLinkConfigEntry) -> bool:
    """Set up BuildingLink from a config entry."""
    session = async_get_clientsession(hass)
    client = BuildingLinkClient(
        session, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )

    scan_interval_minutes = entry.options.get(
        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
    )
    coordinator = BuildingLinkCoordinator(
        hass,
        entry,
        client,
        update_interval=timedelta(minutes=scan_interval_minutes),
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = BuildingLinkRuntimeData(client=client, coordinator=coordinator)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BuildingLinkConfigEntry) -> bool:
    """Unload a BuildingLink config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: BuildingLinkConfigEntry
) -> None:
    """Reload the entry when options change (e.g. scan interval)."""
    await hass.config_entries.async_reload(entry.entry_id)
