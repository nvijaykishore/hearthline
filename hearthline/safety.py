"""Keep model prose from inventing a measurement or giving medical advice."""

from __future__ import annotations

import re

_DIGIT = re.compile(r"\d")
_BANNED = re.compile(
    r"ozone generator|ioniz|detox|guaranteed|prescri|diagnos|cure your|100\s*%|miracle",
    re.IGNORECASE,
)
_TREATMENT = re.compile(
    r"\b(diagnos|prescri|medication|medicine|dosage|inhaler|antibiotic|"
    r"what (?:drug|pill)|chest pain|cannot breathe|can't breathe|heart attack)\b",
    re.IGNORECASE,
)
_ABUSE = re.compile(
    r"\b(fake the|defeat the monitor|spoof|hide the (?:smoke|fire)|not get caught|evade the)\b",
    re.IGNORECASE,
)

TREATMENT_REPLY = (
    "Hearthline cannot diagnose, prescribe, or advise medicines. "
    "If someone is struggling to breathe or has chest pain, seek urgent care. "
    "The plan is about exposure and emissions only."
)

ABUSE_REPLY = (
    "Hearthline will not help hide burning or spoof an air reading. "
    "The useful step is to not burn it, and to shorten time in the plume."
)


def prose_ok(text: str, limit: int = 500) -> bool:
    if not isinstance(text, str):
        return False
    clean = text.strip()
    if not clean or len(clean) > limit:
        return False
    if _DIGIT.search(clean) or _BANNED.search(clean):
        return False
    return True


def question_kind(question: str) -> str:
    if _TREATMENT.search(question):
        return "treatment"
    if _ABUSE.search(question):
        return "abuse"
    return "plan"
