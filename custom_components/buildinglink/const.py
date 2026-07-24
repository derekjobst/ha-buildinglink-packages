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

# The Deliveries page (Deliveries.aspx, which now 302-redirects to a Vue SPA
# shell called VueAppWrapper.aspx) has no server-rendered markup to scrape -
# the actual package list is fetched client-side from a separate JSON API
# (see EVENTLOG_* below) using an OAuth2 access token, not the session cookie.
AUTH_BASE_URL: Final = "https://auth.buildinglink.com"
AUTHORIZE_URL: Final = f"{AUTH_BASE_URL}/connect/authorize"

# The SPA obtains its API access token via a second, silent OIDC flow that
# runs after the main cookie-session login, using its own client_id (distinct
# from the "bl-web" client used for LOGIN_URL) and the id_token from the main
# login as an id_token_hint. This relies on the SSO cookie set by the main
# login, so prompt=none succeeds without user interaction.
SILENT_RENEW_CLIENT_ID: Final = "bldev-5de7b827f6c6fc02789b950e"
SILENT_RENEW_REDIRECT_URI: Final = f"{BUILDINGLINK_BASE_URL}/voidc-silent-renew"
SILENT_RENEW_SCOPE: Final = (
    "openid profile email buildinglink internal_website_apis uuids"
)
ACCESS_TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS: Final = 60

# Package/delivery data lives in BuildingLink's "event log" service, on a
# separate host from www.buildinglink.com, authenticated with the OAuth2
# Bearer token above plus a static API-gateway key that's embedded in the
# vue-event-log frontend bundle (public to any logged-in browser session,
# not a per-user secret). It may need updating if BuildingLink rotates it.
EVENTLOG_BASE_URL: Final = "https://eventlog-us1.buildinglink.com"
EVENTLOG_DELIVERIES_URL: Final = f"{EVENTLOG_BASE_URL}/event-log/resident"
EVENTLOG_API_KEY: Final = "hylwvvmjdgc45mt9kab1agriyvuh0nig9qx8djmu"
EVENTLOG_ACCEPT_HEADER: Final = (
    "application/json; odata.metadata=minimal; odata.streaming=true"
)

ATTRIBUTION: Final = "Data provided by BuildingLink"
