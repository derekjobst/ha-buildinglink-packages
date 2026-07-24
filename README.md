# BuildingLink Packages for Home Assistant

A native Home Assistant custom integration that reports how many packages
are waiting for you in your building's mail room, by logging into your
[BuildingLink](https://www.buildinglink.com) tenant portal and scraping the
Deliveries page. No MQTT broker or external process required.

Inspired by [chrisrosset/buildinglink-mqtt](https://github.com/chrisrosset/buildinglink-mqtt),
which does the same thing as a standalone script that publishes to MQTT.
This integration reimplements the login/scrape logic directly inside Home
Assistant as a config-flow integration with a polling coordinator.

## What you get

- `sensor.<name>_packages` — state is the number of packages currently
  waiting, with an `packages` attribute containing a best-effort parse of
  each row on the Deliveries page (columns vary by property, so this is
  parsed generically).
- Config flow: enter your BuildingLink username/password in the HA UI.
- Options flow: adjust the polling interval (default 15 minutes, 5–1440
  allowed). BuildingLink's login flow is heavier than a typical API call —
  don't poll too aggressively.
- Reauth flow if BuildingLink rejects the stored credentials.

## Known limitations

- **No 2FA/MFA support.** If your BuildingLink account has a second factor
  enabled, this login flow (same as the reference project) won't complete
  it. Use an account/property login without 2FA, if possible.
- **Markup may vary by property.** BuildingLink doesn't have a public API;
  this integration parses the same HTML the reference project used
  (login form field detection, and the `#ctl00_ContentPlaceHolder1_GridDeliveries_ctl00`
  table on `V2/Tenant/Deliveries/Deliveries.aspx`). If your property's portal
  differs, `custom_components/buildinglink/api.py` and `const.py` are the
  places to adjust it.

## Installing

### Option A: HACS custom repository

1. HACS → Integrations → ⋮ → Custom repositories → add this repo URL as
   an "Integration".
2. Install "BuildingLink", restart Home Assistant.

### Option B: Manual copy

Copy `custom_components/buildinglink/` into your HA config's
`custom_components/` directory (e.g. via the Samba, SSH, or File Editor
add-on if you're on HAOS), then restart Home Assistant.

Then: **Settings → Devices & Services → Add Integration → BuildingLink**,
and enter your BuildingLink credentials.

## Testing the scraper before installing

Because the login flow is essentially screen-scraping (there's no public
BuildingLink API), it's worth confirming it works against your specific
account/property before wiring it into HA — that way scraper issues and HA
integration issues aren't tangled together, and you're not restarting HA
repeatedly to debug it.

```bash
pip install aiohttp beautifulsoup4
BUILDINGLINK_USERNAME=you@example.com BUILDINGLINK_PASSWORD=hunter2 \
    python scripts/manual_test.py
```

If this fails, the error message (and BuildingLink's actual HTML, which
you can inspect via your browser's dev tools on the login/Deliveries pages)
should point at what changed in `api.py`.
