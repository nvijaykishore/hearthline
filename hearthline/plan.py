"""Assemble the day plan from the engine. Copy lives here; factors do not."""

from __future__ import annotations

from dataclasses import replace

from hearthline.aqi import WHO_PM25_24H, aqi_from_pm25, category_for, hour_label
from hearthline.impact import (
    CO2E_G_PER_PKM,
    DISTANCE_ROUND_KM,
    MODE_LABEL,
    WASTE_EF_G_PER_KG,
    WASTE_KG,
    WOOD_KG,
    baseline_scenario,
    child_play_ug,
    indoor_parts,
    outdoor_limit,
    recommended_scenario,
    totals,
)
from hearthline.models import AirNow, DayTotals, Household, Scenario
from hearthline.present import co2e, co2e_sentence, emitted_sentence, grams, headline, inhaled_sentence, ug

LIMITS = (
    "These are planning estimates for one day, not a personal dose and not a medical prognosis.",
    "The air reading is a model field, not an official government AQI.",
    "A well-fitted mask is a backup for minutes you still spend outside. It is not for infants.",
    "The language model may phrase the day. It is not allowed to change the figures.",
)


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


def _exercise_card(household: Household, air: AirNow, base: Scenario, plan: Scenario) -> dict | None:
    if not household.outdoor_exercise:
        return None
    who = "the child" if household.children else "the adult"
    window = _window_phrase(air)
    if plan.exercise == "outdoor_now":
        title = "Keep today's outdoor play"
        steps = [
            f"Air is in the {air.category} range, under the line this household uses for moving play inside.",
            "Keep it moderate. The benefit of moving outweighs a small particle difference on a day like this.",
        ]
        impacts = ["No change from the unchanged day. The choice is to keep the outdoor time."]
    elif plan.exercise == "outdoor_clean" and window:
        still = category_for(aqi_from_pm25(air.clean_pm2_5))
        title = f"Move {who}'s play to the cleaner hours"
        steps = [
            f"The cleaner stretch is {window}. It is still {still}.",
            "Keep the session to the planned length. If that stretch is impossible, stay in the filtered room rather than going out now.",
            "Do not add a mask credit for a small child. Infants stay in.",
        ]
        impacts = _marginal(household, air, base, plan, "exercise", base.exercise)
    else:
        title = f"Bring {who}'s play indoors"
        steps = [
            "Indoor air, after the cooking and cleaner steps, is the lower dose for this session.",
            "Harder breathing still pulls in more air, so keep the room closed and the cleaner running while they play.",
        ]
        impacts = _marginal(household, air, base, plan, "exercise", base.exercise)
    if not impacts:
        return None
    return _card("exercise", "routine", title, steps, impacts)


def _marginal(
    household: Household,
    air: AirNow,
    base: Scenario,
    plan: Scenario,
    field: str,
    baseline_value: object,
) -> list[str]:
    if getattr(plan, field) == baseline_value:
        return []
    without = replace(plan, **{field: baseline_value})
    before = totals(household, air, without)
    after = totals(household, air, plan)
    return _lines(before, after)


