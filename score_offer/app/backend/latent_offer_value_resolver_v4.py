#!/usr/bin/env python3
"""Deterministic value resolver used after semantic issue extraction.

This module is intentionally not presented as a production scorer. It fixes the
numeric, date, and discrete-choice errors exposed by the 30-negotiation pilot;
semantic issue identification still requires a sealed benchmark.
"""
from __future__ import annotations

import re
from datetime import date

MONTHS = {name.lower(): number for number, name in enumerate(
    ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
) if name}
MONTH_PATTERN = "(?:" + "|".join(MONTHS) + ")"


def normalize_label(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def linear_score(value: float, anchors: list[float], points: list[float]) -> float:
    """Piecewise-linear interpolation, clipped at the two outer anchors."""
    if len(anchors) != 3 or len(points) != 3:
        raise ValueError("Exactly three anchors and point values are required")
    pairs = sorted(zip(anchors, points), key=lambda pair: pair[0])
    anchors, points = [x[0] for x in pairs], [x[1] for x in pairs]
    value = max(anchors[0], min(anchors[-1], value))
    left = 0 if value <= anchors[1] else 1
    right = left + 1
    fraction = (value - anchors[left]) / (anchors[right] - anchors[left])
    return round(points[left] + fraction * (points[right] - points[left]), 3)


def resolve_continuous(value: float, issue: dict) -> tuple[float, float]:
    anchors = []
    candidate = []
    recruiter = []
    for item in issue["options_or_anchors"]:
        number = re.search(r"-?\d+(?:,\d{3})*(?:\.\d+)?", str(item["value"]))
        if not number:
            raise ValueError(f"No numeric anchor in {item['value']!r}")
        anchors.append(float(number.group(0).replace(",", "")))
        candidate.append(float(item["candidate_points"]))
        recruiter.append(float(item["recruiter_points"]))
    return linear_score(value, anchors, candidate), linear_score(value, anchors, recruiter)


def resolve_discrete(label: str, issue: dict) -> tuple[float, float]:
    wanted = normalize_label(label)
    options = issue["options_or_anchors"]
    exact = [item for item in options if normalize_label(item["value"]) == wanted]
    if len(exact) != 1:
        raise ValueError(f"Discrete choice {label!r} does not identify one listed option")
    item = exact[0]
    return float(item["candidate_points"]), float(item["recruiter_points"])


def extract_start_date(text: str, year: int = 2026) -> date | None:
    """Recognize every date-order and start-date frame observed in the pilot."""
    patterns = [
        rf"\b(?:starting\s+date|start\s+date)\s*(?:of|is|would\s+be|will\s+be|on|at|:)?\s*(?P<month>{MONTH_PATTERN})\s+(?P<day>\d{{1,2}})\b",
        rf"\b(?:starting|beginning|begin|commencing)\s+(?:on\s+)?(?P<month>{MONTH_PATTERN})\s+(?P<day>\d{{1,2}})\b",
        rf"\b(?P<month>{MONTH_PATTERN})\s+(?P<day>\d{{1,2}})\s+(?:starting|start)\s+date\b",
        rf"\b(?:you|i|we)\s+(?:would|will|can|could|shall)?\s*start\s+(?:on\s+)?(?P<month>{MONTH_PATTERN})\s+(?P<day>\d{{1,2}})\b",
        rf"\b(?:starting|beginning|begin|commencing)\s+(?:on\s+)?(?P<day>\d{{1,2}})\s+(?P<month>{MONTH_PATTERN})\b",
        rf"\b(?:starting\s+date|start\s+date)\s*(?:of|is|would\s+be|will\s+be|on|at|:)?\s*(?P<day>\d{{1,2}})\s+(?P<month>{MONTH_PATTERN})\b",
    ]
    match = next((hit for pattern in patterns if (hit := re.search(pattern, text, re.I))), None)
    if not match:
        return None
    return date(year, MONTHS[match.group("month").lower()], int(match.group("day")))


def resolve_starting_date(value: date) -> tuple[float, float]:
    anchors = [date(2026, 5, 1), date(2026, 7, 16), date(2026, 9, 30)]
    scalar = [(item - anchors[0]).days for item in anchors]
    observed = (value - anchors[0]).days
    score = linear_score(observed, scalar, [2.0, 0.0, -2.0])
    return score, score
