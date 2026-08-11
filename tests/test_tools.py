from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

from tools.build_index import collect_entries
from tools.github_palette import analyze_calendar
from tools.plan_day import (
    adjust_activity,
    build_plan,
    choose_color_level,
    irregular_gap,
    main as plan_day_main,
)
from tools.validate_digest import validate_file


class ToolTests(unittest.TestCase):
    def make_valid_fixture(self, root: Path) -> Path:
        digest = root / "digests" / "2026" / "08" / "2026-08-03.md"
        digest.parent.mkdir(parents=True)
        source_url = "https://example.org/report"
        markers = []
        items = []
        for index in range(5):
            event_id = f"event-{index}"
            markers.append(f"<!-- event:{event_id} -->\n{source_url}?id={index}")
            items.append(
                {
                    "id": event_id,
                    "category": "science",
                    "regions": ["Global"],
                    "title": f"Event {index}",
                    "summary": "A sourced event summary.",
                    "why_it_matters": "It demonstrates the schema.",
                    "uncertainty": "No material uncertainty reported.",
                    "confidence": "high",
                    "sources": [
                        {
                            "publisher": "Example",
                            "title": "Example report",
                            "url": f"{source_url}?id={index}",
                            "published_at": "2026-08-03",
                            "source_type": "primary",
                        }
                    ],
                }
            )
            if index < 3:
                items[-1]["section"] = "ai-frontier"
                items[-1]["ai"] = {
                    "kind": "paper",
                    "topics": ["evaluation"],
                    "artifact_date": "2026-08-03",
                    "artifact_status": "preprint",
                    "technical_takeaway": "A concrete technical result.",
                    "evidence_level": "primary-material",
                    "heat": {
                        "label": "platform-trending",
                        "as_of": "2026-08-03T21:30:00+08:00",
                        "signals": [
                            {
                                "platform": "Example",
                                "observation": "Ranked in a dated list.",
                                "url": f"{source_url}?id={index}",
                            }
                        ],
                    },
                }
        digest.write_text("\n".join(markers), encoding="utf-8")

        data_file = root / "data" / "2026" / "08" / "2026-08-03.json"
        data_file.parent.mkdir(parents=True)
        data_file.write_text(
            json.dumps(
                {
                    "date": "2026-08-03",
                    "timezone": "Asia/Shanghai",
                    "generated_at": "2026-08-03T21:30:00+08:00",
                    "overview": "A valid daily overview.",
                    "digest_path": "digests/2026/08/2026-08-03.md",
                    "ai_radar": {
                        "selection_as_of": "2026-08-03T21:30:00+08:00",
                        "item_ids": ["event-0", "event-1", "event-2"],
                    },
                    "items": items,
                }
            ),
            encoding="utf-8",
        )
        return data_file

    def test_valid_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_file = self.make_valid_fixture(root)
            self.assertEqual(validate_file(data_file, root), [])

    def test_duplicate_id_and_bad_url_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_file = self.make_valid_fixture(root)
            payload = json.loads(data_file.read_text(encoding="utf-8"))
            payload["items"][1]["id"] = payload["items"][0]["id"]
            payload["items"][2]["sources"][0]["url"] = "not-a-url"
            data_file.write_text(json.dumps(payload), encoding="utf-8")
            errors = validate_file(data_file, root)
            self.assertTrue(any("duplicated" in error for error in errors))
            self.assertTrue(any("HTTP(S)" in error for error in errors))

    def test_ai_radar_requires_structured_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_file = self.make_valid_fixture(root)
            payload = json.loads(data_file.read_text(encoding="utf-8"))
            del payload["items"][0]["section"]
            payload["items"][1]["ai"]["heat"]["as_of"] = "not-a-timestamp"
            payload["ai_radar"]["item_ids"][2] = payload["ai_radar"]["item_ids"][1]
            data_file.write_text(json.dumps(payload), encoding="utf-8")
            errors = validate_file(data_file, root)
            self.assertTrue(any("section 'ai-frontier'" in error for error in errors))
            self.assertTrue(any("zoned ISO timestamp" in error for error in errors))
            self.assertTrue(any("must not contain duplicates" in error for error in errors))

    def test_index_collects_daily_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_valid_fixture(root)
            entries = collect_entries(root)
            self.assertEqual(entries[0]["date"], "2026-08-03")
            self.assertEqual(entries[0]["item_count"], 5)
            self.assertEqual(entries[0]["ai_radar_count"], 3)

    def test_plan_is_deterministic_with_history(self) -> None:
        day = date(2026, 8, 9)
        recent = [1, 2, 1, 3, 1, 2]
        self.assertEqual(
            build_plan(day, recent_counts=recent),
            build_plan(day, recent_counts=recent),
        )

    def test_plan_varies_without_weekday_rules(self) -> None:
        caps = {
            build_plan(date(2026, 8, day))["activity_cap"] for day in range(1, 29)
        }
        self.assertGreaterEqual(len(caps), 3)

    def test_activity_breaks_long_streaks(self) -> None:
        self.assertNotEqual(adjust_activity(1, [1, 1, 1], 0), 1)
        self.assertGreaterEqual(adjust_activity(1, [1, 1, 1, 1], 0), 2)

    def test_irregular_gaps_stay_in_bounds(self) -> None:
        for day in range(1, 20):
            gap = irregular_gap(date(2026, 7, day), "lab", 9, 21)
            self.assertGreaterEqual(gap, 9)
            self.assertLessEqual(gap, 21)

    def test_project_start_bootstraps_first_review_and_lab(self) -> None:
        project_start = date(2026, 8, 3)
        review_due_date = project_start.replace(day=12)
        lab_due_date = project_start.replace(day=14)

        before_lab = build_plan(
            review_due_date,
            project_start=project_start,
        )
        self.assertEqual(before_lab["review_anchor"], "2026-08-03")
        self.assertEqual(before_lab["review_anchor_source"], "project-start")
        self.assertEqual(before_lab["review_due_date"], "2026-08-12")
        self.assertTrue(before_lab["review_due"])
        self.assertEqual(before_lab["lab_anchor"], "2026-08-03")
        self.assertEqual(before_lab["lab_anchor_source"], "project-start")
        self.assertEqual(before_lab["lab_due_date"], "2026-08-14")
        self.assertFalse(before_lab["lab_due"])

        on_lab_due_date = build_plan(
            lab_due_date,
            project_start=project_start,
        )
        self.assertTrue(on_lab_due_date["review_due"])
        self.assertTrue(on_lab_due_date["lab_due"])
        self.assertEqual(
            on_lab_due_date["candidate_extras"][:2],
            ["rolling-review", "tested-lab"],
        )

    def test_last_artifact_dates_take_priority_over_project_start(self) -> None:
        project_start = date(2026, 8, 3)
        last_review = date(2026, 8, 10)
        last_lab = date(2026, 8, 9)
        plan = build_plan(
            date(2026, 8, 11),
            project_start=project_start,
            last_review=last_review,
            last_lab=last_lab,
        )

        self.assertEqual(plan["review_anchor"], "2026-08-10")
        self.assertEqual(plan["review_anchor_source"], "last-review")
        self.assertEqual(
            plan["review_due_date"],
            date.fromordinal(
                last_review.toordinal()
                + irregular_gap(last_review, "review", 5, 10)
            ).isoformat(),
        )
        self.assertEqual(plan["lab_anchor"], "2026-08-09")
        self.assertEqual(plan["lab_anchor_source"], "last-lab")
        self.assertEqual(
            plan["lab_due_date"],
            date.fromordinal(
                last_lab.toordinal() + irregular_gap(last_lab, "lab", 9, 21)
            ).isoformat(),
        )

    def test_unreachable_color_target_is_downgraded(self) -> None:
        with patch(
            "tools.plan_day.choose_color_level", return_value="SECOND_QUARTILE"
        ):
            plan = build_plan(
                date(2026, 8, 12),
                project_start=date(2026, 8, 3),
                color_targets=[1, 24, 44, 81],
                today_contributions=0,
                planned_atomic_units=4,
            )

        self.assertEqual(plan["aspirational_color_level"], "SECOND_QUARTILE")
        self.assertEqual(plan["aspirational_target_total_contributions"], 24)
        self.assertEqual(
            plan["reachability_planned_atomic_units"], plan["activity_cap"]
        )
        self.assertEqual(plan["reachable_total_contributions"], plan["activity_cap"])
        self.assertTrue(plan["planned_atomic_units_limited_by_activity_cap"])
        self.assertEqual(plan["achievable_color_level"], "FIRST_QUARTILE")
        self.assertEqual(plan["desired_color_level"], "FIRST_QUARTILE")
        self.assertEqual(plan["target_total_contributions"], 1)
        self.assertFalse(plan["color_target_reachable"])

    def test_existing_contributions_reduce_remaining_color_work(self) -> None:
        with patch(
            "tools.plan_day.choose_color_level", return_value="SECOND_QUARTILE"
        ):
            plan = build_plan(
                date(2026, 8, 12),
                project_start=date(2026, 8, 3),
                color_targets=[1, 24, 44, 81],
                today_contributions=23,
                planned_atomic_units=1,
            )

        self.assertEqual(plan["reachable_total_contributions"], 24)
        self.assertEqual(plan["achievable_color_level"], "SECOND_QUARTILE")
        self.assertEqual(plan["desired_color_level"], "SECOND_QUARTILE")
        self.assertEqual(plan["target_total_contributions"], 24)
        self.assertEqual(plan["remaining_contributions_to_target"], 1)
        self.assertTrue(plan["color_target_reachable"])

    def test_plan_day_cli_accepts_new_planning_inputs(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = plan_day_main(
                [
                    "--date",
                    "2026-08-12",
                    "--project-start",
                    "2026-08-03",
                    "--recent-counts",
                    "1,0,1",
                    "--color-targets",
                    "1,24,44,81",
                    "--today-contributions",
                    "3",
                    "--planned-atomic-units",
                    "2",
                ]
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(payload["project_start"], "2026-08-03")
        self.assertEqual(payload["review_anchor_source"], "project-start")
        self.assertEqual(payload["today_contributions"], 3)
        self.assertEqual(payload["planned_atomic_units"], 2)
        self.assertEqual(payload["recent_activity"], [1, 0, 1])

    def test_color_target_never_auto_selects_darkest(self) -> None:
        levels = {
            choose_color_level(sample, lab_due=True, review_due=True)
            for sample in range(100)
        }
        self.assertNotIn("FOURTH_QUARTILE", levels)
        self.assertIn("SECOND_QUARTILE", levels)
        self.assertIn("THIRD_QUARTILE", levels)

    def test_palette_uses_live_observed_ranges(self) -> None:
        fixture = {
            "totalContributions": 100,
            "colors": ["#1", "#2", "#3", "#4"],
            "weeks": [
                {
                    "contributionDays": [
                        {
                            "date": "2026-08-01",
                            "contributionCount": 4,
                            "contributionLevel": "FIRST_QUARTILE",
                            "color": "#1",
                        },
                        {
                            "date": "2026-08-02",
                            "contributionCount": 24,
                            "contributionLevel": "SECOND_QUARTILE",
                            "color": "#2",
                        },
                        {
                            "date": "2026-08-03",
                            "contributionCount": 44,
                            "contributionLevel": "THIRD_QUARTILE",
                            "color": "#3",
                        },
                        {
                            "date": "2026-08-04",
                            "contributionCount": 81,
                            "contributionLevel": "FOURTH_QUARTILE",
                            "color": "#4",
                        },
                    ]
                }
            ],
        }
        result = analyze_calendar(fixture, "2026-08-03")
        self.assertEqual(result["target_values"], [4, 24, 44, 81])
        self.assertEqual(result["today"]["contributionLevel"], "THIRD_QUARTILE")


if __name__ == "__main__":
    unittest.main()
