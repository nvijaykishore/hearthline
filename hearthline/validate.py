"""Reject anything that is not a household day we can reason about."""

from __future__ import annotations

import re
from typing import TypeVar

from hearthline.models import (
    AUDIENCE,
    COMMUTE,
    COOKING,
    DISTANCE,
    HEATING,
    Household,
)

_CITY = re.compile(r"^[\w\s,.'’()\-]+$", re.UNICODE)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

_REQUIRED = frozenset(
    {
        "city",
        "adults",
        "children",
        "older_adults",
        "sensitive",
        "heating",
        "cooking",
        "purifier",
        "commute",
        "distance",
        "transit_available",
        "outdoor_exercise",
        "school_run",
        "burns_waste",
        "audience",
    }
)
_OPTIONAL = frozenset({"latitude", "longitude"})
_V = TypeVar("_V")


class ValidationError(Exception):
    def __init__(self, fields: dict[str, str]):
        self.fields = fields
        super().__init__("Check the highlighted fields.")


def _number(value: object, name: str, errors: dict[str, str]) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        errors[name] = "Use a whole number."
        return None
    if value < 0 or value > 12:
        errors[name] = "Use a number from 0 to 12."
        return None
    return value


def _bool(value: object, name: str, errors: dict[str, str]) -> bool | None:
    if not isinstance(value, bool):
        errors[name] = "Choose yes or no."
        return None
    return value


def _enum(value: object, name: str, allowed: tuple[str, ...], errors: dict[str, str]) -> str | None:
    if not isinstance(value, str) or value not in allowed:
        errors[name] = "Choose one of the listed options."
        return None
    return value


def _coord(value: object, name: str, lo: float, hi: float, errors: dict[str, str]) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors[name] = "Pick a place from the list."
        return None
    number = float(value)
    if not lo <= number <= hi:
        errors[name] = f"That {name} is out of range."
        return None
    return number


def _coordinates(payload: dict, errors: dict[str, str]) -> tuple[float | None, float | None]:
    lat = payload.get("latitude", None)
    lon = payload.get("longitude", None)
    if lat is None and lon is None:
        return None, None
    return (
        _coord(lat, "latitude", -90.0, 90.0, errors),
        _coord(lon, "longitude", -180.0, 180.0, errors),
    )


def _read_city(value: object, errors: dict[str, str]) -> str:
    if not isinstance(value, str):
        errors["city"] = "Enter a city."
        return ""
    city_clean = _CONTROL.sub("", value).strip()
    if not (2 <= len(city_clean) <= 120) or not _CITY.match(city_clean):
        errors["city"] = "Use the place name, up to 120 characters."
    return city_clean


def _known(value: _V | None) -> _V:
    """A field that survived validation. Asserts disappear under python -O."""
    if value is None:
        raise ValidationError({"form": "Check the highlighted fields."})
    return value


def _people(payload: dict, errors: dict[str, str]) -> tuple[int | None, int | None, int | None]:
    adults = _number(payload.get("adults"), "adults", errors)
    children = _number(payload.get("children"), "children", errors)
    older = _number(payload.get("older_adults"), "older_adults", errors)
    if None not in (adults, children, older):
        total = adults + children + older
        if total < 1 or total > 16:
            errors["adults"] = "The household needs between 1 and 16 people."
        elif adults + older < 1:
            errors["adults"] = "Include at least one adult or older adult."
    return adults, children, older


def city_from(value: object) -> str:
    errors: dict[str, str] = {}
    city = _read_city(value, errors)
    if errors:
        raise ValidationError(errors)
    return city


def household_from(payload: object) -> Household:
    if not isinstance(payload, dict):
        raise ValidationError({"form": "Send the household as a JSON object."})
    errors: dict[str, str] = {}
    unknown = set(payload) - _REQUIRED - _OPTIONAL
    if unknown:
        errors["form"] = "Remove fields this plan does not use."

    city_clean = _read_city(payload.get("city"), errors)
    adults, children, older = _people(payload, errors)
    heating = _enum(payload.get("heating"), "heating", HEATING, errors)
    cooking = _enum(payload.get("cooking"), "cooking", COOKING, errors)
    commute = _enum(payload.get("commute"), "commute", COMMUTE, errors)
    distance = _enum(payload.get("distance"), "distance", DISTANCE, errors)
    audience = _enum(payload.get("audience"), "audience", AUDIENCE, errors)

    sensitive = _bool(payload.get("sensitive"), "sensitive", errors)
    purifier = _bool(payload.get("purifier"), "purifier", errors)
    transit = _bool(payload.get("transit_available"), "transit_available", errors)
    exercise = _bool(payload.get("outdoor_exercise"), "outdoor_exercise", errors)
    school = _bool(payload.get("school_run"), "school_run", errors)
    burns = _bool(payload.get("burns_waste"), "burns_waste", errors)

    latitude, longitude = _coordinates(payload, errors)

    if errors:
        raise ValidationError(errors)
    return Household(
        city=city_clean,
        latitude=0.0 if latitude is None else latitude,
        longitude=0.0 if longitude is None else longitude,
        adults=_known(adults),
        children=_known(children),
        older_adults=_known(older),
        sensitive=_known(sensitive),
        heating=_known(heating),
        cooking=_known(cooking),
        purifier=_known(purifier),
        commute=_known(commute),
        distance=_known(distance),
        transit_available=_known(transit),
        outdoor_exercise=_known(exercise),
        school_run=_known(school),
        burns_waste=_known(burns),
        audience=_known(audience),
    )


def coordinates_supplied(payload: object) -> bool:
    return isinstance(payload, dict) and "latitude" in payload and "longitude" in payload


def question_from(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ValidationError({"form": "Send a question and the household."})
    question = payload.get("question")
    if not isinstance(question, str):
        raise ValidationError({"question": "Enter a question."})
    clean = _CONTROL.sub("", question).strip()
    if not clean:
        raise ValidationError({"question": "Enter a question."})
    if len(clean) > 400:
        raise ValidationError({"question": "Keep the question under 400 characters."})
    return clean
