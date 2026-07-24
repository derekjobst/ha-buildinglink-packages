"""Constants for the BuildingLink integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "buildinglink"

CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_SCAN_INTERVAL_MINUTES: Final = 15
MIN_SCAN_INTERVAL_MINUTES: Final = 5
MAX_SCAN_INTERVAL_MINUTES: Final = 1440
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES)

BUILDINGLINK_BASE_URL: Final = "https://www.buildinglink.com"
LOGIN_URL: Final = f"{BUILDINGLINK_BASE_URL}/v2/global/login/login.aspx"
OIDC_CALLBACK_URL: Final = f"{BUILDINGLINK_BASE_URL}/v2/oidc-callback"
DELIVERIES_URL: Final = f"{BUILDINGLINK_BASE_URL}/V2/Tenant/Deliveries/Deliveries.aspx"

DELIVERIES_TABLE_ID: Final = "ctl00_ContentPlaceHolder1_GridDeliveries_ctl00"
NO_RECORDS_ROW_CLASS: Final = "rgNoRecords"

ATTRIBUTION: Final = "Data provided by BuildingLink"
