"""Shared shapes. No I/O."""

from __future__ import annotations

from dataclasses import dataclass

HEATING = ("none", "electric", "district", "gas", "wood_coal")
COOKING = ("induction", "gas", "mixed", "biomass")
COMMUTE = ("wfh", "walk", "cycle", "bus", "metro", "car")
DISTANCE = ("under_2", "2_to_8", "over_8")
AUDIENCE = ("household", "school", "block")


@dataclass(frozen=True)
class Household:
    city: str
    latitude: float
    longitude: float
    adults: int
    children: int
    older_adults: int
    sensitive: bool
    heating: str
    cooking: str
    purifier: bool
    commute: str
    distance: str
    transit_available: bool
    outdoor_exercise: bool
    school_run: bool
    burns_waste: bool
    audience: str


@dataclass(frozen=True)
class AirNow:
    pm2_5: float
    us_aqi: int
    category: str
    pm_aqi: int
    observed_at: str
    clean_pm2_5: float | None
    clean_start: str | None
    clean_end: str | None
    source: str
    place_label: str
    note: str


@dataclass(frozen=True)
class Scenario:
    """One way the household might spend the day. Flags are independent so a
    card can show what changes when only that flag is turned off."""

    work_mode: str
    school_mode: str
    exercise: str
    mask: bool
    purifier_mode: str
    cook_controlled: bool
    heat_controlled: bool
    burns: bool
    school_wait_min: float
    idle_min: float


@dataclass(frozen=True)
class DayTotals:
    inhaled_ug: float
    co2e_g: float
    emitted_pm_g: float
