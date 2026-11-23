"""A fixed winter morning so the demo and the tests do not need the network."""

from __future__ import annotations

from hearthline.aqi import aqi_from_pm25, parse_air
from hearthline.models import AirNow, Household

_HOURLY_PM = [186, 190, 170, 140, 110, 80, 62, 58, 64, 90, 130, 170, 190, 180, 160, 140, 120, 100]


def sample_household() -> Household:
    return Household(
        city="Delhi, India",
        latitude=28.6139,
        longitude=77.2090,
        adults=2,
        children=2,
        older_adults=1,
        sensitive=True,
        heating="none",
        cooking="gas",
        purifier=False,
        commute="car",
        distance="2_to_8",
        transit_available=True,
        outdoor_exercise=True,
        school_run=True,
        burns_waste=True,
        audience="household",
    )


def sample_payload() -> dict:
    times = []
    for offset, _pm in enumerate(_HOURLY_PM):
        hour = 8 + offset
        times.append(f"2026-01-15T{hour % 24:02d}:00")
    return {
        "current": {"time": "2026-01-15T08:00", "pm2_5": 186.4, "us_aqi": aqi_from_pm25(186.4)},
        "hourly": {"time": times, "pm2_5": _HOURLY_PM},
    }


def sample_air() -> AirNow:
    return parse_air(sample_payload(), "Delhi, India", source="sample")
