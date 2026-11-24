"""Card wording. Each card quotes the engine; none of them recalculates a factor."""

from __future__ import annotations

from dataclasses import dataclass, replace

from hearthline.aqi import aqi_from_pm25, category_for, hour_label
from hearthline.impact import (
    CO2E_G_PER_PKM,
    DISTANCE_ROUND_KM,
    MODE_LABEL,
    WASTE_EF_G_PER_KG,
    WASTE_KG,
    WOOD_KG,
    child_play_ug,
    indoor_parts,
    outdoor_limit,
    totals,
)
from hearthline.models import AirNow, DayTotals, Household, Scenario
from hearthline.present import co2e, co2e_sentence, emitted_sentence, grams, inhaled_sentence, ug


@dataclass(frozen=True)
class _Compare:
    household: Household
    air: AirNow
    base: Scenario
    plan: Scenario


_COOK = {
    "biomass": (
        "Get children out of the biomass kitchen",
        [
            "Children leave the kitchen while fuel is lit.",
            "Lid on, shortest cook you can manage, and air that room only in the cleaner hours.",
        ],
    ),
    "gas": (
        "Calm the gas flame and the pan",
        [
            "Lid on, back burner, hood running. The flame adds combustion pollution and the pan adds particles.",
            "The hood should vent outside. A recirculating hood mostly stirs the same air.",
        ],
    ),
    "mixed": (
        "Use the cleaner stove for today's hot meal",
        [
            "Cook today's meal on the induction or gas burner, not the solid fuel.",
            "Lid on, and keep children out of the room while anything is frying.",
        ],
    ),
    "induction": (
        "Keep the pan from smoking",
        [
            "There is no flame, but a smoking pan still fills the room.",
            "Lid on, hood on, and turn the heat down before the oil burns.",
        ],
    ),
}

_BEDROOM = {
    "hepa": (
        "Run the cleaner in the bedroom",
        [
            "Door closed, cleaner on, for the hours people sleep.",
            "A cleaner in the bedroom does less for the kitchen plume. The cooking card covers that.",
            "Stop using a machine that smells of ozone. Ozone is not a particle cleaner.",
        ],
    ),
    "diy": (
        "Give the bedroom a simple particle cleaner",
        [
            "A box fan taped to a fine-particle furnace filter, blowing into the room where people sleep.",
            "Keep it off soft bedding and away from curtains. Replace the filter when it turns grey.",
            "This is the smaller effect in the figure. A sealed HEPA unit does more, and the plan says so when you already own one.",
        ],
    ),
    "off": (
        "No new cleaner today",
        [
            "Outdoor air and indoor sources do not justify a new machine for this day.",
            "Use the hood while cooking. That is the higher-leverage indoor step.",
        ],
    ),
}


def _lines(before: DayTotals, after: DayTotals) -> list[str]:
    lines: list[str] = []
    for sentence in (
        inhaled_sentence(before.inhaled_ug, after.inhaled_ug),
        co2e_sentence(before.co2e_g, after.co2e_g),
        emitted_sentence(before.emitted_pm_g, after.emitted_pm_g),
    ):
        if sentence:
            lines.append(sentence)
    return lines


def _card(card_id: str, category: str, title: str, steps: list[str], impacts: list[str]) -> dict:
    return {
        "id": card_id,
        "category": category,
        "title": title,
        "steps": steps,
        "impacts": impacts,
        "note": "",
    }


def _window_phrase(air: AirNow) -> str | None:
    if air.clean_start is None or air.clean_end is None or air.clean_pm2_5 is None:
        return None
    return (
        f"the three hours starting at {hour_label(air.clean_start)} "
        f"(about {ug(air.clean_pm2_5)} PM2.5)"
    )


def _marginal(days: _Compare, field: str, baseline_value: object) -> list[str]:
    if getattr(days.plan, field) == baseline_value:
        return []
    without = replace(days.plan, **{field: baseline_value})
    before = totals(days.household, days.air, without)
    after = totals(days.household, days.air, days.plan)
    return _lines(before, after)


def _keep_outdoor(days: _Compare) -> dict:
    air = days.air
    return _card(
        "exercise",
        "routine",
        "Keep today's outdoor play",
        [
            f"Air is in the {air.category} range, under the line this household uses for moving play inside.",
            "Keep it moderate. The benefit of moving outweighs a small particle difference on a day like this.",
        ],
        ["No change from the unchanged day. The choice is to keep the outdoor time."],
    )


