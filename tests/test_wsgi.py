import io
import json
import os
import unittest

from hearthline.sample import sample_payload
from hearthline.server import AppState, request_ip
from hearthline.wsgi import build_app


def _fetch(url):
    payload = sample_payload()
    return payload


def _call(application, method, path, body=None, headers=None, remote="127.0.0.1"):
    raw = b"" if body is None else json.dumps(body).encode("utf-8")
    path_only, _, query = path.partition("?")
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path_only,
        "QUERY_STRING": query,
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "80",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "wsgi.input": io.BytesIO(raw),
        "wsgi.errors": io.StringIO(),
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
        "REMOTE_ADDR": remote,
    }
    if body is not None:
        environ["CONTENT_TYPE"] = "application/json"
        environ["CONTENT_LENGTH"] = str(len(raw))
    for key, value in (headers or {}).items():
        environ["HTTP_" + key.upper().replace("-", "_")] = value
    captured = {}

    def start_response(status, response_headers, exc_info=None):
        captured["status"] = status
        captured["headers"] = dict(response_headers)

    payload = b"".join(application(environ, start_response))
    return captured["status"], captured["headers"], payload


class WsgiTests(unittest.TestCase):
    def test_page_health_and_plan_use_the_same_handler(self):
        application = build_app(AppState(fetch=_fetch, explain_fn=lambda *args, **kwargs: None))
        status, headers, body = _call(application, "GET", "/")
        self.assertTrue(status.startswith("200"))
        self.assertIn(b"<h1>", body)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        status, headers, body = _call(application, "GET", "/styles.css")
        self.assertTrue(status.startswith("200"))
        self.assertIn("text/css", headers["Content-Type"])
        self.assertIn(b"--paper:", body)
        status, _headers, body = _call(application, "GET", "/api/health")
        self.assertTrue(status.startswith("200"))
        self.assertTrue(json.loads(body)["ok"])
        status, _headers, body = _call(
            application,
            "POST",
            "/api/plan",
            {
                "city": "Delhi, India",
                "latitude": 28.6139,
                "longitude": 77.209,
                "adults": 2,
                "children": 1,
                "older_adults": 0,
                "sensitive": True,
                "heating": "none",
                "cooking": "gas",
                "purifier": False,
                "commute": "car",
                "distance": "2_to_8",
                "transit_available": True,
                "outdoor_exercise": True,
                "school_run": False,
                "burns_waste": False,
                "audience": "household",
            },
        )
        self.assertTrue(status.startswith("200"))
        plan = json.loads(body)
        self.assertLess(plan["combined"]["inhaled_ug_plan"], plan["combined"]["inhaled_ug_baseline"])

    def test_platform_address_is_used_only_when_vercel_sets_it(self):
        self.assertEqual(request_ip({"x-real-ip": "203.0.113.9"}, "10.0.0.1"), "10.0.0.1")
        os.environ["VERCEL"] = "1"
        try:
            self.assertEqual(request_ip({"x-real-ip": "203.0.113.9"}, "10.0.0.1"), "203.0.113.9")
            self.assertEqual(request_ip({"x-real-ip": "203.0.113.9, 1.2.3.4"}, "10.0.0.1"), "10.0.0.1")
            self.assertEqual(request_ip({"x-real-ip": "not-an-ip"}, "10.0.0.1"), "10.0.0.1")
            application = build_app(AppState(fetch=_fetch, explain_fn=lambda *args, **kwargs: None))
            for _ in range(60):
                status, _headers, _body = _call(
                    application, "GET", "/api/places?q=Delhi", headers={"x-real-ip": "203.0.113.9"}
                )
                self.assertTrue(status.startswith("200"))
            blocked, _headers, _body = _call(
                application, "GET", "/api/places?q=Delhi", headers={"x-real-ip": "203.0.113.9"}
            )
            other, _headers, _body = _call(
                application, "GET", "/api/places?q=Delhi", headers={"x-real-ip": "203.0.113.10"}
            )
            self.assertTrue(blocked.startswith("429"))
            self.assertTrue(other.startswith("200"))
        finally:
            os.environ.pop("VERCEL", None)


if __name__ == "__main__":
    unittest.main()