def _commute_card(
    household: Household, air: AirNow, base: Scenario, plan: Scenario, refusal: str | None
) -> dict:
    km = DISTANCE_ROUND_KM[household.distance]
    if household.commute == "wfh" and plan.school_mode == base.school_mode:
        title = "The work day stays home"
        steps = [
            "No work trip today, so that share of climate pollution stays off the road.",
        ]
        impacts = ["Working from home avoids the work-trip emissions of a day that starts with a drive."]
        if household.school_run:
            steps.append("The school trip is counted on its own card, not as a second full commute.")
        return _card("commute", "alternative", title, steps, impacts)

    if plan.work_mode == base.work_mode and household.commute != "car":
        car = CO2E_G_PER_PKM["car"] * km
        yours = CO2E_G_PER_PKM[household.commute] * km
        saved = car - yours
        title = f"Stay with {MODE_LABEL[household.commute]}"
        steps = [
            "This trip is already a lower-emission choice than driving the same distance alone.",
            "The figure is the difference against a car, and it is not counted again in today's reduction.",
        ]
        impacts = [
            f"Compared with a car on the same {km:.0f} km round trip, this avoids about {co2e(saved)}."
        ]
        return _card("commute", "alternative", title, steps, impacts)

    if plan.work_mode == "car" and household.commute == "car":
        title = "Keep the car, and change how it is used"
        steps = [
            refusal
            or "Transit is not available for this trip, so the car stays and the idle does not.",
            "Set the cabin to recirculate while you are in traffic. Open it only once you are out of the plume.",
        ]
        impacts = [
            "The climate figure for this trip does not fall, because the distance is unchanged. Idling is on the school-run card when that trip exists."
        ]
        return _card("commute", "alternative", title, steps, impacts)

    title = f"Move the work trip from {MODE_LABEL[base.work_mode]} to {MODE_LABEL[plan.work_mode]}"
    steps = [
        "One commuter, round trip, at the distance you chose.",
        "Wear a mask for the walk to the stop when the index is unhealthy. The ride itself is not given a mask credit in the figure.",
        "If the stop is a long walk in very dirty air, the plan keeps the car instead. That guard is already applied.",
    ]
    impacts = _marginal(household, air, base, plan, "work_mode", base.work_mode)
    if not impacts:
        impacts = ["The swap changes the day by less than the smallest change this plan reports."]
    return _card("commute", "alternative", title, steps, impacts)


def _school_card(household: Household, air: AirNow, base: Scenario, plan: Scenario) -> dict | None:
    if not household.school_run:
        return None
    steps = [
        "Arrive, engine off, and keep the handover to a minute or two when the air is poor.",
        "Do not idle the line. The climate figure is the fuel, and the particle figure is the wait in the plume.",
    ]
    if household.commute == "wfh" and plan.school_mode != base.school_mode:
        steps.insert(0, f"The separate school trip moves from a car to {MODE_LABEL[plan.school_mode]}.")
    impacts = []
    # Wait and idle move together in the recommendation. Show them as one choice.
    without = replace(
        plan,
        school_wait_min=base.school_wait_min,
        idle_min=base.idle_min,
        school_mode=base.school_mode,
    )
    impacts = _lines(totals(household, air, without), totals(household, air, plan))
    if not impacts:
        return None
    return _card("school-run", "routine", "Cut the idle at pickup", steps, impacts)


def _cook_card(household: Household, air: AirNow, base: Scenario, plan: Scenario) -> dict:
    titles = {
        "biomass": "Get children out of the biomass kitchen",
        "gas": "Calm the gas flame and the pan",
        "mixed": "Use the cleaner stove for today's hot meal",
        "induction": "Keep the pan from smoking",
    }
    steps = {
        "biomass": [
            "Children leave the kitchen while fuel is lit.",
            "Lid on, shortest cook you can manage, and air that room only in the cleaner hours.",
        ],
        "gas": [
            "Lid on, back burner, hood running. The flame adds combustion pollution and the pan adds particles.",
            "The hood should vent outside. A recirculating hood mostly stirs the same air.",
        ],
        "mixed": [
            "Cook today's meal on the induction or gas burner, not the solid fuel.",
            "Lid on, and keep children out of the room while anything is frying.",
        ],
        "induction": [
            "There is no flame, but a smoking pan still fills the room.",
            "Lid on, hood on, and turn the heat down before the oil burns.",
        ],
    }
    impacts = _marginal(household, air, base, plan, "cook_controlled", False)
    if not impacts:
        impacts = ["Cooking is a small share of today's dose next to the outdoor air."]
    return _card("cook", "indoor", titles[household.cooking], steps[household.cooking], impacts)


