"""DataUpdateCoordinator for the BuildingLink integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BuildingLinkAuthError, BuildingLinkClient, BuildingLinkError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class BuildingLinkDeliveriesData:
    """Parsed result of a Deliveries page poll."""

    count: int
    packages: list[dict]


class BuildingLinkCoordinator(DataUpdateCoordinator[BuildingLinkDeliveriesData]):
    """Polls BuildingLink for package/delivery info."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: BuildingLinkClient,
        update_interval=DEFAULT_SCAN_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.client = client

    async def _async_update_data(self) -> BuildingLinkDeliveriesData:
        try:
            result = await self.client.async_get_deliveries()
        except BuildingLinkAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except BuildingLinkError as err:
            raise UpdateFailed(str(err)) from err

        return BuildingLinkDeliveriesData(
            count=result["count"], packages=result["packages"]
        )
