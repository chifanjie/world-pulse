#!/usr/bin/env python3
"""Create an irregular, history-aware editorial activity plan."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime


CATEGORIES = [
    "politics",
    "economy",
    "markets",
    "technology",
    "science",
    "climate-environment",
    "health-society",
    "culture",
]

ACTIVITY_WEIGHTS = ((1, 44), (2, 34), (3, 17), (4, 5))
EXTRA_CANDIDATES = [
    "deep-dive",
    "source-diversity-check",
    "context-timeline",
    "small-data-view",
    "methodology-maintenance",
]
COLOR_LEVELS = [
    "FIRST_QUARTILE",
    "SECOND_QUARTILE",
    "THIRD_QUARTILE",
    "FOURTH_QUARTILE",
]


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_counts(value: str) -> list[int]:
    if not value.strip():
        return []
    counts = [int(part) for part in value.split(",")]
    if any(count < 0 or count > 20 for count in counts):
        raise argparse.ArgumentTypeError("recent counts must be between 0 and 20")
    return counts


def parse_color_targets(value: str) -> list[int]:
    targets = [int(part) for part in value.split(",")]
    if len(targets) != 4 or any(target < 1 for target in targets):
        raise argparse.ArgumentTypeError("color targets must contain four positive counts")
    if targets != sorted(targets):
        raise argparse.ArgumentTypeError("color targets must be in ascending order")
    return targets


def weighted_activity(sample: int) -> int:
    bucket = sample % 100
    cumulative = 0
    for activity, weight in ACTIVITY_WEIGHTS:
        cumulative += weight
        if bucket < cumulative:
            return activity
    return 1


def adjust_activity(sampled: int, recent_counts: list[int], nudge: int) -> int:
    """Break obvious streaks while retaining a quiet-day bias."""
    recent = recent_counts[-14:]
    activity = sampled

    if len(recent) >= 3 and recent[-3:] == [activity] * 3:
        alternatives = [count for count in (1, 2, 3, 4) if count != activity]
        activity = alternatives[nudge % len(alternatives)]

    if len(recent) >= 4 and all(count <= 1 for count in recent[-4:]):
        activity = max(activity, 2)

    if len(recent) >= 5 and sum(recent[-5:]) >= 13:
        activity = min(activity, 2)

    if len(recent) >= 14 and recent[-7:] == recent[-14:-7]:
        activity = 2 if activity == 1 else 1

    return activity


def irregular_gap(anchor: date, label: str, minimum: int, maximum: int) -> int:
    digest = hashlib.sha256(f"world-pulse/{label}|{anchor.isoformat()}".encode()).digest()
    return minimum + digest[0] % (maximum - minimum + 1)


def choose_color_level(sample: int, lab_due: bool, review_due: bool) -> str:
    """Reserve visibly darker levels for genuine project-sized work."""
    roll = sample % 100
    if lab_due:
        if roll < 8:
            return "THIRD_QUARTILE"
        if roll < 78:
            return "SECOND_QUARTILE"
    elif review_due and roll < 20:
        return "SECOND_QUARTILE"
    return "FIRST_QUARTILE"


def build_plan(
    day: date,
    last_lab: date | None = None,
    last_review: date | None = None,
    recent_counts: list[int] | None = None,
    color_targets: list[int] | None = None,
) -> dict[str, object]:
    recent = list(recent_counts or [])[-14:]
    history = ",".join(str(count) for count in recent)
    digest = hashlib.sha256(
        f"world-pulse/v2|{day.isoformat()}|{history}".encode()
    ).digest()
    story_count = 6 + digest[0] % 5
    lead_category = CATEGORIES[digest[1] % len(CATEGORIES)]
    deep_dives = 1 + digest[1] % 2

    activity_cap = adjust_activity(weighted_activity(digest[2]), recent, digest[3])

    lab_due = False
    lab_gap_days: int | None = None
    if last_lab is not None:
        lab_gap_days = irregular_gap(last_lab, "lab", 9, 21)
        lab_due = (day - last_lab).days >= lab_gap_days

    review_due = False
    review_gap_days: int | None = None
    if last_review is not None:
        review_gap_days = irregular_gap(last_review, "review", 5, 10)
        review_due = (day - last_review).days >= review_gap_days

    required_extras: list[str] = []
    if review_due:
        required_extras.append("rolling-review")
    if lab_due:
        required_extras.append("tested-lab")
    activity_cap = max(activity_cap, min(4, 1 + len(required_extras)))

    rotated = EXTRA_CANDIDATES[digest[4] % len(EXTRA_CANDIDATES) :] + EXTRA_CANDIDATES[
        : digest[4] % len(EXTRA_CANDIDATES)
    ]
    candidates = required_extras + [item for item in rotated if item not in required_extras]
    candidates = candidates[: max(0, activity_cap - 1)]

    color_level = choose_color_level(digest[5], lab_due, review_due)
    color_target = None
    if color_targets:
        color_target = color_targets[COLOR_LEVELS.index(color_level)]

    return {
        "date": day.isoformat(),
        "target_story_count": story_count,
        "lead_category": lead_category,
        "deep_dive_count": deep_dives,
        "activity_cap": activity_cap,
        "recent_activity": recent,
        "candidate_extras": candidates,
        "review_due": review_due,
        "review_gap_days": review_gap_days,
        "lab_due": lab_due,
        "lab_gap_days": lab_gap_days,
        "desired_color_level": color_level,
        "target_total_contributions": color_target,
        "auto_target_darkest": False,
        "note": (
            "Activity and color targets are ceilings, not quotas. A darker target may "
            "only be pursued through independently useful, tested project work; never "
            "create filler or empty commits."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=parse_date, default=date.today())
    parser.add_argument("--last-lab", type=parse_date)
    parser.add_argument("--last-review", type=parse_date)
    parser.add_argument("--recent-counts", type=parse_counts, default=[])
    parser.add_argument("--color-targets", type=parse_color_targets)
    args = parser.parse_args(argv)
    print(
        json.dumps(
            build_plan(
                args.date,
                args.last_lab,
                args.last_review,
                args.recent_counts,
                args.color_targets,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