def _cleaner_play(days: _Compare) -> dict | None:
    air = days.air
    window = _window_phrase(air)
    if window is None or air.clean_pm2_5 is None:
        return _indoor_play(days)
    who = "the child" if days.household.children else "the adult"
    still = category_for(aqi_from_pm25(air.clean_pm2_5))
    impacts = _marginal(days, "exercise", days.base.exercise)
    if not impacts:
        return None
    return _card(
        "exercise",
        "routine",
        f"Move {who}'s play to the cleaner hours",
        [
            f"The cleaner stretch is {window}. It is still {still}.",
            "Keep the session to the planned length. If that stretch is impossible, stay in the filtered room rather than going out now.",
            "Do not add a mask credit for a small child. Infants stay in.",
        ],
        impacts,
    )


def _indoor_play(days: _Compare) -> dict | None:
    who = "the child" if days.household.children else "the adult"
    impacts = _marginal(days, "exercise", days.base.exercise)
    if not impacts:
        return None
    return _card(
        "exercise",
        "routine",
        f"Bring {who}'s play indoors",
        [
            "Indoor air, after the cooking and cleaner steps, is the lower dose for this session.",
            "Harder breathing still pulls in more air, so keep the room closed and the cleaner running while they play.",
        ],
        impacts,
    )


def _exercise_card(days: _Compare) -> dict | None:
    if not days.household.outdoor_exercise:
        return None
    if days.plan.exercise == "outdoor_now":
        return _keep_outdoor(days)
    if days.plan.exercise == "outdoor_clean" and _window_phrase(days.air):
        return _cleaner_play(days)
    return _indoor_play(days)


def _home_work(days: _Compare) -> dict:
    steps = ["No work trip today, so that share of climate pollution stays off the road."]
    if days.household.school_run:
        steps.append("The school trip is counted on its own card, not as a second full commute.")
    return _card(
        "commute",
        "alternative",
        "The work day stays home",
        steps,
        ["Working from home avoids the work-trip emissions of a day that starts with a drive."],
    )


def _already_lower(days: _Compare) -> dict:
    household = days.household
    km = DISTANCE_ROUND_KM[household.distance]
    saved = (CO2E_G_PER_PKM["car"] - CO2E_G_PER_PKM[household.commute]) * km
    return _card(
        "commute",
        "alternative",
        f"Stay with {MODE_LABEL[household.commute]}",
        [
            "This trip is already a lower-emission choice than driving the same distance alone.",
            "The figure is the difference against a car, and it is not counted again in today's reduction.",
        ],
        [f"Compared with a car on the same {km:.0f} km round trip, this avoids about {co2e(saved)}."],
    )


def _kept_car(days: _Compare, refusal: str | None) -> dict:
    return _card(
        "commute",
        "alternative",
        "Keep the car, and change how it is used",
        [
            refusal or "Transit is not available for this trip, so the car stays and the idle does not.",
            "Set the cabin to recirculate while you are in traffic. Open it only once you are out of the plume.",
        ],
        [
            "The climate figure for this trip does not fall, because the distance is unchanged. Idling is on the school-run card when that trip exists."
        ],
    )


def _swapped_trip(days: _Compare) -> dict:
    impacts = _marginal(days, "work_mode", days.base.work_mode)
    if not impacts:
        impacts = ["The swap changes the day by less than the smallest change this plan reports."]
    return _card(
        "commute",
        "alternative",
        f"Move the work trip from {MODE_LABEL[days.base.work_mode]} to {MODE_LABEL[days.plan.work_mode]}",
        [
            "One commuter, round trip, at the distance you chose.",
            "Wear a mask for the walk to the stop when the index is unhealthy. The ride itself is not given a mask credit in the figure.",
            "If the stop is a long walk in very dirty air, the plan keeps the car instead. That guard is already applied.",
        ],
        impacts,
    )


def _commute_card(days: _Compare, refusal: str | None) -> dict:
    household = days.household
    if household.commute == "wfh" and days.plan.school_mode == days.base.school_mode:
        return _home_work(days)
    if days.plan.work_mode == days.base.work_mode and household.commute != "car":
        return _already_lower(days)
    if days.plan.work_mode == "car" and household.commute == "car":
        return _kept_car(days, refusal)
    return _swapped_trip(days)


