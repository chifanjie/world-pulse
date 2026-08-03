from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tools.build_index import collect_entries
from tools.github_palette import analyze_calendar
from tools.plan_day import (
    adjust_activity,
    build_plan,
    choose_color_level,
    irregular_gap,
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
