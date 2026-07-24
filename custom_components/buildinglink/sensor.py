"""Sensor platform for the BuildingLink integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import BuildingLinkConfigEntry
from .const import ATTRIBUTION, BUILDINGLINK_BASE_URL, DOMAIN
from .coordinator import BuildingLinkCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BuildingLinkConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BuildingLink packages sensor."""
    runtime_data = entry.runtime_data
    async_add_entities([BuildingLinkPackagesSensor(runtime_data.coordinator, entry)])


class BuildingLinkPackagesSensor(CoordinatorEntity[BuildingLinkCoordinator], SensorEntity):
    """Sensor reporting the number of packages waiting at BuildingLink."""

    _attr_has_entity_name = True
    _attr_translation_key = "packages"
    _attr_icon = "mdi:package-variant"
    _attr_native_unit_of_measurement = "packages"
    _attr_attribution = ATTRIBUTION

    def __init__(
        self, coordinator: BuildingLinkCoordinator, entry: BuildingLinkConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_packages"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"BuildingLink ({entry.data[CONF_USERNAME]})",
            manufacturer="BuildingLink",
            model="Tenant Portal",
            configuration_url=BUILDINGLINK_BASE_URL,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> int:
        return self.coordinator.data.count

    @property
    def extra_state_attributes(self) -> dict:
        packages = self.coordinator.data.packages
        return {"packages": packages}
