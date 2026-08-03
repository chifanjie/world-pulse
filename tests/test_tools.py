from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tools.build_index import collect_entries
from tools.plan_day import build_plan
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

    def test_index_collects_daily_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_valid_fixture(root)
            entries = collect_entries(root)
            self.assertEqual(entries[0]["date"], "2026-08-03")
            self.assertEqual(entries[0]["item_count"], 5)

    def test_plan_is_deterministic_and_marks_sunday(self) -> None:
        day = date(2026, 8, 9)
        self.assertEqual(build_plan(day), build_plan(day))
        self.assertTrue(build_plan(day)["weekly_review"])


if __name__ == "__main__":
    unittest.main()