def _heat_card(household: Household, air: AirNow, base: Scenario, plan: Scenario) -> dict | None:
    if household.heating not in ("gas", "wood_coal"):
        return None
    if household.heating == "wood_coal":
        title = "Heat one room and burn half the wood"
        steps = [
            f"The figure assumes one evening of about {WOOD_KG:.0f} kg of wood, and a cleaner evening that uses half of that.",
            "Dry wood, a hot fire, and no trash in the stove. It is still smoke.",
            "A shared warm room in the building beats a second fire if you have one.",
        ]
    else:
        title = "Shorten the unvented gas heat"
        steps = [
            "If the heater vents outside and burns cleanly, this card is the cautious case, not a measurement of your flue.",
            "Prefer a short burst over a long low burn, and do not crack a window at the dirty peak.",
        ]
    impacts = _marginal(household, air, base, plan, "heat_controlled", False)
    if not impacts:
        return None
    return _card("heat", "indoor", title, steps, impacts)


def _bedroom_card(household: Household, air: AirNow, base: Scenario, plan: Scenario) -> dict:
    if plan.purifier_mode == "hepa":
        title = "Run the cleaner in the bedroom"
        steps = [
            "Door closed, cleaner on, for the hours people sleep.",
            "A cleaner in the bedroom does less for the kitchen plume. The cooking card covers that.",
            "Stop using a machine that smells of ozone. Ozone is not a particle cleaner.",
        ]
    elif plan.purifier_mode == "diy":
        title = "Give the bedroom a simple particle cleaner"
        steps = [
            "A box fan taped to a fine-particle furnace filter, blowing into the room where people sleep.",
            "Keep it off soft bedding and away from curtains. Replace the filter when it turns grey.",
            "This is the smaller effect in the figure. A sealed HEPA unit does more, and the plan says so when you already own one.",
        ]
    else:
        title = "No new cleaner today"
        steps = [
            "Outdoor air and indoor sources do not justify a new machine for this day.",
            "Use the hood while cooking. That is the higher-leverage indoor step.",
        ]
        return _card(
            "bedroom",
            "indoor",
            title,
            steps,
            ["The cleaner stays off in both the unchanged day and this plan."],
        )
    impacts = _marginal(household, air, base, plan, "purifier_mode", "off")
    if not impacts:
        impacts = ["Running the cleaner changes today's dose by less than the smallest change this plan reports."]
    return _card("bedroom", "indoor", title, steps, impacts)


def _ventilate_card(household: Household, air: AirNow, plan: Scenario) -> dict:
    window = _window_phrase(air)
    parts = indoor_parts(household, air.pm2_5, plan)
    indoor = parts["other"]
    if window and air.clean_pm2_5 is not None and air.clean_pm2_5 < indoor:
        title = "Air the home in the cleaner stretch, then close it"
        steps = [
            f"Open up around {window}, for about ten minutes, then close the windows.",
            f"Opening at the current peak would aim the room toward {ug(air.pm2_5)}. The cleaner stretch is lower than the indoor level the plan is already holding.",
        ]
        impacts = [
            f"This card is the avoided mistake, not a change in the 24-hour total. Peak outdoor air is about {ug(air.pm2_5)}; the cleaner stretch averages about {ug(air.clean_pm2_5)}."
        ]
    elif window:
        title = "Keep the windows closed today"
        steps = [
            f"The cleaner stretch ({window}) is still not cleaner than the indoor air you can hold with windows shut.",
            "Airing out now would aim the room toward the outdoor reading.",
        ]
        impacts = [
            f"Holding the closed room keeps the target near about {ug(indoor)} instead of about {ug(air.pm2_5)} outside."
        ]
    else:
        title = "Keep the windows closed while the index is high" if air.us_aqi >= 101 else "Airing out is reasonable"
        if air.us_aqi >= 101:
            steps = [
                "No hourly window came back cleaner than now.",
                "Stay closed. Airing out would aim indoor air toward the outdoor reading.",
            ]
            impacts = [f"Outdoor air is about {ug(air.pm2_5)}. Indoor air with the windows shut is estimated near {ug(indoor)}."]
        else:
            steps = ["Outdoor air is in a range where a short airing is reasonable.", "Skip it if someone is frying or a fuel is lit."]
            impacts = [f"Outdoor PM2.5 is about {ug(air.pm2_5)}."]
    return _card("ventilate", "indoor", title, steps, impacts)


