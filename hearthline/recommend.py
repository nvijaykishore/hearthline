"""Choose the recommended day. Arithmetic stays in impact.py."""

from __future__ import annotations

from dataclasses import replace

from hearthline.impact import (
    EXERCISE_H,
    clean_is_useful,
    exercise_kind,
    exercise_vent,
    indoor_parts,
    outdoor_limit,
    trip_inhaled_ug,
)
from hearthline.models import AirNow, Household, Scenario


def baseline_scenario(household: Household) -> Scenario:
    wait = 10.0 if household.school_run else 0.0
    car_school = household.school_run and household.commute in ("car", "wfh")
    return Scenario(
        work_mode=household.commute,
        school_mode="car" if household.school_run and household.commute == "wfh" else "none",
        exercise="outdoor_now" if household.outdoor_exercise else "none",
        mask=False,
        purifier_mode="off",
        cook_controlled=False,
        heat_controlled=False,
        burns=household.burns_waste,
        school_wait_min=wait,
        idle_min=wait if car_school else 0.0,
    )


def _candidate_work_mode(household: Household, air: AirNow) -> str:
    if household.commute != "car":
        return household.commute
    bad = air.us_aqi >= outdoor_limit(household)
    if household.distance == "under_2" and not bad:
        return "walk"
    if household.transit_available:
        return "metro"
    return "car"


def _accept_swap(household: Household, air: AirNow, candidate: str, mask: bool) -> bool:
    if candidate == household.commute:
        return True
    # Compare the two modes under the same mask, so a mask is not mistaken
    # for a better vehicle.
    current = replace(baseline_scenario(household), mask=mask)
    proposed = replace(current, work_mode=candidate)
    old = trip_inhaled_ug(household, air, current)
    new = trip_inhaled_ug(household, air, proposed)
    if old <= 0:
        return True
    ratio = new / old
    if air.us_aqi >= 201:
        return ratio <= 1.05
    if air.us_aqi >= 151:
        return ratio <= 1.20
    return ratio <= 1.35


def _choose_exercise(household: Household, air: AirNow, shaped: Scenario) -> str:
    if not household.outdoor_exercise:
        return "none"
    if air.us_aqi < outdoor_limit(household):
        return "outdoor_now"
    kind = exercise_kind(household)
    if kind is None:
        return "none"
    vent = exercise_vent(kind)
    parts = indoor_parts(household, air.pm2_5, shaped)
    indoor_dose = parts["other"] * vent * EXERCISE_H
    outdoor_dose = air.pm2_5 * vent * EXERCISE_H
    best = "indoor"
    best_dose = indoor_dose
    if clean_is_useful(air) and air.clean_pm2_5 is not None:
        clean_dose = air.clean_pm2_5 * vent * EXERCISE_H
        if clean_dose < best_dose:
            best = "outdoor_clean"
            best_dose = clean_dose
    if outdoor_dose < best_dose:
        best = "outdoor_now"
    return best


def _choose_purifier(household: Household, air: AirNow) -> str:
    dirty_home = household.cooking in ("gas", "mixed", "biomass") or household.heating in (
        "gas",
        "wood_coal",
    )
    if household.purifier and (air.us_aqi >= 51 or dirty_home):
        return "hepa"
    if not household.purifier and (
        air.us_aqi >= 101 or household.cooking == "biomass" or household.heating == "wood_coal"
    ):
        return "diy"
    return "off"


def _choose_school_mode(household: Household, air: AirNow) -> str:
    if not household.school_run or household.commute != "wfh":
        return "none"
    bad = air.us_aqi >= outdoor_limit(household)
    if bad and air.us_aqi >= 201:
        return "car"
    if household.transit_available:
        return "metro"
    if not bad:
        return "walk"
    return "car"


def _choose_school_wait(household: Household, air: AirNow) -> float:
    if not household.school_run:
        return 0.0
    if air.us_aqi >= outdoor_limit(household):
        return 1.0
    return 3.0


def recommended_scenario(household: Household, air: AirNow) -> tuple[Scenario, str | None]:
    """Return the plan scenario and, when a lower-emission commute was refused, a short reason."""
    mask = air.us_aqi >= 101
    candidate = _candidate_work_mode(household, air)
    refusal = None
    if candidate != household.commute and not _accept_swap(household, air, candidate, mask):
        refusal = (
            "A switch to transit today means more minutes in the plume than it saves. "
            "Keep the car, set it to recirculate, and leave the engine off at the door."
        )
        candidate = household.commute

    shaped = Scenario(
        work_mode=candidate,
        school_mode=_choose_school_mode(household, air),
        exercise="none",
        mask=mask,
        purifier_mode=_choose_purifier(household, air),
        cook_controlled=True,  # every listed cooking type has a control step
        heat_controlled=household.heating in ("gas", "wood_coal"),
        burns=False,
        school_wait_min=_choose_school_wait(household, air),
        idle_min=0.0,
    )
    exercise = _choose_exercise(household, air, shaped)
    return replace(shaped, exercise=exercise), refusal
