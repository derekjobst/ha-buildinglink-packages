#!/usr/bin/env python3
"""Standalone test of the BuildingLink login + scraping logic, outside of HA.

Usage:
    pip install aiohttp beautifulsoup4
    BUILDINGLINK_USERNAME=you@example.com BUILDINGLINK_PASSWORD=hunter2 \
        python scripts/manual_test.py

This exercises custom_components/buildinglink/api.py and const.py directly
(neither has any Home Assistant imports) so you can debug the login flow and
page parsing against your real BuildingLink account without installing
anything into HA or restarting it between attempts.

custom_components/buildinglink/__init__.py *does* import homeassistant, and
importing "buildinglink.api" normally would run that package __init__ first
and fail outside of HA. To avoid that, this script registers a stub
"buildinglink" package (pointed at the real directory) in sys.modules before
importing the submodules, so api.py/const.py load without ever executing
__init__.py.
"""

from __future__ import annotations

import asyncio
import os
import sys
import types
from pathlib import Path

import aiohttp

_PKG_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "buildinglink"
_stub = types.ModuleType("buildinglink")
_stub.__path__ = [str(_PKG_DIR)]
sys.modules["buildinglink"] = _stub

from buildinglink.api import BuildingLinkAuthError, BuildingLinkClient, BuildingLinkError  # noqa: E402


async def main() -> int:
    username = os.environ.get("BUILDINGLINK_USERNAME")
    password = os.environ.get("BUILDINGLINK_PASSWORD")
    if not username or not password:
        print(
            "Set BUILDINGLINK_USERNAME and BUILDINGLINK_PASSWORD environment "
            "variables first.",
            file=sys.stderr,
        )
        return 1

    async with aiohttp.ClientSession() as session:
        client = BuildingLinkClient(session, username, password)

        print("Logging in...")
        try:
            await client.async_login()
        except BuildingLinkAuthError as err:
            print(f"Auth failed: {err}", file=sys.stderr)
            return 1
        except BuildingLinkError as err:
            print(f"Login flow error: {err}", file=sys.stderr)
            return 1
        print("Login succeeded.")

        print("Fetching deliveries...")
        try:
            result = await client.async_get_deliveries()
        except BuildingLinkError as err:
            print(f"Failed to fetch deliveries: {err}", file=sys.stderr)
            return 1

        print(f"Package count: {result['count']}")
        for i, package in enumerate(result["packages"], start=1):
            print(f"  [{i}] {package}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