def _school_card(days: _Compare) -> dict | None:
    household = days.household
    if not household.school_run:
        return None
    steps = [
        "Arrive, engine off, and keep the handover to a minute or two when the air is poor.",
        "Do not idle the line. The climate figure is the fuel, and the particle figure is the wait in the plume.",
    ]
    if household.commute == "wfh" and days.plan.school_mode != days.base.school_mode:
        steps.insert(0, f"The separate school trip moves from a car to {MODE_LABEL[days.plan.school_mode]}.")
    # Wait and idle move together in the recommendation. Show them as one choice.
    without = replace(
        days.plan,
        school_wait_min=days.base.school_wait_min,
        idle_min=days.base.idle_min,
        school_mode=days.base.school_mode,
    )
    impacts = _lines(totals(household, days.air, without), totals(household, days.air, days.plan))
    if not impacts:
        return None
    return _card("school-run", "routine", "Cut the idle at pickup", steps, impacts)


def _cook_card(days: _Compare) -> dict:
    title, steps = _COOK[days.household.cooking]
    impacts = _marginal(days, "cook_controlled", False)
    if not impacts:
        impacts = ["Cooking is a small share of today's dose next to the outdoor air."]
    return _card("cook", "indoor", title, steps, impacts)


def _wood_heat() -> tuple[str, list[str]]:
    return (
        "Heat one room and burn half the wood",
        [
            f"The figure assumes one evening of about {WOOD_KG:.0f} kg of wood, and a cleaner evening that uses half of that.",
            "Dry wood, a hot fire, and no trash in the stove. It is still smoke.",
            "A shared warm room in the building beats a second fire if you have one.",
        ],
    )


def _gas_heat() -> tuple[str, list[str]]:
    return (
        "Shorten the unvented gas heat",
        [
            "If the heater vents outside and burns cleanly, this card is the cautious case, not a measurement of your flue.",
            "Prefer a short burst over a long low burn, and do not crack a window at the dirty peak.",
        ],
    )


def _heat_card(days: _Compare) -> dict | None:
    if days.household.heating not in ("gas", "wood_coal"):
        return None
    title, steps = _wood_heat() if days.household.heating == "wood_coal" else _gas_heat()
    impacts = _marginal(days, "heat_controlled", False)
    if not impacts:
        return None
    return _card("heat", "indoor", title, steps, impacts)


def _bedroom_card(days: _Compare) -> dict:
    title, steps = _BEDROOM[days.plan.purifier_mode]
    if days.plan.purifier_mode == "off":
        return _card(
            "bedroom",
            "indoor",
            title,
            steps,
            ["The cleaner stays off in both the unchanged day and this plan."],
        )
    impacts = _marginal(days, "purifier_mode", "off")
    if not impacts:
        impacts = ["Running the cleaner changes today's dose by less than the smallest change this plan reports."]
    return _card("bedroom", "indoor", title, steps, impacts)


def _open_then_close(days: _Compare, window: str) -> dict:
    air = days.air
    return _card(
        "ventilate",
        "indoor",
        "Air the home in the cleaner stretch, then close it",
        [
            f"Open up around {window}, for about ten minutes, then close the windows.",
            f"Opening at the current peak would aim the room toward {ug(air.pm2_5)}. The cleaner stretch is lower than the indoor level the plan is already holding.",
        ],
        [
            f"This card is the avoided mistake, not a change in the 24-hour total. Peak outdoor air is about {ug(air.pm2_5)}; the cleaner stretch averages about {ug(air.clean_pm2_5)}."
        ],
    )


def _closed_despite_window(days: _Compare, window: str, indoor: float) -> dict:
    return _card(
        "ventilate",
        "indoor",
        "Keep the windows closed today",
        [
            f"The cleaner stretch ({window}) is still not cleaner than the indoor air you can hold with windows shut.",
            "Airing out now would aim the room toward the outdoor reading.",
        ],
        [f"Holding the closed room keeps the target near about {ug(indoor)} instead of about {ug(days.air.pm2_5)} outside."],
    )


def _no_cleaner_hour(days: _Compare, indoor: float) -> dict:
    return _card(
        "ventilate",
        "indoor",
        "Keep the windows closed while the index is high",
        [
            "No hourly window came back cleaner than now.",
            "Stay closed. Airing out would aim indoor air toward the outdoor reading.",
        ],
        [f"Outdoor air is about {ug(days.air.pm2_5)}. Indoor air with the windows shut is estimated near {ug(indoor)}."],
    )