def _burn_card(household: Household, air: AirNow, base: Scenario, plan: Scenario) -> dict | None:
    bag = WASTE_KG * WASTE_EF_G_PER_KG
    if household.burns_waste:
        impacts = _marginal(household, air, base, plan, "burns", True)
        title = "Do not burn the bag"
        steps = [
            "Put it out for collection, or store it until collection day.",
            f"The figure is one typical bag of about {WASTE_KG:.0f} kg. A larger pile is more. A smaller one is less.",
        ]
        return _card("burn", "alternative", title, steps, impacts or [f"About {grams(bag)} of PM2.5 stays out of the lane."])
    if household.audience == "block":
        title = "Ask the block to skip burning today"
        steps = [
            "One household's bag is enough to spike the lane even when the city index is already high.",
            "The figure is per bag not burned. It is not added to your household total unless you were going to burn one.",
        ]
        impacts = [f"One bag not burned avoids about {grams(bag)} of PM2.5 in the air people nearby breathe."]
        return _card("burn", "alternative", title, steps, impacts)
    return None


def _mask_card(household: Household, air: AirNow, base: Scenario, plan: Scenario) -> dict | None:
    if not plan.mask:
        return None
    impacts = _marginal(household, air, base, plan, "mask", False)
    steps = [
        "A well-fitted FFP2 or N95, pinched at the nose, for adults who still step outside.",
        "Do not mask an infant. Keep infants indoors.",
        "The figure credits the mask on outdoor minutes only, and only for an adult commuter or an adult at play. A child's play is reduced by moving it, not by a mask.",
    ]
    if not impacts:
        impacts = [
            "With play moved and the wait shortened, little masked time remains. Wear one anyway if you step out for more than a few minutes."
        ]
    return _card("mask", "routine", "Mask the minutes you still spend outside", steps, impacts)


def _recess_card(household: Household, air: AirNow, plan: Scenario) -> dict | None:
    if household.audience not in ("school", "block"):
        return None
    if air.us_aqi < outdoor_limit(household):
        return None
    parts = indoor_parts(household, air.pm2_5, plan)
    outside = child_play_ug(air.pm2_5, 20)
    inside = child_play_ug(parts["other"], 20)
    title = "Move recess and sports indoors"
    steps = [
        "Use the same line the household plan uses: sensitive groups, including children, ease off strenuous outdoor time from the Unhealthy-for-Sensitive-Groups range up.",
        "Tell families the reason in one sentence, with the index and the clock.",
    ]
    impacts = [
        f"Per child, twenty minutes outdoors is about {ug(outside)} inhaled, against about {ug(inside)} in the planned indoor air. This is not added again to the household total."
    ]
    return _card("recess", "routine", title, steps, impacts)


def _who(household: Household) -> str:
    bits: list[str] = []
    if household.adults:
        bits.append(f"{household.adults} adult" + ("s" if household.adults != 1 else ""))
    if household.children:
        bits.append(f"{household.children} child" + ("ren" if household.children != 1 else ""))
    if household.older_adults:
        bits.append(
            f"{household.older_adults} older adult" + ("s" if household.older_adults != 1 else "")
        )
    line = ", ".join(bits)
    if household.sensitive or household.children or household.older_adults:
        line += ". The plan uses the more cautious outdoor line."
    else:
        line += "."
    return line


def _audience_line(household: Household) -> str:
    if household.audience == "school":
        return "Written so a school can reuse the same day, not only one kitchen."
    if household.audience == "block":
        return "Written so a block can share the same day, not only one kitchen."
    return "Written for one household."


