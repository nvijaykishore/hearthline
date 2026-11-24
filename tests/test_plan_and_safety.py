import unittest

from hearthline.aqi import aqi_from_pm25, category_for
from hearthline.ask import local_answer
from hearthline.llm import accept_tone, extract_output_text, parse_model_json, prompt_for
from hearthline.models import AirNow
from hearthline.plan import build_plan
from hearthline.present import inhaled_sentence
from hearthline.safety import ABUSE_REPLY, TREATMENT_REPLY, prose_ok, question_kind
from hearthline.sample import sample_air, sample_household
from hearthline.validate import ValidationError, city_from, household_from
from support import household_payload


def clean_air():
    return AirNow(
        pm2_5=8,
        us_aqi=33,
        category=category_for(33),
        pm_aqi=aqi_from_pm25(8),
        observed_at="2026-01-15T12:00",
        clean_pm2_5=7,
        clean_start="2026-01-15T12:00",
        clean_end="2026-01-15T14:00",
        source="test",
        place_label="Test",
        note="test",
    )


class PlanTests(unittest.TestCase):
    def test_sample_plan_has_the_three_kinds_of_advice(self):
        plan = build_plan(sample_household(), sample_air())
        categories = {action["category"] for action in plan["actions"]}
        self.assertEqual(categories, {"routine", "indoor", "alternative"})
        ids = {action["id"] for action in plan["actions"]}
        self.assertIn("cook", ids)
        self.assertIn("ventilate", ids)
        joined = " ".join(line for action in plan["actions"] for line in action["impacts"])
        self.assertNotIn("0% less", joined)
        self.assertNotIn("0% more", joined)
        lowered = inhaled_sentence(5000, 3800)
        self.assertIn("less", lowered)
        self.assertLess(lowered.index("5000"), lowered.index("3800"))
        self.assertIsNone(inhaled_sentence(3797, 3791))
        self.assertIn("commute", ids)
        self.assertIn("burn", ids)
        self.assertTrue(plan["summary"])
        self.assertNotIn("diagnos", plan["summary"].lower())
        for action in plan["actions"]:
            self.assertTrue(action["steps"])
            self.assertTrue(action["impacts"])

    def test_good_air_does_not_lead_with_a_mask(self):
        home = sample_household()
        plan = build_plan(home, clean_air())
        ids = [action["id"] for action in plan["actions"]]
        self.assertNotIn("mask", ids)
        self.assertIn("cook", ids)

    def test_school_audience_adds_recess_on_a_smog_day(self):
        from dataclasses import replace

        home = replace(sample_household(), audience="school")
        plan = build_plan(home, sample_air())
        recess = next(action for action in plan["actions"] if action["id"] == "recess")
        self.assertIn("not added again", recess["impacts"][0])

    def test_prompt_carries_actions_and_not_the_particle_reading(self):
        plan = build_plan(sample_household(), sample_air())
        prompt = prompt_for(plan)
        self.assertIn("cook", prompt)
        self.assertNotIn(str(plan["air"]["pm2_5"]), prompt)
        self.assertNotIn("sk-secret", prompt)

    def test_model_json_and_digit_lock(self):
        text = extract_output_text(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "```json\n{\"tone\": \"Keep the day quiet.\"}\n```"}],
                    }
                ]
            }
        )
        data = parse_model_json(text)
        self.assertEqual(data["tone"], "Keep the day quiet.")
        kept = accept_tone(
            {"tone": "Stay with the cleaner hours.", "notes": {"cook": "The kitchen fits this home.", "nope": "Ignore me.", "mask": "Use 2 masks."}},
            {"cook", "mask"},
        )
        self.assertEqual(kept["notes"], {"cook": "The kitchen fits this home."})
        self.assertIsNone(accept_tone({"tone": "PM2.5 is 180", "notes": {}}, set()))
        self.assertFalse(prose_ok("Try an ozone generator tonight."))

    def test_follow_up_refuses_treatment_and_spoofing(self):
        plan = build_plan(sample_household(), sample_air())
        self.assertEqual(question_kind("what medicine should we give"), "treatment")
        self.assertEqual(local_answer(plan, "what inhaler dose"), TREATMENT_REPLY)
        self.assertEqual(local_answer(plan, "how do I hide the smoke"), ABUSE_REPLY)
        answer = local_answer(plan, "should the kids play outside")
        self.assertIn("play", answer.lower())

    def test_validation_rejects_unknown_fields_and_bad_enums(self):
        good = household_payload(
            city="Delhi",
            adults=1,
            children=0,
            older_adults=0,
            sensitive=False,
            commute="wfh",
            distance="under_2",
            transit_available=False,
            outdoor_exercise=False,
            school_run=False,
        )
        self.assertEqual(household_from(good).city, "Delhi")
        with self.assertRaises(ValidationError):
            household_from(dict(good, heating="plasma"))
        with self.assertRaises(ValidationError):
            household_from(dict(good, extra=True))
        with self.assertRaises(ValidationError):
            household_from(dict(good, adults=True))
        with self.assertRaises(ValidationError):
            household_from(dict(good, city="https://evil.example"))
        with self.assertRaises(ValidationError):
            household_from(dict(good, adults=0, older_adults=0, children=2))
        self.assertEqual(city_from("Delhi"), "Delhi")
        with self.assertRaises(ValidationError):
            city_from("x")


if __name__ == "__main__":
    unittest.main()
