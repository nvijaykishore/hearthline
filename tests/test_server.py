import json
import threading
import unittest
import urllib.error
import urllib.request

from hearthline.aqi import aqi_from_pm25
from hearthline.sample import sample_payload
from hearthline.server import AppState, make_server
from support import household_payload


def _air_response(url):
    if "geocoding-api" in url:
        if "Ambiguous" in url or "Ambiguous" in urllib.request.unquote(url):
            return {
                "results": [
                    {"name": "Springfield", "admin1": "Illinois", "country": "United States", "latitude": 39.8, "longitude": -89.6},
                    {"name": "Springfield", "admin1": "Massachusetts", "country": "United States", "latitude": 42.1, "longitude": -72.5},
                ]
            }
        return {
            "results": [
                {"name": "Delhi", "admin1": "Delhi", "country": "India", "latitude": 28.6, "longitude": 77.2}
            ]
        }
    payload = sample_payload()
    payload["current"]["us_aqi"] = aqi_from_pm25(payload["current"]["pm2_5"])
    return payload


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        state = AppState(fetch=_air_response, explain_fn=lambda *args, **kwargs: None)
        cls.server = make_server("127.0.0.1", 0, state)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=5) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers, exc.read()

    def _post(self, path, payload):
        raw = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base + path,
            data=raw,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_page_and_security_headers(self):
        status, headers, body = self._get("/")
        self.assertEqual(status, 200)
        text = body.decode("utf-8")
        self.assertIn('lang="en"', text)
        self.assertIn('href="#results"', text)
        self.assertIn("<h1>", text)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")

    def test_sample_and_health(self):
        status, _headers, body = self._get("/api/sample")
        plan = json.loads(body.decode("utf-8"))
        self.assertEqual(status, 200)
        self.assertEqual(plan["air"]["source"], "sample")
        self.assertGreater(len(plan["actions"]), 3)
        status, headers, body = self._get("/api/health")
        health = json.loads(body.decode("utf-8"))
        self.assertTrue(health["ok"])
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_plan_with_coordinates_and_ambiguous_city(self):
        status, plan = self._post(
            "/api/plan",
            household_payload(latitude=28.6139, longitude=77.209),
        )
        self.assertEqual(status, 200)
        self.assertLess(plan["combined"]["inhaled_ug_plan"], plan["combined"]["inhaled_ug_baseline"])
        status, choice = self._post(
            "/api/plan",
            household_payload(
                city="Ambiguous",
                adults=1,
                children=0,
                older_adults=0,
                sensitive=False,
                cooking="induction",
                commute="wfh",
                distance="under_2",
                transit_available=False,
                outdoor_exercise=False,
                school_run=False,
            ),
        )
        self.assertEqual(status, 409)
        self.assertEqual(len(choice["places"]), 2)

    def test_rejects_bad_json_unknown_paths_and_treatment_questions(self):
        status, body = self._post("/api/plan", {"city": "nope"})
        self.assertEqual(status, 400)
        self.assertIn("fields", body)
        status, _headers, _body = self._get("/%2e%2e/server.py")
        self.assertEqual(status, 404)
        status, answer = self._post(
            "/api/ask",
            household_payload(
                question="what medicine should I take for chest pain",
                city="Delhi",
                latitude=28.6,
                longitude=77.2,
                adults=1,
                children=0,
                older_adults=0,
                sensitive=False,
                cooking="induction",
                commute="wfh",
                distance="under_2",
                transit_available=False,
                outdoor_exercise=False,
                school_run=False,
            ),
        )
        self.assertEqual(status, 200)
        self.assertIn("cannot diagnose", answer["answer"])

    def test_places_rejects_a_tiny_query(self):
        status, _headers, body = self._get("/api/places?q=x")
        self.assertEqual(status, 400)
        payload = json.loads(body.decode("utf-8"))
        self.assertIn("fields", payload)

    def test_static_script_does_not_inject_html(self):
        _status, _headers, body = self._get("/app.js")
        script = body.decode("utf-8")
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("document.write", script)
        self.assertNotIn("eval(", script)


if __name__ == "__main__":
    unittest.main()
