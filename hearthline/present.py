"""Turn engine quantities into the sentences the page shows.

Every figure in these sentences is passed in. This module does not invent one.
"""

from __future__ import annotations

from hearthline.models import DayTotals


def ug(value: float) -> str:
    if abs(value) >= 10:
        return f"{value:.0f} µg"
    return f"{value:.1f} µg"


def co2e(grams: float) -> str:
    sign = "−" if grams < 0 else ""
    magnitude = abs(grams)
    if magnitude >= 1000:
        return f"{sign}{magnitude / 1000:.1f} kg CO₂e"
    return f"{sign}{magnitude:.0f} g CO₂e"


def grams(value: float) -> str:
    return f"{abs(value):.0f} g"


def pct(value: float) -> str:
    return f"{abs(value):.0f}%"


def inhaled_sentence(before: float, after: float) -> str | None:
    """`before` is the day without this step. `after` is the day with it."""
    if before <= 1 and after <= 1:
        return None
    delta = before - after
    share = abs(delta) / max(before, 1.0) * 100.0
    # A rounded 0% reads as a broken figure. Leave the sentence out.
    if abs(delta) < 1 or int(share + 0.5) < 1:
        return None
    if delta > 0:
        return (
            f"This step brings the household's inhaled PM2.5 from about {ug(before)} down to about {ug(after)} "
            f"(about {pct(share)} less)."
        )
    return (
        f"This step raises the household's inhaled PM2.5 from about {ug(before)} to about {ug(after)} "
        f"(about {pct(share)} more)."
    )


def co2e_sentence(before: float, after: float) -> str | None:
    delta = before - after
    if abs(delta) < 50:
        return None
    if delta > 0:
        return (
            f"This step brings climate pollution from about {co2e(before)} down to about {co2e(after)} "
            f"(about {co2e(delta)} less)."
        )
    return (
        f"This step raises climate pollution from about {co2e(before)} to about {co2e(after)} "
        f"(about {co2e(abs(delta))} more)."
    )


def emitted_sentence(before: float, after: float) -> str | None:
    delta = before - after
    if abs(delta) < 1:
        return None
    if delta > 0:
        return (
            f"This step keeps about {grams(delta)} of PM2.5 out of the neighborhood air "
            f"(about {grams(before)} down to about {grams(after)})."
        )
    return (
        f"This step sends about {grams(delta)} more PM2.5 into the neighborhood air "
        f"(about {grams(before)} up to about {grams(after)})."
    )


def _join_clauses(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]}, and {parts[1]}"
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def headline(before: DayTotals, after: DayTotals) -> str:
    parts: list[str] = []
    if before.inhaled_ug > 1:
        delta = before.inhaled_ug - after.inhaled_ug
        share = delta / before.inhaled_ug * 100.0
        if delta > 1:
            parts.append(
                f"inhaled PM2.5 falls from about {ug(before.inhaled_ug)} to about {ug(after.inhaled_ug)} ({pct(share)} less)"
            )
        elif delta < -1:
            parts.append(
                f"inhaled PM2.5 rises from about {ug(before.inhaled_ug)} to about {ug(after.inhaled_ug)}"
            )
    c_delta = before.co2e_g - after.co2e_g
    if c_delta >= 50:
        parts.append(f"climate pollution falls by about {co2e(c_delta)}")
    elif c_delta <= -50:
        parts.append(f"climate pollution rises by about {co2e(abs(c_delta))}")
    e_delta = before.emitted_pm_g - after.emitted_pm_g
    if e_delta >= 1:
        parts.append(f"about {grams(e_delta)} less PM2.5 is sent into neighborhood air")
    if not parts:
        return "The day you described is already close to this plan. The cards are the remaining moves."
    return f"Against an unchanged day, {_join_clauses(parts)}."
