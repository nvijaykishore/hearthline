"""Local HTTP server. The API key never reaches the browser."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Generic, TypeVar
from urllib.parse import ParseResult, parse_qs, unquote, urlparse

from hearthline.aqi import AirError, fetch_json, load_air, search_places
from hearthline.ask import local_answer
from hearthline.llm import MODEL, accept_tone, configured, explain
from hearthline.models import AirNow, Household
from hearthline.plan import apply_tone, build_plan
from hearthline.safety import question_kind
from hearthline.sample import sample_air, sample_household
from hearthline.validate import ValidationError, city_from, coordinates_supplied, household_from, question_from

_T = TypeVar("_T")

_STATIC_ROOT = Path(__file__).resolve().parent / "static"
_STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}
_SECURITY = {
    "Content-Security-Policy": (
        "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self'; "
        "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


class ChoosePlace(Exception):
    def __init__(self, places: list[dict]):
        self.places = places
        super().__init__("Choose a place.")


class TtlCache(Generic[_T]):
    def __init__(self, ttl_s: float, max_items: int = 200):
        self.ttl = ttl_s
        self.max_items = max_items
        self._data: dict[object, tuple[float, _T]] = {}
        self._lock = threading.Lock()

    def get(self, key: object) -> _T | None:
        now = time.monotonic()
        with self._lock:
            item = self._data.get(key)
            if item is None or item[0] < now:
                self._data.pop(key, None)
                return None
            return item[1]

    def set(self, key: object, value: _T) -> None:
        with self._lock:
            if len(self._data) >= self.max_items:
                self._data.clear()
            self._data[key] = (time.monotonic() + self.ttl, value)


class RateLimiter:
    def __init__(self, limit: int, window_s: float):
        self.limit = limit
        self.window = window_s
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = [stamp for stamp in self._hits.get(key, []) if now - stamp < self.window]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > 4000:
                self._hits.clear()
            return True


class AppState:
    def __init__(
        self,
        fetch: Callable[..., dict] = fetch_json,
        explain_fn: Callable[..., dict | None] = explain,
    ) -> None:
        self.fetch = fetch
        self.explain_fn = explain_fn
        self.air_cache: TtlCache[AirNow] = TtlCache(20 * 60)
        self.place_cache: TtlCache[list[dict]] = TtlCache(6 * 3600)
        self.plans = RateLimiter(20, 600)
        self.asks = RateLimiter(30, 600)
        self.places = RateLimiter(60, 600)
        self.static = {
            path: ((_STATIC_ROOT / name).read_bytes(), mime) for path, (name, mime) in _STATIC.items()
        }


def _guard(tone: dict | None, plan: dict) -> dict | None:
    if not isinstance(tone, dict):
        return None
    return accept_tone(tone, {action["id"] for action in plan["actions"]})


def _phrasing(state: AppState, plan: dict, question: str | None = None) -> dict | None:
    try:
        raw = state.explain_fn(plan) if question is None else state.explain_fn(plan, question)
        return _guard(raw, plan)
    except Exception:
        return None


def resolve_household(state: AppState, payload: dict) -> tuple[Household, str]:
    household = household_from(payload)
    if coordinates_supplied(payload):
        return household, household.city
    key = household.city.casefold()
    found = state.place_cache.get(key)
    if found is None:
        found = search_places(household.city, fetch=state.fetch)
        state.place_cache.set(key, found)
    if not found:
        raise AirError("No matching place. Try a larger city name.")
    if len(found) > 1:
        raise ChoosePlace(found)
    place = found[0]
    located = replace(
        household,
        city=place["label"],
        latitude=place["latitude"],
        longitude=place["longitude"],
    )
    return located, place["label"]


def air_for(state: AppState, household: Household, label: str) -> AirNow:
    key = (round(household.latitude, 2), round(household.longitude, 2))
    cached = state.air_cache.get(key)
    if cached is not None:
        return cached
    air = load_air(household.latitude, household.longitude, label, fetch=state.fetch)
    state.air_cache.set(key, air)
    return air


_IP = re.compile(r"\A[0-9A-Fa-f:.]{2,64}\Z")


def request_ip(headers: object, peer: str) -> str:
    """Visitor key for rate limits. On Vercel the socket peer is the platform."""
    if os.environ.get("VERCEL"):
        raw = headers.get("x-real-ip") if headers is not None else None
        token = (raw or "").strip()
        if _IP.fullmatch(token):
            return token
    return peer or "unknown"


def make_plan(state: AppState, household: Household, label: str) -> dict:
    plan = build_plan(household, air_for(state, household, label))
    return apply_tone(plan, _phrasing(state, plan))


class Handler(BaseHTTPRequestHandler):
    server_version = "Hearthline"
    protocol_version = "HTTP/1.0"

    def _security(self, cache: str) -> None:
        for key, value in _SECURITY.items():
            self.send_header(key, value)
        self.send_header("Cache-Control", cache)

    def _json(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._security("no-store")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict:
        ctype = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if ctype != "application/json":
            raise ValidationError({"form": "Send JSON."})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError as exc:
            raise ValidationError({"form": "Send JSON."}) from exc
        if length <= 0 or length > 8000:
            raise ValidationError({"form": "That request is the wrong size."})
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValidationError({"form": "That JSON could not be read."}) from exc
        if not isinstance(data, dict):
            raise ValidationError({"form": "Send a JSON object."})
        return data

    def _ip(self) -> str:
        peer = self.client_address[0] if self.client_address else ""
        return request_ip(self.headers, peer)

    def _state(self) -> AppState:
        return self.server.state

    def _route_path(self) -> tuple[str | None, ParseResult]:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path != parsed.path or ".." in path or "\\" in path:
            return None, parsed
        return path, parsed

    def _handle(self, work: Callable[[], None]) -> None:
        try:
            work()
        except ValidationError as exc:
            self._json(400, {"error": "Check the highlighted fields.", "fields": exc.fields})
        except ChoosePlace as exc:
            self._json(409, {"error": "Choose the matching place.", "places": exc.places})
        except AirError as exc:
            self._json(502, {"error": str(exc)})
        except Exception:
            traceback.print_exc()
            self._json(500, {"error": "Something went wrong on our side."})

    def _send_static(self, path: str) -> None:
        body, mime = self._state().static[path]
        self.send_response(200)
        self._security("public, max-age=300")
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _places(self, parsed: ParseResult) -> None:
        state = self._state()
        if not state.places.allow(self._ip()):
            self._json(429, {"error": "Too many place lookups. Wait a few minutes."})
            return
        name = (parse_qs(parsed.query).get("q") or [""])[0]
        try:
            city_from(name)
        except ValidationError as exc:
            self._json(400, {"error": "Check the place name.", "fields": exc.fields})
            return
        found = search_places(name, fetch=state.fetch)
        self._json(200, {"places": found})

    def _plan(self, payload: dict) -> None:
        state = self._state()
        if not state.plans.allow(self._ip()):
            self._json(429, {"error": "Too many plans from this network. Wait a few minutes."})
            return
        household, label = resolve_household(state, payload)
        self._json(200, make_plan(state, household, label))

    def _ask(self, payload: dict) -> None:
        state = self._state()
        if not state.asks.allow(self._ip()):
            self._json(429, {"error": "Too many questions. Wait a few minutes."})
            return
        question = question_from(payload)
        body = dict(payload)
        body.pop("question", None)
        household, label = resolve_household(state, body)
        plan = build_plan(household, air_for(state, household, label))
        answer = local_answer(plan, question)
        tone = ""
        source = "local"
        if question_kind(question) == "plan":
            phrased = _phrasing(state, plan, question)
            if phrased and phrased.get("tone"):
                tone = phrased["tone"]
                source = "model"
        self._json(
            200,
            {
                "answer": answer,
                "tone": tone,
                "narrative_source": source,
                "summary": plan["summary"],
            },
        )

    def _get(self, path: str, parsed: ParseResult) -> None:
        state = self._state()
        if path == "/api/health":
            self._json(200, {"ok": True, "llm_configured": configured(), "model": MODEL})
            return
        if path == "/api/sample":
            self._json(200, build_plan(sample_household(), sample_air()))
            return
        if path == "/api/places":
            self._places(parsed)
            return
        if path in state.static:
            self._send_static(path)
            return
        self._json(404, {"error": "Not found."})

    def _post(self, path: str) -> None:
        if path not in ("/api/plan", "/api/ask"):
            self._json(404, {"error": "Not found."})
            return
        payload = self._read_json()
        if path == "/api/plan":
            self._plan(payload)
            return
        self._ask(payload)

    def do_GET(self):
        path, parsed = self._route_path()
        if path is None:
            self._json(404, {"error": "Not found."})
            return
        self._handle(lambda: self._get(path, parsed))

    def do_POST(self):
        path, _parsed = self._route_path()
        if path is None:
            self._json(404, {"error": "Not found."})
            return
        self._handle(lambda: self._post(path))

    def _not_allowed(self) -> None:
        self._json(405, {"error": "Method not allowed."})

    def do_PUT(self):
        self._not_allowed()

    def do_DELETE(self):
        self._not_allowed()


class HearthServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], state: AppState):
        self.state = state
        super().__init__(address, Handler)


def make_server(host: str = "127.0.0.1", port: int = 8000, state: AppState | None = None) -> HearthServer:
    return HearthServer((host, port), state or AppState())


def _load_dotenv() -> None:
    """Read a local .env without overriding variables already set. No dependency."""
    path = Path.cwd() / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> None:
    _load_dotenv()
    host = os.environ.get("HEARTHLINE_HOST", "127.0.0.1")
    port = int(os.environ.get("HEARTHLINE_PORT", "8000"))
    server = make_server(host, port)
    print(f"Hearthline listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()
