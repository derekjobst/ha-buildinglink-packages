"""Async client for scraping package/delivery info from BuildingLink.

BuildingLink has no public API for this, so this client reproduces the login
flow and page scraping used by https://github.com/chrisrosset/buildinglink-mqtt:

1. GET the login page, which redirects (via a bit of inline JS) to an
   ``https://auth...`` OIDC login form.
2. GET that form, submit the detected username/password fields plus any
   hidden fields back to the form's action URL.
3. The response contains a hidden auto-submit form (id_token/code/state);
   POST those fields to BuildingLink's OIDC callback endpoint to finish
   establishing the session.
4. GET the Deliveries page and parse the packages table.

BuildingLink's markup isn't documented and can change or vary by property,
so field/table detection here is intentionally defensive rather than
hardcoded to exact names. Use scripts/manual_test.py to verify against a
real account before relying on this.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup, Tag

from .const import (
    DELIVERIES_TABLE_ID,
    DELIVERIES_URL,
    LOGIN_URL,
    NO_RECORDS_ROW_CLASS,
    OIDC_CALLBACK_URL,
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

    async def async_test_credentials(self) -> None:
        """Attempt a login, raising BuildingLinkAuthError if credentials are bad."""
        await self.async_login()

    async def async_get_deliveries(self) -> dict:
        """Return {"count": int, "packages": list[dict]} from the Deliveries page."""
        if not self._logged_in:
            await self.async_login()

        html, url = await self._get(DELIVERIES_URL)
        if self._looks_like_login_page(url):
            _LOGGER.debug("Session appears expired, re-authenticating")
            self._logged_in = False
            await self.async_login()
            html, url = await self._get(DELIVERIES_URL)
            if self._looks_like_login_page(url):
                raise BuildingLinkAuthError(
                    "Session expired and re-login did not restore access"
                )

        return self._parse_deliveries(html)

    async def async_login(self) -> None:
        """Run the full BuildingLink login flow, establishing a session."""
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

        final_html, final_url = await self._post(OIDC_CALLBACK_URL, oidc_fields)

        if self._looks_like_login_page(final_url) or self._contains_login_failure(
            final_html
        ):
            raise BuildingLinkAuthError("BuildingLink login did not complete")

        self._logged_in = True

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
    def _parse_deliveries(html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find(id=DELIVERIES_TABLE_ID)
        if table is None:
            raise BuildingLinkError(
                "Deliveries table not found - BuildingLink's page layout may "
                "have changed"
            )

        tbody = table.find("tbody") or table
        rows = tbody.find_all("tr")
        data_rows = [
            row for row in rows if NO_RECORDS_ROW_CLASS not in (row.get("class") or [])
        ]

        headers: list[str] = []
        thead = table.find("thead")
        if thead:
            headers = [th.get_text(strip=True) for th in thead.find_all("th")]

        packages = []
        for row in data_rows:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if not cells:
                continue
            if headers and len(headers) == len(cells):
                packages.append(dict(zip(headers, cells)))
            else:
                packages.append(
                    {f"column_{i + 1}": value for i, value in enumerate(cells)}
                )

        return {"count": len(data_rows), "packages": packages}
