"""Async client for scraping package/delivery info from BuildingLink.

BuildingLink has no public API for this, so this client reproduces the login
flow used by https://github.com/chrisrosset/buildinglink-mqtt, verified
against a real account with chrome-devtools-mcp:

1. GET the login page, which redirects (via a bit of inline JS) to an
   ``https://auth...`` OIDC login form (client_id "bl-web").
2. GET that form, submit the detected username/password fields plus any
   hidden fields (including the anti-forgery token) back to the form's own
   URL.
3. The response redirects through an OIDC callback that renders a hidden
   auto-submit form (code/id_token/access_token/state); POST those fields to
   BuildingLink's OIDC callback endpoint to finish establishing the
   www.buildinglink.com session cookie.

That session cookie is enough for browsing BuildingLink's pages, but *not*
for the Deliveries data: BuildingLink's "My Deliveries" page
(Deliveries.aspx) now 302-redirects to a client-rendered Vue/single-spa
shell with no server-rendered markup at all. The actual package list is
fetched by that SPA from a separate JSON API (eventlog-us1.buildinglink.com)
authenticated with an OAuth2 *Bearer* access token - not the session cookie.

That access token is obtained via a second, silent OIDC flow the SPA runs
after the main login completes:

4. GET the authorize endpoint again, this time with the SPA's own client_id
   ("bldev-...", distinct from "bl-web"), ``prompt=none``, and
   ``id_token_hint`` set to the id_token from step 3. Because the SSO cookie
   from the main login is already set, this succeeds without user
   interaction and redirects to a "silent renew" landing page with the
   access token in the URL *fragment* (never sent to the server) - so the
   token has to be parsed out of the redirect's Location header directly
   instead of by following it.
5. GET the eventlog API with ``Authorization: Bearer <access_token>`` plus a
   static ``x-api-key`` header (embedded in BuildingLink's frontend bundle;
   not a per-user secret, but may need updating if BuildingLink rotates it).
   The response is a plain JSON array of delivery events - no HTML parsing
   needed for this part.

BuildingLink's markup/APIs aren't documented and can change or vary by
property, so login field/form detection is intentionally defensive rather
than hardcoded to exact names. Use scripts/manual_test.py to verify against
a real account before relying on this.
"""

from __future__ import annotations

import logging
import re
import secrets
import time
from urllib.parse import parse_qsl, urlencode, urljoin

import aiohttp
from bs4 import BeautifulSoup, Tag

from .const import (
    ACCESS_TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS,
    AUTHORIZE_URL,
    EVENTLOG_ACCEPT_HEADER,
    EVENTLOG_API_KEY,
    EVENTLOG_DELIVERIES_URL,
    LOGIN_URL,
    OIDC_CALLBACK_URL,
    SILENT_RENEW_CLIENT_ID,
    SILENT_RENEW_REDIRECT_URI,
    SILENT_RENEW_SCOPE,
)

_LOGGER = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; HomeAssistantBuildingLink/0.1; "
        "+https://github.com/derekjobst/ha-buildinglink-packages)"
    )
}

_AUTH_REDIRECT_RE = re.compile(r"https://auth[^\s'\"<>]+")

_LOGIN_FAILURE_MARKERS = (
    "invalid username or password",
    "invalid login",
    "incorrect password",
    "we don't recognize",
    "authentication failed",
    "the username or password",
    "your account has been locked",
)


class BuildingLinkError(Exception):
    """Generic error talking to BuildingLink."""


class BuildingLinkAuthError(BuildingLinkError):
    """Raised when BuildingLink rejects the configured credentials."""


