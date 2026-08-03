#!/usr/bin/env python3
"""Create a deterministic editorial plan without prescribing commit counts."""

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


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def build_plan(day: date, last_lab: date | None = None) -> dict[str, object]:
    digest = hashlib.sha256(f"world-pulse/v1|{day.isoformat()}".encode()).digest()
    story_count = 6 + digest[0] % 5
    lead_category = CATEGORIES[day.toordinal() % len(CATEGORIES)]
    deep_dives = 1 + digest[1] % 2

    lab_due = False
    lab_gap_days: int | None = None
    if last_lab is not None:
        lab_seed = hashlib.sha256(
            f"world-pulse/lab|{last_lab.isoformat()}".encode()
        ).digest()
        lab_gap_days = 10 + lab_seed[0] % 9
        lab_due = (day - last_lab).days >= lab_gap_days

    return {
        "date": day.isoformat(),
        "target_story_count": story_count,
        "lead_category": lead_category,
        "deep_dive_count": deep_dives,
        "chart_candidate": day.weekday() == 2,
        "weekly_review": day.weekday() == 6,
        "lab_due": lab_due,
        "lab_gap_days": lab_gap_days,
        "note": "Extra work is optional and must represent an independently useful result.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=parse_date, default=date.today())
    parser.add_argument("--last-lab", type=parse_date)
    args = parser.parse_args(argv)
    print(json.dumps(build_plan(args.date, args.last_lab), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
