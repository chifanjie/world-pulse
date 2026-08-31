import json
import tempfile
import unittest
from pathlib import Path

from labs.pulse_timeline.pulse_timeline import build_timeline, collect_paths


class PulseTimelineTests(unittest.TestCase):
    def write_daily(self, root: Path, date: str, items: list[dict]) -> Path:
        path = root / f"{date}.json"
        path.write_text(json.dumps({"date": date, "items": items}), encoding="utf-8")
        return path

    def test_orders_by_date_then_id_and_filters_category(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_daily(
                root,
                "2026-08-31",
                [
                    {"id": "b", "title": "B", "category": "technology", "regions": ["Z", "A"]},
                    {"id": "a", "title": "A", "category": "economy", "regions": []},
                ],
            )
            earlier = self.write_daily(
                root,
                "2026-08-27",
                [{"id": "c", "title": "C", "category": "technology", "regions": ["Asia"]}],
            )
            payload = build_timeline([root], category="technology")
            self.assertEqual(payload["dates"], ["2026-08-27", "2026-08-31"])
            self.assertEqual([entry["id"] for entry in payload["entries"]], ["c", "b"])
            self.assertEqual(payload["entries"][-1]["regions"], ["A", "Z"])
            self.assertEqual(collect_paths([root / "data", earlier]), [earlier.resolve()])

    def test_rejects_missing_required_item_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_daily(Path(temporary), "2026-08-31", [{"id": "x"}])
            with self.assertRaises(ValueError):
                build_timeline([path])


if __name__ == "__main__":
    unittest.main()
