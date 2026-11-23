import unittest

from hearthline.aqi import (
    AirError,
    allowed_url,
    aqi_from_pm25,
    category_for,
    cleanest_window,
    parse_air,
)
from hearthline.sample import sample_air, sample_payload


class AqiTests(unittest.TestCase):
    def test_breakpoints_match_the_epa_formula(self):
        self.assertEqual(aqi_from_pm25(0), 0)
        self.assertEqual(aqi_from_pm25(12.0), 50)
        self.assertEqual(aqi_from_pm25(12.1), 51)
        self.assertEqual(aqi_from_pm25(35.4), 100)
        self.assertEqual(aqi_from_pm25(35.5), 101)
        self.assertEqual(aqi_from_pm25(55.5), 151)
        # 100 µg/m³ sits inside 55.5–150.4 → 151–200.
        expected = int((200 - 151) / (150.4 - 55.5) * (100 - 55.5) + 151 + 0.5)
        self.assertEqual(aqi_from_pm25(100), expected)
        self.assertEqual(aqi_from_pm25(600), 500)

    def test_category_words(self):
        self.assertEqual(category_for(50), "Good")
        self.assertEqual(category_for(101), "Unhealthy for Sensitive Groups")
        self.assertEqual(category_for(201), "Very Unhealthy")
        self.assertEqual(category_for(301), "Hazardous")

    def test_negative_pm_is_rejected(self):
        with self.assertRaises(AirError):
            aqi_from_pm25(-1)

    def test_cleanest_window_picks_the_afternoon_dip(self):
        air = sample_air()
        self.assertEqual(air.clean_start, "2026-01-15T14:00")
        self.assertLess(air.clean_pm2_5, 70)
        self.assertGreater(air.pm2_5, air.clean_pm2_5)

    def test_missing_pm_is_an_error(self):
        with self.assertRaises(AirError):
            parse_air({"current": {}}, "Nowhere")

    def test_only_known_https_hosts(self):
        self.assertTrue(allowed_url("https://air-quality-api.open-meteo.com/v1/air-quality"))
        self.assertTrue(allowed_url("https://api.x.ai/v1/responses"))
        self.assertFalse(allowed_url("http://air-quality-api.open-meteo.com/v1/air-quality"))
        self.assertFalse(allowed_url("https://evil.example/v1/air-quality"))
        self.assertFalse(allowed_url("https://api.x.ai.evil.example/v1/responses"))

    def test_window_skips_incomplete_hours(self):
        times = ["2026-01-15T08:00", "2026-01-15T09:00", "2026-01-15T10:00", "2026-01-15T11:00"]
        window = cleanest_window(times, [None, 10, 12, 11], "2026-01-15T08:00", width=3, horizon=4)
        self.assertEqual(window[0], 11)
        self.assertEqual(window[1], "2026-01-15T09:00")
        missing = cleanest_window(times, [None, None, 12, None], "2026-01-15T08:00", width=3, horizon=4)
        self.assertIsNone(missing)

    def test_sample_payload_parses(self):
        air = parse_air(sample_payload(), "Delhi, India", source="sample")
        self.assertEqual(air.source, "sample")
        self.assertIn("not a live", air.note)


if __name__ == "__main__":
    unittest.main()
