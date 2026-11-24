"""Planning estimates for one household day.

Not a lung model and not a regulatory inventory. Outdoor PM2.5 is taken as
uniform at the reported value. With winter windows closed, indoor air starts
at that value times INFILTRATION_CLOSED, then cooking and heating add to
their own hours only.

Trips and exercise are treated as sequential. When they actually overlap,
time at home is overstated a little. Baseline and plan use the same rule,
so the comparison stays honest even though the absolute micrograms are not
a personal dose.

Card figures turn one choice off inside the full plan. The headline compares
the full plan with the unchanged day. Overlapping choices mean those two
views are not meant to be added together.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from hearthline.aqi import aqi_from_pm25
from hearthline.models import AirNow, DayTotals, Household, Scenario

# Closed-window winter infiltration. Residences span roughly 0.3 to 0.8.
INFILTRATION_CLOSED = 0.55

ADULT_REST = 0.50
CHILD_REST = 0.30
OLDER_REST = 0.42
ADULT_WALK = 1.20
ADULT_EXERCISE = 2.50
CHILD_PLAY = 1.20
OLDER_WALK = 1.00
CYCLE_VENT = 1.80

SLEEP_H = 8.0
COOK_H = 1.5
HEAT_H = 4.0
EXERCISE_H = 40.0 / 60.0
RECESS_H = 20.0 / 60.0

# Added indoor µg/m³ during that activity, on top of infiltrated outdoor air.
COOKING_EXTRA_UG = {
    "induction": 12.0,
    "gas": 40.0,
    "mixed": 70.0,
    "biomass": 180.0,
}
HEATING_EXTRA_UG = {
    "none": 0.0,
    "electric": 0.0,
    "district": 8.0,
    "gas": 25.0,
    "wood_coal": 140.0,
}

# Multiplier on the infiltrated outdoor portion, by where the cleaner sits.
PURIFIER_FACTOR = {
    "off": {"sleep": 1.0, "cook": 1.0, "heat": 1.0, "other": 1.0},
    "hepa": {"sleep": 0.35, "cook": 0.90, "heat": 0.55, "other": 0.65},
    "diy": {"sleep": 0.60, "cook": 0.95, "heat": 0.75, "other": 0.80},
}

COOK_CONTROL = 0.50
HEAT_CONTROL = {
    "none": 1.0,
    "electric": 1.0,
    "district": 1.0,
    "gas": 0.60,
    "wood_coal": 0.50,
}

# Fraction of PM2.5 still inhaled through a well-fitted FFP2 or N95.
MASK_FACTOR = 0.25

# Grams CO2e per passenger-kilometre. Regional averages, not a local inventory.
CO2E_G_PER_PKM = {
    "walk": 0.0,
    "cycle": 0.0,
    "wfh": 0.0,
    "metro": 40.0,
    "bus": 80.0,
    "car": 180.0,
}
DISTANCE_ROUND_KM = {"under_2": 3.0, "2_to_8": 10.0, "over_8": 24.0}
SCHOOL_ONLY_ROUND_KM = 3.0

SPEED_KMH = {"walk": 4.5, "cycle": 15.0}
VEHICLE_MIN_PER_KM = 3.0
ACCESS_MIN = {"car": 2.0, "bus": 8.0, "metro": 8.0}
IN_VEHICLE_PM_FACTOR = {"car": 0.80, "bus": 0.70, "metro": 0.55}

IDLE_G_PER_MIN = 30.0
WOOD_KG = 2.0
WOOD_EF_G_PER_KG = 12.0
WASTE_KG = 2.0
WASTE_EF_G_PER_KG = 8.0

MODE_LABEL = {
    "walk": "walking",
    "cycle": "cycling",
    "bus": "the bus",
    "metro": "the metro",
    "car": "a car",
    "wfh": "working from home",
}

_REST = {"adult": ADULT_REST, "child": CHILD_REST, "older": OLDER_REST}
_WALK = {"adult": ADULT_WALK, "child": CHILD_PLAY, "older": OLDER_WALK}


@dataclass(frozen=True)
class Block:
    hours: float
    conc: float
    vent: float
    absent_rest: float


def outdoor_limit(household: Household) -> int:
    """AQI at which strenuous outdoor time should move. Sensitive households
    include children, older adults, pregnancy, asthma, and heart or lung conditions.
    The form stores only the boolean."""
    if household.sensitive or household.children or household.older_adults:
        return 101
    return 151


def clean_is_useful(air: AirNow) -> bool:
    if air.clean_pm2_5 is None:
        return False
    return air.clean_pm2_5 <= air.pm2_5 - 15 and air.clean_pm2_5 <= air.pm2_5 * 0.70


def heat_hours(household: Household) -> float:
    if household.heating == "none":
        return 0.0
    return HEAT_H


def household_rest(household: Household) -> float:
    return (
        household.adults * ADULT_REST
        + household.children * CHILD_REST
        + household.older_adults * OLDER_REST
    )


def commuter_kind(household: Household) -> str | None:
    if household.adults:
        return "adult"
    if household.older_adults:
        return "older"
    return None


def exercise_kind(household: Household) -> str | None:
    if not household.outdoor_exercise:
        return None
    if household.children:
        return "child"
    if household.adults:
        return "adult"
    if household.older_adults:
        return "older"
    return None


def _rest(kind: str) -> float:
    return _REST[kind]


def _walk(kind: str) -> float:
    return _WALK[kind]


def _exercise_vent(kind: str) -> float:
    if kind == "child":
        return CHILD_PLAY
    if kind == "older":
        return OLDER_WALK
    return ADULT_EXERCISE


def _mask(apply: bool) -> float:
    return MASK_FACTOR if apply else 1.0


def indoor_parts(household: Household, outdoor_pm: float, scenario: Scenario) -> dict[str, float]:
    factors = PURIFIER_FACTOR[scenario.purifier_mode]
    cook_extra = COOKING_EXTRA_UG[household.cooking]
    if scenario.cook_controlled:
        cook_extra *= COOK_CONTROL
    heat_extra = HEATING_EXTRA_UG[household.heating]
    if scenario.heat_controlled:
        heat_extra *= HEAT_CONTROL[household.heating]

    def base(period: str) -> float:
        return outdoor_pm * INFILTRATION_CLOSED * factors[period]

    return {
        "sleep": base("sleep"),
        "cook": base("cook") + cook_extra,
        "heat": base("heat") + heat_extra,
        "other": base("other"),
    }


def _trip_blocks(
    household: Household,
    air: AirNow,
    scenario: Scenario,
    mode: str,
    round_km: float,
) -> list[Block]:
    if mode in ("wfh", "none"):
        return []
    kind = commuter_kind(household)
    if kind is None:
        return []
    rest = _rest(kind)
    # Masks are for adults who can get a seal. Children and the model of an
    # older adult's commute are left unmasked; the copy says so.
    mask = scenario.mask and kind == "adult"
    # The commute clock usually cannot move to the cleaner hours, so trip
    # concentration stays on the current reading. Masks apply outdoors, where
    # a seal is the point, and not as a credit inside the vehicle.
    outdoor = air.pm2_5
    if mode in ("walk", "cycle"):
        vent = _walk(kind) if mode == "walk" else CYCLE_VENT
        hours = round_km / SPEED_KMH[mode]
        return [Block(hours, outdoor * _mask(mask), vent, rest)]
    ride_h = round_km * VEHICLE_MIN_PER_KM / 60.0
    access_h = ACCESS_MIN[mode] / 60.0
    blocks: list[Block] = []
    if access_h:
        blocks.append(Block(access_h, outdoor * _mask(mask), _walk(kind), rest))
    blocks.append(
        Block(ride_h, air.pm2_5 * IN_VEHICLE_PM_FACTOR[mode], rest, rest)
    )
    return blocks


def work_blocks(household: Household, air: AirNow, scenario: Scenario) -> list[Block]:
    return _trip_blocks(
        household, air, scenario, scenario.work_mode, DISTANCE_ROUND_KM[household.distance]
    )


def school_trip_blocks(household: Household, air: AirNow, scenario: Scenario) -> list[Block]:
    """A separate short trip only when the adult is otherwise at home.
    When the school run is part of a commute, it is a wait, not a second distance."""
    if not household.school_run or household.commute != "wfh":
        return []
    return _trip_blocks(household, air, scenario, scenario.school_mode, SCHOOL_ONLY_ROUND_KM)


def school_wait_block(household: Household, air: AirNow, scenario: Scenario) -> list[Block]:
    if not household.school_run or scenario.school_wait_min <= 0:
        return []
    kind = commuter_kind(household)
    if kind is None:
        return []
    hours = scenario.school_wait_min / 60.0
    rest = _rest(kind)
    mask = scenario.mask and kind == "adult"
    if scenario.idle_min > 0:
        conc = air.pm2_5 * IN_VEHICLE_PM_FACTOR["car"]
        return [Block(hours, conc, rest, rest)]
    return [Block(hours, air.pm2_5 * _mask(mask), rest, rest)]


def exercise_blocks(
    household: Household, air: AirNow, scenario: Scenario, other_conc: float
) -> list[Block]:
    kind = exercise_kind(household)
    if kind is None or scenario.exercise == "none":
        return []
    rest = _rest(kind)
    vent = _exercise_vent(kind)
    mask = scenario.mask and kind == "adult" and scenario.exercise != "indoor"
    if scenario.exercise == "indoor":
        conc = other_conc
    elif scenario.exercise == "outdoor_clean" and air.clean_pm2_5 is not None:
        conc = air.clean_pm2_5 * _mask(mask)
    else:
        conc = air.pm2_5 * _mask(mask)
    return [Block(EXERCISE_H, conc, vent, rest)]


def _all_blocks(
    household: Household, air: AirNow, scenario: Scenario, parts: dict[str, float]
) -> list[Block]:
    return (
        work_blocks(household, air, scenario)
        + school_trip_blocks(household, air, scenario)
        + school_wait_block(household, air, scenario)
        + exercise_blocks(household, air, scenario, parts["other"])
    )


def inhaled_ug(household: Household, air: AirNow, scenario: Scenario) -> float:
    parts = indoor_parts(household, air.pm2_5, scenario)
    blocks = _all_blocks(household, air, scenario, parts)
    heat_h = heat_hours(household)
    out_h = sum(block.hours for block in blocks)
    indoor_fixed = SLEEP_H + COOK_H + heat_h
    if out_h > 0 and indoor_fixed + out_h > 24.0:
        scale = (24.0 - indoor_fixed) / out_h
        blocks = [
            Block(block.hours * scale, block.conc, block.vent, block.absent_rest)
            for block in blocks
        ]
        out_h = sum(block.hours for block in blocks)
    other_h = max(0.0, 24.0 - indoor_fixed - out_h)
    home = household_rest(household)
    dose = (
        parts["sleep"] * home * SLEEP_H
        + parts["cook"] * home * COOK_H
        + parts["heat"] * home * heat_h
        + parts["other"] * home * other_h
    )
    for block in blocks:
        dose += parts["other"] * max(0.0, home - block.absent_rest) * block.hours
        dose += block.conc * block.vent * block.hours
    return max(0.0, dose)


def co2e_g(household: Household, scenario: Scenario) -> float:
    work = 0.0
    if scenario.work_mode != "wfh":
        work = CO2E_G_PER_PKM[scenario.work_mode] * DISTANCE_ROUND_KM[household.distance]
    school = 0.0
    if (
        household.school_run
        and household.commute == "wfh"
        and scenario.school_mode not in ("none", "wfh")
    ):
        school = CO2E_G_PER_PKM[scenario.school_mode] * SCHOOL_ONLY_ROUND_KM
    return work + school + scenario.idle_min * IDLE_G_PER_MIN


def emitted_pm_g(household: Household, scenario: Scenario) -> float:
    waste = WASTE_KG * WASTE_EF_G_PER_KG if scenario.burns else 0.0
    wood = 0.0
    if household.heating == "wood_coal":
        factor = HEAT_CONTROL["wood_coal"] if scenario.heat_controlled else 1.0
        wood = WOOD_KG * WOOD_EF_G_PER_KG * factor
    return waste + wood


def totals(household: Household, air: AirNow, scenario: Scenario) -> DayTotals:
    return DayTotals(
        inhaled_ug=inhaled_ug(household, air, scenario),
        co2e_g=co2e_g(household, scenario),
        emitted_pm_g=emitted_pm_g(household, scenario),
    )


def trip_inhaled_ug(household: Household, air: AirNow, scenario: Scenario) -> float:
    """Inhaled PM2.5 for the work trip only, used to refuse a swap that
    lengthens time in the plume."""
    dose = 0.0
    for block in work_blocks(household, air, scenario):
        dose += block.conc * block.vent * block.hours
    return dose


def child_play_ug(concentration: float, minutes: float = 20.0) -> float:
    return concentration * CHILD_PLAY * (minutes / 60.0)


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
    vent = _exercise_vent(kind)
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
    """Return the plan scenario and, when a lower-emission commute was refused,
    a short reason the caller can show."""
    severe = air.us_aqi >= 101
    mask = severe
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