class BuildingLinkClient:
    """Handles authentication and delivery lookups against BuildingLink."""

    def __init__(
        self, session: aiohttp.ClientSession, username: str, password: str
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._logged_in = False
        self._id_token: str | None = None
        self._access_token: str | None = None
        self._access_token_expiry = 0.0

    async def async_test_credentials(self) -> None:
        """Attempt a login, raising BuildingLinkAuthError if credentials are bad."""
        await self.async_login()

    async def async_get_deliveries(self) -> dict:
        """Return {"count": int, "packages": list[dict]} of open deliveries."""
        if not self._logged_in:
            await self.async_login()

        return await self._async_fetch_deliveries(allow_relogin=True)

    async def async_login(self) -> None:
        """Run the full BuildingLink login flow, establishing a session."""
        self._logged_in = False
        self._access_token = None

        login_html, _ = await self._get(LOGIN_URL)

        match = _AUTH_REDIRECT_RE.search(login_html)
        if not match:
            raise BuildingLinkError(
                "Could not find BuildingLink auth redirect URL - the login "
                "page layout may have changed"
            )
        auth_url = match.group(0).replace("&amp;", "&")

        auth_html, auth_page_url = await self._get(auth_url)
        form_action, hidden_fields = self._parse_form(auth_html, auth_page_url)
        username_field, password_field = self._detect_login_fields(auth_html)

        if not username_field or not password_field:
            raise BuildingLinkError(
                "Could not detect BuildingLink's username/password form fields"
            )

        payload = dict(hidden_fields)
        payload[username_field] = self._username
        payload[password_field] = self._password

        callback_html, _ = await self._post(form_action, payload)
        oidc_fields = self._parse_hidden_inputs(callback_html)

        if not oidc_fields:
            if self._contains_login_failure(callback_html):
                raise BuildingLinkAuthError(
                    "BuildingLink rejected the username or password"
                )
            raise BuildingLinkError(
                "Unexpected response after submitting BuildingLink credentials"
            )

        id_token = oidc_fields.get("id_token")

        final_html, final_url = await self._post(OIDC_CALLBACK_URL, oidc_fields)

        if self._looks_like_login_page(final_url) or self._contains_login_failure(
            final_html
        ):
            raise BuildingLinkAuthError("BuildingLink login did not complete")

        if not id_token:
            raise BuildingLinkError(
                "BuildingLink login succeeded but did not return an id_token "
                "needed to fetch an API access token"
            )

        self._id_token = id_token
        self._logged_in = True

        # Fail fast here (rather than on the first coordinator poll) so
        # config flow validation catches a broken token exchange too.
        await self._async_refresh_access_token()

    async def _async_fetch_deliveries(self, allow_relogin: bool) -> dict:
        if not self._access_token_valid():
            await self._async_refresh_access_token()

        headers = {
            **_HEADERS,
            "Authorization": f"Bearer {self._access_token}",
            "x-api-key": EVENTLOG_API_KEY,
            "Accept": EVENTLOG_ACCEPT_HEADER,
        }
        try:
            async with self._session.get(
                EVENTLOG_DELIVERIES_URL, headers=headers
            ) as resp:
                if resp.status == 401 and allow_relogin:
                    _LOGGER.debug(
                        "Eventlog API rejected the access token, re-authenticating"
                    )
                    await self.async_login()
                    return await self._async_fetch_deliveries(allow_relogin=False)
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise BuildingLinkError(
                f"Error fetching {EVENTLOG_DELIVERIES_URL}: {err}"
            ) from err

        return self._parse_deliveries(data)

    async def _async_refresh_access_token(self) -> None:
        """Silently obtain an eventlog API access token via the SPA's OIDC client."""
        if not self._id_token:
            raise BuildingLinkError(
                "Cannot refresh BuildingLink API access token without an id_token"
            )

        params = {
            "client_id": SILENT_RENEW_CLIENT_ID,
            "redirect_uri": SILENT_RENEW_REDIRECT_URI,
            "response_type": "id_token token",
            "scope": SILENT_RENEW_SCOPE,
            "state": secrets.token_hex(16),
            "nonce": secrets.token_hex(16),
            "prompt": "none",
            "id_token_hint": self._id_token,
        }
        url = f"{AUTHORIZE_URL}?{urlencode(params)}"

        try:
            async with self._session.get(
                url, headers=_HEADERS, allow_redirects=False
            ) as resp:
                location = resp.headers.get("Location")
        except aiohttp.ClientError as err:
            raise BuildingLinkError(
                f"Error requesting BuildingLink API access token: {err}"
            ) from err

        if not location or "#" not in location:
            raise BuildingLinkAuthError(
                "BuildingLink silent token renewal did not redirect with a "
                "token fragment - the session may have expired"
            )

        fragment = location.split("#", 1)[1]
        token_data = dict(parse_qsl(fragment))
        access_token = token_data.get("access_token")

        if not access_token:
            raise BuildingLinkAuthError(
                "BuildingLink silent token renewal did not return an access_token"
            )

        try:
            expires_in = int(token_data.get("expires_in", ""))
        except ValueError:
            expires_in = 3600

        self._access_token = access_token
        self._access_token_expiry = time.monotonic() + max(
            expires_in - ACCESS_TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS, 0
        )

    def _access_token_valid(self) -> bool:
        return (
            self._access_token is not None
            and time.monotonic() < self._access_token_expiry
        )

    async def _get(self, url: str) -> tuple[str, str]:
        try:
            async with self._session.get(url, headers=_HEADERS) as resp:
                resp.raise_for_status()
                return await resp.text(), str(resp.url)
        except aiohttp.ClientError as err:
            raise BuildingLinkError(f"Error fetching {url}: {err}") from err

    async def _post(self, url: str, data: dict) -> tuple[str, str]:
        try:
            async with self._session.post(url, data=data, headers=_HEADERS) as resp:
                resp.raise_for_status()
                return await resp.text(), str(resp.url)
        except aiohttp.ClientError as err:
            raise BuildingLinkError(f"Error posting to {url}: {err}") from err

    @staticmethod
    def _looks_like_login_page(url: str) -> bool:
        lowered = url.lower()
        return "login" in lowered or "://auth" in lowered

    @staticmethod
    def _contains_login_failure(html: str) -> bool:
        lowered = html.lower()
        return any(marker in lowered for marker in _LOGIN_FAILURE_MARKERS)

    @staticmethod
    def _parse_hidden_inputs(html: str) -> dict[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        return {
            inp["name"]: inp.get("value", "")
            for inp in soup.find_all("input", type="hidden")
            if inp.get("name")
        }

    @staticmethod
    def _parse_form(html: str, page_url: str) -> tuple[str, dict[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        form = soup.find("form")
        if form is None:
            return page_url, {}
        action = form.get("action") or ""
        resolved_action = urljoin(page_url, action)
        hidden_fields = {
            inp["name"]: inp.get("value", "")
            for inp in form.find_all("input", type="hidden")
            if inp.get("name")
        }
        return resolved_action, hidden_fields

    @staticmethod
    def _detect_login_fields(html: str) -> tuple[str | None, str | None]:
        soup = BeautifulSoup(html, "html.parser")
        scope: Tag = soup.find("form") or soup

        password_input = scope.find("input", {"type": "password"})
        password_field = password_input.get("name") if password_input else None

        username_field = None
        for inp in scope.find_all("input"):
            itype = (inp.get("type") or "text").lower()
            name = inp.get("name") or ""
            if itype in ("hidden", "password", "submit", "button", "checkbox") or not name:
                continue
            if any(keyword in name.lower() for keyword in ("user", "email", "login")):
                username_field = name
                break

        if username_field is None:
            for inp in scope.find_all("input"):
                itype = (inp.get("type") or "text").lower()
                name = inp.get("name") or ""
                if itype in ("text", "email") and name:
                    username_field = name
                    break

        return username_field, password_field

    @staticmethod
    def _parse_deliveries(events: list[dict]) -> dict:
        packages = [
            {
                "id": event.get("id"),
                "carrier": event.get("eventTypeName"),
                "comment": event.get("openComment"),
                "received": event.get("openUtc"),
            }
            for event in events
        ]
        return {"count": len(packages), "packages": packages}
