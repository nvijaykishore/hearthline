"""Ask Grok to phrase a plan it is not allowed to recalculate.

The request sets store=false so the household description is not kept on the
provider. Figures stay in the engine. Prose with a digit, or with a banned
claim, is dropped and the local sentences remain.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request

from hearthline.aqi import USER_AGENT, allowed_url
from hearthline.safety import prose_ok

MODEL = os.environ.get("XAI_MODEL", "grok-4.7")
URL = "https://api.x.ai/v1/responses"
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)

_SYSTEM = (
    "You phrase a household air plan that was already calculated. "
    "You do not diagnose, prescribe, or recommend treatment. "
    "You do not recommend ozone generators, ionizers, herbs, or lung detoxes. "
    "You do not invent or restate any measurement. Use no digits and no percentages. "
    "The screen already shows every figure. "
    "Reply with one JSON object and nothing else, using keys tone and notes. "
    "tone is two short sentences for the family. "
    "notes maps each given action id to one sentence about why that action fits this household. "
    "Omit an id rather than guess. Use only the ids you are given."
)


def configured() -> bool:
    return bool(os.environ.get("XAI_API_KEY"))


def extract_output_text(body: dict) -> str:
    if isinstance(body.get("output_text"), str):
        return body["output_text"]
    chunks: list[str] = []
    for item in body.get("output") or []:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("text"), str) and item.get("type") != "message":
            chunks.append(item["text"])
        for part in item.get("content") or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "".join(chunks)


def parse_model_json(text: str) -> dict | None:
    raw = _FENCE.sub("", text.strip())
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def prompt_for(plan: dict, question: str | None = None) -> str:
    actions = [
        {"id": action["id"], "title": action["title"], "category": action["category"]}
        for action in plan["actions"]
    ]
    payload = {
        "place": plan["place"]["label"],
        "air_category": plan["air"]["category"],
        "audience": plan["audience_line"],
        "actions": actions,
    }
    if question:
        payload["question"] = question
    return json.dumps(payload, ensure_ascii=False)


def accept_tone(data: dict, allowed_ids: set[str]) -> dict | None:
    tone = data.get("tone") if isinstance(data.get("tone"), str) else ""
    notes_in = data.get("notes") if isinstance(data.get("notes"), dict) else {}
    notes = {}
    for key, value in notes_in.items():
        if key in allowed_ids and isinstance(value, str) and prose_ok(value, limit=280):
            notes[key] = value.strip()
    kept_tone = tone.strip() if prose_ok(tone, limit=400) else ""
    if not kept_tone and not notes:
        return None
    return {"tone": kept_tone, "notes": notes}


def _post(key: str, user: str, timeout: float) -> dict:
    if not allowed_url(URL):
        raise RuntimeError("refused")
    body = json.dumps(
        {
            "model": MODEL,
            "store": False,
            "input": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        URL,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read(1_000_000).decode("utf-8"))


def explain(plan: dict, question: str | None = None, timeout: float = 25.0) -> dict | None:
    key = os.environ.get("XAI_API_KEY")
    if not key:
        return None
    user = prompt_for(plan, question)
    try:
        body = _post(key, user, timeout)
        text = extract_output_text(body)
        data = parse_model_json(text)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if data is None:
        return None
    return accept_tone(data, set(action["id"] for action in plan["actions"]))
