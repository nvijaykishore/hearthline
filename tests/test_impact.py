import unittest
from dataclasses import replace

from hearthline.aqi import aqi_from_pm25, category_for
from hearthline.impact import (
    CO2E_G_PER_PKM,
    DISTANCE_ROUND_KM,
    IDLE_G_PER_MIN,
    WASTE_EF_G_PER_KG,
    WASTE_KG,
    WOOD_EF_G_PER_KG,
    WOOD_KG,
    co2e_g,
    emitted_pm_g,
    outdoor_limit,
    totals,
)
from hearthline.recommend import baseline_scenario, recommended_scenario
from hearthline.models import AirNow
from hearthline.sample import sample_air, sample_household


def air_at(pm, aqi=None):
    index = aqi_from_pm25(pm) if aqi is None else aqi
    return AirNow(
        pm2_5=pm,
        us_aqi=index,
        category=category_for(index),
        pm_aqi=aqi_from_pm25(pm),
        observed_at="2026-01-15T08:00",
        clean_pm2_5=None,
        clean_start=None,
        clean_end=None,
        source="test",
        place_label="Test",
        note="test",
    )


def household(**overrides):
    base = dict(
        city="Test",
        latitude=1.0,
        longitude=2.0,
        adults=2,
        children=0,
        older_adults=0,
        sensitive=False,
        heating="none",
        cooking="induction",
        purifier=False,
        commute="wfh",
        distance="2_to_8",
        transit_available=False,
        outdoor_exercise=False,
        school_run=False,
        burns_waste=False,
        audience="household",
    )
    base.update(overrides)
    from hearthline.models import Household

    return Household(**base)


class ImpactTests(unittest.TestCase):
    def test_sensitive_households_use_the_lower_outdoor_line(self):
        self.assertEqual(outdoor_limit(household()), 151)
        self.assertEqual(outdoor_limit(household(children=1)), 101)
        self.assertEqual(outdoor_limit(household(older_adults=1)), 101)
        self.assertEqual(outdoor_limit(household(sensitive=True)), 101)

    def test_dirtier_air_raises_the_unchanged_day(self):
        home = household(cooking="gas")
        low = totals(home, air_at(10), baseline_scenario(home))
        high = totals(home, air_at(180), baseline_scenario(home))
        self.assertGreater(high.inhaled_ug, low.inhaled_ug)

    def test_biomass_is_a_larger_indoor_source_than_induction(self):
        air = air_at(40, aqi=80)
        biomass = household(cooking="biomass")
        induction = household(cooking="induction")
        self.assertGreater(
            totals(biomass, air, baseline_scenario(biomass)).inhaled_ug,
            totals(induction, air, baseline_scenario(induction)).inhaled_ug,
        )

    def test_mask_helps_a_walking_commute_and_not_a_day_indoors(self):
        air = air_at(180)
        walker = household(commute="walk", distance="2_to_8")
        base = baseline_scenario(walker)
        masked = replace(base, mask=True)
        self.assertLess(totals(walker, air, masked).inhaled_ug, totals(walker, air, base).inhaled_ug)

        indoor = household()
        stay = baseline_scenario(indoor)
        self.assertAlmostEqual(
            totals(indoor, air, stay).inhaled_ug,
            totals(indoor, air, replace(stay, mask=True)).inhaled_ug,
        )

    def test_metro_saves_the_documented_co2e(self):
        home = household(commute="car", distance="2_to_8", transit_available=True)
        base = baseline_scenario(home)
        swapped = replace(base, work_mode="metro")
        km = DISTANCE_ROUND_KM["2_to_8"]
        expected = (CO2E_G_PER_PKM["car"] - CO2E_G_PER_PKM["metro"]) * km
        self.assertAlmostEqual(co2e_g(home, base) - co2e_g(home, swapped), expected)

    def test_idle_uses_the_documented_per_minute_factor(self):
        home = household(commute="car", school_run=True)
        base = baseline_scenario(home)
        quiet = replace(base, idle_min=0, school_wait_min=1)
        self.assertAlmostEqual(co2e_g(home, base) - co2e_g(home, quiet), 10 * IDLE_G_PER_MIN)

    def test_waste_and_wood_use_the_documented_factors(self):
        burning = household(burns_waste=True)
        self.assertAlmostEqual(emitted_pm_g(burning, baseline_scenario(burning)), WASTE_KG * WASTE_EF_G_PER_KG)
        wood = household(heating="wood_coal")
        self.assertAlmostEqual(emitted_pm_g(wood, baseline_scenario(wood)), WOOD_KG * WOOD_EF_G_PER_KG)
        controlled = replace(baseline_scenario(wood), heat_controlled=True)
        self.assertAlmostEqual(emitted_pm_g(wood, controlled), WOOD_KG * WOOD_EF_G_PER_KG * 0.5)

    def test_hepa_beats_the_diy_box_on_a_dirty_day(self):
        air = air_at(180)
        home = household(purifier=True, cooking="gas")
        base = baseline_scenario(home)
        diy = totals(home, air, replace(base, purifier_mode="diy")).inhaled_ug
        hepa = totals(home, air, replace(base, purifier_mode="hepa")).inhaled_ug
        off = totals(home, air, base).inhaled_ug
        self.assertLess(hepa, diy)
        self.assertLess(diy, off)

    def test_sample_day_improves_exposure_climate_and_smoke(self):
        home = sample_household()
        air = sample_air()
        plan, _reason = recommended_scenario(home, air)
        before = totals(home, air, baseline_scenario(home))
        after = totals(home, air, plan)
        self.assertLess(after.inhaled_ug, before.inhaled_ug)
        self.assertLess(after.co2e_g, before.co2e_g)
        self.assertLess(after.emitted_pm_g, before.emitted_pm_g)
        self.assertEqual(plan.work_mode, "metro")
        self.assertFalse(plan.burns)

    def test_hazardous_short_drive_is_not_swapped_for_a_longer_walk(self):
        home = household(
            commute="car",
            distance="under_2",
            transit_available=True,
            sensitive=True,
        )
        air = air_at(400)
        self.assertGreaterEqual(air.us_aqi, 201)
        plan, reason = recommended_scenario(home, air)
        self.assertEqual(plan.work_mode, "car")
        self.assertIsNotNone(reason)

    def test_moderate_day_for_a_healthy_adult_can_take_transit(self):
        home = household(commute="car", distance="2_to_8", transit_available=True)
        air = air_at(20, aqi=60)
        plan, reason = recommended_scenario(home, air)
        self.assertEqual(plan.work_mode, "metro")
        self.assertIsNone(reason)
        self.assertFalse(plan.mask)


if __name__ == "__main__":
    unittest.main()
