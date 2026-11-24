"""Assemble the day plan. Wording lives in cards.py; the choice of day lives in recommend.py."""

from __future__ import annotations

from hearthline.aqi import WHO_PM25_24H, hour_label
from hearthline.cards import plan_cards
from hearthline.impact import totals
from hearthline.models import AirNow, DayTotals, Household
from hearthline.present import co2e, grams, headline, ug
from hearthline.recommend import baseline_scenario, recommended_scenario

LIMITS = (
    "These are planning estimates for one day, not a personal dose and not a medical prognosis.",
    "The air reading is a model field, not an official government AQI.",
    "A well-fitted mask is a backup for minutes you still spend outside. It is not for infants.",
    "The language model may phrase the day. It is not allowed to change the figures.",
)


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
        "actions": plan_cards(household, air, base, plan, refusal),
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
