"""Reject anything that is not a household day we can reason about."""

from __future__ import annotations

import re

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

_FIELDS = {
    "city": str,
    "adults": int,
    "children": int,
    "older_adults": int,
    "sensitive": bool,
    "heating": str,
    "cooking": str,
    "purifier": bool,
    "commute": str,
    "distance": str,
    "transit_available": bool,
    "outdoor_exercise": bool,
    "school_run": bool,
    "burns_waste": bool,
    "audience": str,
}

_OPTIONAL = {"latitude": float, "longitude": float}


class ValidationError(Exception):
    def __init__(self, fields: dict[str, str]):
        self.fields = fields
        super().__init__("Check the highlighted fields.")


def _number(value, name: str, errors: dict) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        errors[name] = "Use a whole number."
        return None
    if value < 0 or value > 12:
        errors[name] = "Use a number from 0 to 12."
        return None
    return value


def _bool(value, name: str, errors: dict) -> bool | None:
    if not isinstance(value, bool):
        errors[name] = "Choose yes or no."
        return None
    return value


def _enum(value, name: str, allowed: tuple, errors: dict) -> str | None:
    if not isinstance(value, str) or value not in allowed:
        errors[name] = "Choose one of the listed options."
        return None
    return value


def household_from(payload: object) -> Household:
    if not isinstance(payload, dict):
        raise ValidationError({"form": "Send the household as a JSON object."})
    errors: dict[str, str] = {}
    unknown = set(payload) - set(_FIELDS) - set(_OPTIONAL)
    if unknown:
        errors["form"] = "Remove fields this plan does not use."

    city = payload.get("city")
    if not isinstance(city, str):
        errors["city"] = "Enter a city."
        city_clean = ""
    else:
        city_clean = _CONTROL.sub("", city).strip()
        if not (2 <= len(city_clean) <= 120) or not _CITY.match(city_clean):
            errors["city"] = "Use the place name, up to 120 characters."

    adults = _number(payload.get("adults"), "adults", errors)
    children = _number(payload.get("children"), "children", errors)
    older = _number(payload.get("older_adults"), "older_adults", errors)
    if None not in (adults, children, older):
        total = adults + children + older
        if total < 1 or total > 16:
            errors["adults"] = "The household needs between 1 and 16 people."
        elif adults + older < 1:
            errors["adults"] = "Include at least one adult or older adult."

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

    lat = payload.get("latitude", None)
    lon = payload.get("longitude", None)
    if lat is None and lon is None:
        latitude = longitude = None
    else:
        latitude = longitude = None
        if isinstance(lat, bool) or not isinstance(lat, (int, float)):
            errors["latitude"] = "Pick a place from the list."
        elif not -90 <= float(lat) <= 90:
            errors["latitude"] = "That latitude is out of range."
        else:
            latitude = float(lat)
        if isinstance(lon, bool) or not isinstance(lon, (int, float)):
            errors["longitude"] = "Pick a place from the list."
        elif not -180 <= float(lon) <= 180:
            errors["longitude"] = "That longitude is out of range."
        else:
            longitude = float(lon)

    if errors:
        raise ValidationError(errors)
    return Household(
        city=city_clean,
        latitude=0.0 if latitude is None else latitude,
        longitude=0.0 if longitude is None else longitude,
        adults=adults,
        children=children,
        older_adults=older,
        sensitive=sensitive,
        heating=heating,
        cooking=cooking,
        purifier=purifier,
        commute=commute,
        distance=distance,
        transit_available=transit,
        outdoor_exercise=exercise,
        school_run=school,
        burns_waste=burns,
        audience=audience,
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
