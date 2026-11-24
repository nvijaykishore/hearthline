"""Answer a follow-up from the plan that was just calculated."""

from __future__ import annotations

import re

from hearthline.safety import ABUSE_REPLY, TREATMENT_REPLY, question_kind

_TOPICS = (
    (re.compile(r"\b(school|recess|classroom|teacher)\b", re.I), "recess"),
    (re.compile(r"\b(mask|n95|ffp2|respirator)\b", re.I), "mask"),
    (re.compile(r"\b(window|ventilat|air out|airing)\b", re.I), "ventilate"),
    (re.compile(r"\b(cook|kitchen|stove|gas|fry)\b", re.I), "cook"),
    (re.compile(r"\b(burn|trash|waste|bonfire)\b", re.I), "burn"),
    (re.compile(r"\b(exercise|run|play|sport|jog)\b", re.I), "exercise"),
    (re.compile(r"\b(infant|baby|newborn|toddler)\b", re.I), "mask"),
    (re.compile(r"\b(commute|metro|bus|car|drive|idle)\b", re.I), "commute"),
    (re.compile(r"\b(purifier|filter|hepa|fan)\b", re.I), "bedroom"),
)


def _action(plan: dict, action_id: str) -> dict | None:
    for action in plan["actions"]:
        if action["id"] == action_id:
            return action
    return None


def local_answer(plan: dict, question: str) -> str:
    kind = question_kind(question)
    if kind == "treatment":
        return TREATMENT_REPLY
    if kind == "abuse":
        return ABUSE_REPLY
    for pattern, action_id in _TOPICS:
        if pattern.search(question):
            action = _action(plan, action_id)
            if action is None and action_id == "recess":
                action = _action(plan, "exercise")
            if action is not None:
                impact = " ".join(action["impacts"])
                return f"{action['title']}. {impact}"
    first = plan["actions"][0]
    impact = " ".join(first["impacts"])
    return (
        f"The plan's figures did not change. Start with {first['title']}. {impact}"
    )
