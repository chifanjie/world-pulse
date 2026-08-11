#!/usr/bin/env python3
"""Create an irregular, history-aware editorial activity plan."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timedelta


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


def parse_nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be a non-negative integer") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be a non-negative integer")
    return parsed


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


def highest_reachable_color(
    total_contributions: int, color_targets: list[int]
) -> tuple[str, int] | tuple[None, None]:
    """Return the darkest level with a safely observed target within reach."""
    reachable_level: str | None = None
    reachable_target: int | None = None
    for level, target in zip(COLOR_LEVELS, color_targets):
        if total_contributions < target:
            break
        reachable_level = level
        reachable_target = target
    if reachable_level is None:
        return None, None
    return reachable_level, reachable_target


def build_plan(
    day: date,
    last_lab: date | None = None,
    last_review: date | None = None,
    recent_counts: list[int] | None = None,
    color_targets: list[int] | None = None,
    project_start: date | None = None,
    today_contributions: int = 0,
    planned_atomic_units: int | None = None,
) -> dict[str, object]:
    if today_contributions < 0:
        raise ValueError("today_contributions must be non-negative")
    if planned_atomic_units is not None and planned_atomic_units < 0:
        raise ValueError("planned_atomic_units must be non-negative")

    recent = list(recent_counts or [])[-14:]
    history = ",".join(str(count) for count in recent)
    digest = hashlib.sha256(
        f"world-pulse/v2|{day.isoformat()}|{history}".encode()
    ).digest()
    story_count = 6 + digest[0] % 5
    lead_category = CATEGORIES[digest[1] % len(CATEGORIES)]
    deep_dives = 1 + digest[1] % 2

    activity_cap = adjust_activity(weighted_activity(digest[2]), recent, digest[3])

    lab_anchor = last_lab or project_start
    lab_anchor_source = (
        "last-lab" if last_lab is not None else "project-start" if project_start else None
    )
    lab_due = False
    lab_gap_days: int | None = None
    lab_due_date: date | None = None
    if lab_anchor is not None:
        lab_gap_days = irregular_gap(lab_anchor, "lab", 9, 21)
        lab_due_date = lab_anchor + timedelta(days=lab_gap_days)
        lab_due = day >= lab_due_date

    review_anchor = last_review or project_start
    review_anchor_source = (
        "last-review"
        if last_review is not None
        else "project-start" if project_start else None
    )
    review_due = False
    review_gap_days: int | None = None
    review_due_date: date | None = None
    if review_anchor is not None:
        review_gap_days = irregular_gap(review_anchor, "review", 5, 10)
        review_due_date = review_anchor + timedelta(days=review_gap_days)
        review_due = day >= review_due_date

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

    aspirational_color_level = choose_color_level(digest[5], lab_due, review_due)
    aspirational_color_target = None
    achievable_color_level = None
    achievable_color_target = None
    desired_color_level = aspirational_color_level
    color_target = None
    color_target_reachable = None

    reachability_atomic_units = (
        activity_cap
        if planned_atomic_units is None
        else min(planned_atomic_units, activity_cap)
    )
    reachable_total_contributions = today_contributions + reachability_atomic_units

    if color_targets:
        aspirational_color_target = color_targets[
            COLOR_LEVELS.index(aspirational_color_level)
        ]
        achievable_color_level, achievable_color_target = highest_reachable_color(
            reachable_total_contributions, color_targets
        )
        color_target_reachable = (
            reachable_total_contributions >= aspirational_color_target
        )
        if color_target_reachable:
            color_target = aspirational_color_target
        else:
            desired_color_level = achievable_color_level or "NONE"
            color_target = achievable_color_target

    remaining_contributions_to_target = (
        None
        if color_target is None
        else max(0, color_target - today_contributions)
    )
    remaining_contributions_to_aspirational_target = (
        None
        if aspirational_color_target is None
        else max(0, aspirational_color_target - today_contributions)
    )

    return {
        "date": day.isoformat(),
        "project_start": project_start.isoformat() if project_start else None,
        "target_story_count": story_count,
        "lead_category": lead_category,
        "deep_dive_count": deep_dives,
        "activity_cap": activity_cap,
        "recent_activity": recent,
        "candidate_extras": candidates,
        "review_due": review_due,
        "review_anchor": review_anchor.isoformat() if review_anchor else None,
        "review_anchor_source": review_anchor_source,
        "review_gap_days": review_gap_days,
        "review_due_date": review_due_date.isoformat() if review_due_date else None,
        "lab_due": lab_due,
        "lab_anchor": lab_anchor.isoformat() if lab_anchor else None,
        "lab_anchor_source": lab_anchor_source,
        "lab_gap_days": lab_gap_days,
        "lab_due_date": lab_due_date.isoformat() if lab_due_date else None,
        "today_contributions": today_contributions,
        "planned_atomic_units": planned_atomic_units,
        "reachability_planned_atomic_units": reachability_atomic_units,
        "planned_atomic_units_limited_by_activity_cap": (
            planned_atomic_units is not None and planned_atomic_units > activity_cap
        ),
        "reachable_total_contributions": reachable_total_contributions,
        "aspirational_color_level": aspirational_color_level,
        "aspirational_target_total_contributions": aspirational_color_target,
        "achievable_color_level": achievable_color_level,
        "achievable_target_total_contributions": achievable_color_target,
        "desired_color_level": desired_color_level,
        "target_total_contributions": color_target,
        "color_target_reachable": color_target_reachable,
        "remaining_contributions_to_target": remaining_contributions_to_target,
        "remaining_contributions_to_aspirational_target": (
            remaining_contributions_to_aspirational_target
        ),
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
    parser.add_argument("--project-start", type=parse_date)
    parser.add_argument("--last-lab", type=parse_date)
    parser.add_argument("--last-review", type=parse_date)
    parser.add_argument("--recent-counts", type=parse_counts, default=[])
    parser.add_argument("--color-targets", type=parse_color_targets)
    parser.add_argument(
        "--today-contributions", type=parse_nonnegative_int, default=0
    )
    parser.add_argument("--planned-atomic-units", type=parse_nonnegative_int)
    args = parser.parse_args(argv)
    print(
        json.dumps(
            build_plan(
                day=args.date,
                last_lab=args.last_lab,
                last_review=args.last_review,
                recent_counts=args.recent_counts,
                color_targets=args.color_targets,
                project_start=args.project_start,
                today_contributions=args.today_contributions,
                planned_atomic_units=args.planned_atomic_units,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
