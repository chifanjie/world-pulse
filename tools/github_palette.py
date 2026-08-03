#!/usr/bin/env python3
"""Read a GitHub user's live contribution colors and observed count ranges."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import date
from typing import Any


LEVELS = [
    "FIRST_QUARTILE",
    "SECOND_QUARTILE",
    "THIRD_QUARTILE",
    "FOURTH_QUARTILE",
]

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        colors
        weeks {
          contributionDays {
            date
            contributionCount
            contributionLevel
            color
          }
        }
      }
    }
  }
}
"""


def _run_gh(arguments: list[str]) -> str:
    completed = subprocess.run(
        ["gh", *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout


def current_login() -> str:
    return _run_gh(["api", "user", "--jq", ".login"]).strip()


def fetch_calendar(login: str) -> dict[str, Any]:
    output = _run_gh(
        [
            "api",
            "graphql",
            "-f",
            f"query={QUERY}",
            "-F",
            f"login={login}",
        ]
    )
    payload = json.loads(output)
    user = payload.get("data", {}).get("user")
    if not user:
        raise RuntimeError(f"GitHub user not found: {login}")
    return user["contributionsCollection"]["contributionCalendar"]


def analyze_calendar(calendar: dict[str, Any], today: str | None = None) -> dict[str, Any]:
    days = [
        day
        for week in calendar.get("weeks", [])
        for day in week.get("contributionDays", [])
    ]
    positive_days = [day for day in days if day.get("contributionCount", 0) > 0]
    maximum = max((day["contributionCount"] for day in positive_days), default=0)
    palette = calendar.get("colors", [])

    levels: list[dict[str, Any]] = []
    for index, level in enumerate(LEVELS):
        matching = [day for day in positive_days if day["contributionLevel"] == level]
        counts = sorted({day["contributionCount"] for day in matching})
        estimated_lower_bound = 1 if maximum == 0 else maximum * index // 4 + 1
        observed_min = min(counts) if counts else None
        target_min = observed_min or estimated_lower_bound
        levels.append(
            {
                "level": level,
                "color": matching[0]["color"] if matching else (
                    palette[index] if index < len(palette) else None
                ),
                "observed_min": observed_min,
                "observed_max": max(counts) if counts else None,
                "observed_counts": counts,
                "estimated_lower_bound": estimated_lower_bound,
                "safe_seen_target": target_min,
            }
        )

    today_value = today or date.today().isoformat()
    today_data = next((day for day in days if day.get("date") == today_value), None)
    return {
        "total_contributions": calendar.get("totalContributions", 0),
        "maximum_daily_count": maximum,
        "palette": palette,
        "levels": levels,
        "target_values": [level["safe_seen_target"] for level in levels],
        "today": today_data,
        "note": (
            "GitHub levels are relative to the current calendar. Re-query before "
            "planning; observed targets are safer than assuming fixed thresholds."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--login", help="GitHub login; defaults to the authenticated user")
    parser.add_argument("--today", help="Date to report in YYYY-MM-DD form")
    args = parser.parse_args(argv)
    login = args.login or current_login()
    result = analyze_calendar(fetch_calendar(login), args.today)
    result["login"] = login
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
