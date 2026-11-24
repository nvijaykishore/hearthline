"""WSGI entry so Vercel can serve the same handler as the local server."""

from __future__ import annotations

import io
import traceback
from collections.abc import Callable, Mapping
from email.parser import BytesParser
from email.policy import HTTP

from hearthline.server import AppState, Handler

_METHODS = {"GET", "POST", "PUT", "DELETE"}


class _Server:
    def __init__(self, state: AppState):
        self.state = state


def _header_block(environ: Mapping[str, object]) -> bytes:
    lines: list[str] = []
    for key, value in environ.items():
        if not key.startswith("HTTP_") or value is None:
            continue
        lines.append(f"{key[5:].replace('_', '-')}: {value}")
    content_type = environ.get("CONTENT_TYPE")
    if content_type:
        lines.append(f"Content-Type: {content_type}")
    content_length = environ.get("CONTENT_LENGTH")
    if content_length:
        lines.append(f"Content-Length: {content_length}")
    text = "\r\n".join(lines) + "\r\n\r\n"
    return text.encode("latin-1", "replace")


def _split_response(raw: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n") if head else []
    status = "500 Internal Server Error"
    headers: list[tuple[str, str]] = []
    if lines:
        parts = lines[0].split(" ", 2)
        if len(parts) >= 3:
            status = f"{parts[1]} {parts[2]}"
        elif len(parts) == 2:
            status = f"{parts[1]} OK"
        for line in lines[1:]:
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            headers.append((name.strip(), value.strip()))
    return status, headers, body


def build_app(state: AppState | None = None) -> Callable:
    bound = _Server(state or AppState())

    def application(environ, start_response):
        method = environ.get("REQUEST_METHOD") or "GET"
        path = environ.get("PATH_INFO") or "/"
        query = environ.get("QUERY_STRING") or ""
        target = f"{path}?{query}" if query else path
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        payload = environ["wsgi.input"].read(max(length, 0)) if length > 0 else b""
        handler = Handler.__new__(Handler)
        handler.server = bound
        handler.client_address = (environ.get("REMOTE_ADDR") or "0.0.0.0", 0)
        handler.request_version = "HTTP/1.1"
        handler.command = method
        handler.path = target
        handler.requestline = f"{method} {target} HTTP/1.1"
        handler.close_connection = True
        handler.headers = BytesParser(policy=HTTP).parsebytes(_header_block(environ))
        handler.rfile = io.BytesIO(payload)
        handler.wfile = io.BytesIO()
        try:
            if method not in _METHODS:
                handler._json(405, {"error": "Method not allowed."})
            else:
                getattr(handler, "do_" + method)()
        except Exception:
            traceback.print_exc()
            if not handler.wfile.getvalue():
                handler._json(500, {"error": "Something went wrong on our side."})
        status, headers, body = _split_response(handler.wfile.getvalue())
        start_response(status, headers)
        return [body]

    return application


app = build_app()