def _airing_ok(days: _Compare) -> dict:
    return _card(
        "ventilate",
        "indoor",
        "Airing out is reasonable",
        [
            "Outdoor air is in a range where a short airing is reasonable.",
            "Skip it if someone is frying or a fuel is lit.",
        ],
        [f"Outdoor PM2.5 is about {ug(days.air.pm2_5)}."],
    )


def _ventilate_card(days: _Compare) -> dict:
    window = _window_phrase(days.air)
    indoor = indoor_parts(days.household, days.air.pm2_5, days.plan)["other"]
    clean = days.air.clean_pm2_5
    if window and clean is not None and clean < indoor:
        return _open_then_close(days, window)
    if window:
        return _closed_despite_window(days, window, indoor)
    if days.air.us_aqi >= 101:
        return _no_cleaner_hour(days, indoor)
    return _airing_ok(days)


def _household_burn(days: _Compare, bag: float) -> dict:
    impacts = _marginal(days, "burns", True) or [f"About {grams(bag)} of PM2.5 stays out of the lane."]
    return _card(
        "burn",
        "alternative",
        "Do not burn the bag",
        [
            "Put it out for collection, or store it until collection day.",
            f"The figure is one typical bag of about {WASTE_KG:.0f} kg. A larger pile is more. A smaller one is less.",
        ],
        impacts,
    )


def _block_burn(bag: float) -> dict:
    return _card(
        "burn",
        "alternative",
        "Ask the block to skip burning today",
        [
            "One household's bag is enough to spike the lane even when the city index is already high.",
            "The figure is per bag not burned. It is not added to your household total unless you were going to burn one.",
        ],
        [f"One bag not burned avoids about {grams(bag)} of PM2.5 in the air people nearby breathe."],
    )


def _burn_card(days: _Compare) -> dict | None:
    bag = WASTE_KG * WASTE_EF_G_PER_KG
    if days.household.burns_waste:
        return _household_burn(days, bag)
    if days.household.audience == "block":
        return _block_burn(bag)
    return None


def _mask_card(days: _Compare) -> dict | None:
    if not days.plan.mask:
        return None
    impacts = _marginal(days, "mask", False) or [
        "With play moved and the wait shortened, little masked time remains. Wear one anyway if you step out for more than a few minutes."
    ]
    return _card(
        "mask",
        "routine",
        "Mask the minutes you still spend outside",
        [
            "A well-fitted FFP2 or N95, pinched at the nose, for adults who still step outside.",
            "Do not mask an infant. Keep infants indoors.",
            "The figure credits the mask on outdoor minutes only, and only for an adult commuter or an adult at play. A child's play is reduced by moving it, not by a mask.",
        ],
        impacts,
    )


def _recess_card(days: _Compare) -> dict | None:
    household = days.household
    air = days.air
    if household.audience not in ("school", "block"):
        return None
    if air.us_aqi < outdoor_limit(household):
        return None
    parts = indoor_parts(household, air.pm2_5, days.plan)
    outside = child_play_ug(air.pm2_5, 20)
    inside = child_play_ug(parts["other"], 20)
    return _card(
        "recess",
        "routine",
        "Move recess and sports indoors",
        [
            "Use the same line the household plan uses: sensitive groups, including children, ease off strenuous outdoor time from the Unhealthy-for-Sensitive-Groups range up.",
            "Tell families the reason in one sentence, with the index and the clock.",
        ],
        [
            f"Per child, twenty minutes outdoors is about {ug(outside)} inhaled, against about {ug(inside)} in the planned indoor air. This is not added again to the household total."
        ],
    )


def plan_cards(
    household: Household,
    air: AirNow,
    base: Scenario,
    plan: Scenario,
    refusal: str | None,
) -> list[dict]:
    days = _Compare(household, air, base, plan)
    cards = [
        _exercise_card(days),
        _school_card(days),
        _commute_card(days, refusal),
        _cook_card(days),
        _heat_card(days),
        _bedroom_card(days),
        _ventilate_card(days),
        _burn_card(days),
        _mask_card(days),
        _recess_card(days),
    ]
    return [card for card in cards if card is not None]
