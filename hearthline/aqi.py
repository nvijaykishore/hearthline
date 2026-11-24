"""Air index, Open-Meteo fetch, and the cleaner-hours window.

The US AQI number is a communication scale. Dose math uses PM2.5
micrograms, not the index. Open-Meteo is a model mosaic, not a
regulatory monitor, so callers keep that label attached to the reading.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from hearthline.models import AirNow

# EPA PM2.5 breakpoints (µg/m³, 1 decimal) and AQI breakpoints.
_PM_BANDS = (
    (0.0, 12.0, 0, 50),
    (12.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 150.4, 151, 200),
    (150.5, 250.4, 201, 300),
    (250.5, 350.4, 301, 400),
    (350.5, 500.4, 401, 500),
)

ALLOWED_HOSTS = frozenset(
    {
        "air-quality-api.open-meteo.com",
        "geocoding-api.open-meteo.com",
        "api.x.ai",
    }
)

USER_AGENT = "Hearthline/1.0 (family air plan; educational)"
WHO_PM25_24H = 15.0


class AirError(Exception):
    """A failure the household can act on. The message is safe to show."""


def category_for(aqi: int) -> str:
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Moderate"
    if aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    if aqi <= 200:
        return "Unhealthy"
    if aqi <= 300:
        return "Very Unhealthy"
    return "Hazardous"


def truncate_pm(concentration: float) -> float:
    """EPA truncates PM2.5 to one decimal before the index formula."""
    if concentration < 0:
        raise AirError("PM2.5 cannot be negative.")
    return math.floor(concentration * 10.0 + 1e-9) / 10.0


def aqi_from_pm25(concentration: float) -> int:
    c = truncate_pm(concentration)
    if c > 500.4:
        return 500
    for lo, hi, ilo, ihi in _PM_BANDS:
        if lo <= c <= hi:
            if hi == lo:
                return ilo
            value = (ihi - ilo) / (hi - lo) * (c - lo) + ilo
            return int(value + 0.5)
    return 0


def hour_label(iso: str) -> str:
    if "T" in iso:
        return iso.split("T", 1)[1][:5]
    return iso[:5]


def cleanest_window(
    times: list[str],
    values: list[object],
    observed: str,
    width: int = 3,
    horizon: int = 18,
) -> tuple[float, str, str] | None:
    """Lowest mean PM2.5 across `width` hours inside the next `horizon`."""
    if not times or not values:
        return None
    start = 0
    for i, stamp in enumerate(times):
        if str(stamp) >= observed:
            start = i
            break
    end = min(len(times), len(values), start + horizon)
    best: tuple[float, str, str] | None = None
    for i in range(start, end - width + 1):
        chunk = values[i : i + width]
        if any(v is None for v in chunk):
            continue
        try:
            nums = [float(v) for v in chunk]
        except (TypeError, ValueError):
            continue
        mean = sum(nums) / float(width)
        if best is None or mean < best[0]:
            best = (mean, str(times[i]), str(times[i + width - 1]))
    return best


def parse_air(payload: dict, place_label: str, source: str = "open-meteo") -> AirNow:
    if not isinstance(payload, dict):
        raise AirError("The air service returned something we could not read.")
    current = payload.get("current")
    if not isinstance(current, dict) or current.get("pm2_5") is None:
        raise AirError("The air service did not return PM2.5 for this place.")
    try:
        pm = float(current["pm2_5"])
    except (TypeError, ValueError) as exc:
        raise AirError("The air service returned a PM2.5 value we could not read.") from exc
    pm_aqi = aqi_from_pm25(pm)
    raw_us = current.get("us_aqi")
    if raw_us is None:
        us_aqi = pm_aqi
    else:
        try:
            us_aqi = int(float(raw_us) + 0.5)
        except (TypeError, ValueError):
            us_aqi = pm_aqi
    us_aqi = max(0, min(500, us_aqi))
    observed = str(current.get("time") or "")
    hourly = payload.get("hourly") if isinstance(payload.get("hourly"), dict) else {}
    window = cleanest_window(
        [str(stamp) for stamp in (hourly.get("time") or [])],
        list(hourly.get("pm2_5") or []),
        observed,
    )
    clean_pm = clean_start = clean_end = None
    if window is not None:
        clean_pm, clean_start, clean_end = window
    if source == "sample":
        note = "Illustrative winter morning for this city, not a live reading."
    else:
        note = "Current model reading, not an official 24-hour government AQI."
    return AirNow(
        pm2_5=pm,
        us_aqi=us_aqi,
        category=category_for(us_aqi),
        pm_aqi=pm_aqi,
        observed_at=observed,
        clean_pm2_5=clean_pm,
        clean_start=clean_start,
        clean_end=clean_end,
        source=source,
        place_label=place_label,
        note=note,
    )


def allowed_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS


def fetch_json(url: str, timeout: float = 8.0) -> dict:
    if not allowed_url(url):
        raise AirError("Refused a request to an unexpected service.")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(1_000_000)
    except urllib.error.HTTPError as exc:
        raise AirError("The air service rejected the request. Try another place.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AirError("The air service did not respond. Check the connection and try again.") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AirError("The air service returned something we could not read.") from exc
    if not isinstance(data, dict):
        raise AirError("The air service returned something we could not read.")
    return data


def air_url(latitude: float, longitude: float) -> str:
    query = urllib.parse.urlencode(
        {
            "latitude": f"{latitude:.4f}",
            "longitude": f"{longitude:.4f}",
            "current": "us_aqi,pm2_5,pm10,nitrogen_dioxide,sulphur_dioxide,ozone,carbon_monoxide",
            "hourly": "pm2_5,us_aqi",
            "timezone": "auto",
            "forecast_days": 2,
        }
    )
    return f"https://air-quality-api.open-meteo.com/v1/air-quality?{query}"


def geocode_url(name: str) -> str:
    query = urllib.parse.urlencode(
        {"name": name, "count": 5, "language": "en", "format": "json"}
    )
    return f"https://geocoding-api.open-meteo.com/v1/search?{query}"


def _place_label(row: dict) -> str:
    parts = []
    for key in ("name", "admin1", "country"):
        value = str(row.get(key) or "").strip()
        if value and value not in parts:
            parts.append(value)
    return ", ".join(parts)


def search_places(name: str, fetch: Callable[[str], dict] = fetch_json) -> list[dict]:
    data = fetch(geocode_url(name))
    found: list[dict] = []
    for row in data.get("results") or []:
        if not isinstance(row, dict):
            continue
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        found.append(
            {
                "label": _place_label(row),
                "latitude": lat,
                "longitude": lon,
                "country": str(row.get("country") or ""),
            }
        )
    return found


def load_air(
    latitude: float,
    longitude: float,
    place_label: str,
    fetch: Callable[[str], dict] = fetch_json,
) -> AirNow:
    payload = fetch(air_url(latitude, longitude))
    return parse_air(payload, place_label, source="open-meteo")