def _air_view(air: AirNow) -> dict:
    driver = "PM2.5 is the pollutant the dose uses."
    if abs(air.us_aqi - air.pm_aqi) > 25:
        driver = "The index includes more than PM2.5. The dose still uses the PM2.5 concentration."
    guideline = ""
    if air.pm2_5 >= WHO_PM25_24H:
        guideline = f"Above the WHO 24-hour PM2.5 guideline of {WHO_PM25_24H:.0f} µg/m³."
    return {
        "pm2_5": round(air.pm2_5, 1),
        "us_aqi": air.us_aqi,
        "category": air.category,
        "pm_aqi": air.pm_aqi,
        "observed_at": air.observed_at,
        "clean_pm2_5": None if air.clean_pm2_5 is None else round(air.clean_pm2_5, 1),
        "clean_start": None if air.clean_start is None else hour_label(air.clean_start),
        "clean_end": None if air.clean_end is None else hour_label(air.clean_end),
        "source": air.source,
        "note": air.note,
        "driver": driver,
        "guideline": guideline,
    }


def _combined(before: DayTotals, after: DayTotals) -> dict:
    return {
        "inhaled_ug_baseline": round(before.inhaled_ug, 1),
        "inhaled_ug_plan": round(after.inhaled_ug, 1),
        "co2e_g_baseline": round(before.co2e_g, 1),
        "co2e_g_plan": round(after.co2e_g, 1),
        "emitted_pm_g_baseline": round(before.emitted_pm_g, 1),
        "emitted_pm_g_plan": round(after.emitted_pm_g, 1),
        "inhaled_baseline": ug(before.inhaled_ug),
        "inhaled_plan": ug(after.inhaled_ug),
        "co2e_baseline": co2e(before.co2e_g),
        "co2e_plan": co2e(after.co2e_g),
        "emitted_baseline": grams(before.emitted_pm_g),
        "emitted_plan": grams(after.emitted_pm_g),
    }


def _actions(household: Household, air: AirNow, base: Scenario, plan: Scenario, refusal: str | None) -> list[dict]:
    cards = [
        _exercise_card(household, air, base, plan),
        _school_card(household, air, base, plan),
        _commute_card(household, air, base, plan, refusal),
        _cook_card(household, air, base, plan),
        _heat_card(household, air, base, plan),
        _bedroom_card(household, air, base, plan),
        _ventilate_card(household, air, plan),
        _burn_card(household, air, base, plan),
        _mask_card(household, air, base, plan),
        _recess_card(household, air, plan),
    ]
    return [card for card in cards if card is not None]


def build_plan(household: Household, air: AirNow) -> dict:
    base = baseline_scenario(household)
    plan, refusal = recommended_scenario(household, air)
    before = totals(household, air, base)
    after = totals(household, air, plan)
    return {
        "place": {
            "label": air.place_label or household.city,
            "latitude": household.latitude,
            "longitude": household.longitude,
        },
        "air": _air_view(air),
        "household_line": _who(household),
        "audience_line": _audience_line(household),
        "summary": headline(before, after),
        "tone": "",
        "narrative_source": "local",
        "combined": _combined(before, after),
        "actions": _actions(household, air, base, plan, refusal),
        "limits": list(LIMITS),
        "choices": {
            "commute": plan.work_mode,
            "exercise": plan.exercise,
            "purifier": plan.purifier_mode,
            "mask": plan.mask,
            "burns": plan.burns,
        },
    }


def apply_tone(plan: dict, tone: dict | None) -> dict:
    """Attach model phrasing that has already passed the safety check."""
    if not tone:
        return plan
    updated = dict(plan)
    text = tone.get("tone") or ""
    if text:
        updated["tone"] = text
        updated["narrative_source"] = "model"
    notes = tone.get("notes") or {}
    actions: list[dict] = []
    for action in plan["actions"]:
        note = notes.get(action["id"]) or ""
        if note:
            cloned = dict(action)
            cloned["note"] = note
            actions.append(cloned)
            updated["narrative_source"] = "model"
        else:
            actions.append(action)
    updated["actions"] = actions
    return updated
