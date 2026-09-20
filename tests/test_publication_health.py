from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from labs.publication_health.publication_health import audit


class PublicationHealthTests(unittest.TestCase):
    def make_digest(self, root, day, generated, markdown=True):
        data = root / "data" / day[:4] / day[5:7] / f"{day}.json"
        data.parent.mkdir(parents=True, exist_ok=True)
        link = f"digests/{day[:4]}/{day[5:7]}/{day}.md"
        if markdown:
            target = root / link
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# A digest\n", encoding="utf-8")
        data.write_text(json.dumps({"date": day, "generated_at": generated, "digest_path": link}), encoding="utf-8")

    def test_empty_archive_reports_every_missing_day_across_month_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            report = audit(Path(folder), date(2026, 8, 31), date(2026, 9, 2))
        self.assertEqual(report["missing_dates"], ["2026-08-31", "2026-09-01", "2026-09-02"])
        self.assertIsNone(report["latest_digest"])

    def test_backfill_is_present_but_honestly_reported_as_late(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_digest(root, "2026-09-02", "2026-09-20T16:00:00+08:00")
            report = audit(root, date(2026, 9, 2), date(2026, 9, 2))
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["late_published_dates"], ["2026-09-02"])

    def test_utc_timestamp_is_compared_in_shanghai_time(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_digest(root, "2026-09-02", "2026-09-01T17:00:00Z")
            report = audit(root, date(2026, 9, 2), date(2026, 9, 2))
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["late_published_dates"], [])

    def test_missing_markdown_and_invalid_date_do_not_count_as_published(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_digest(root, "2026-09-02", "2026-09-02T16:00:00+08:00", markdown=False)
            self.make_digest(root, "2026-09-03", "2026-09-01T16:00:00+08:00")
            report = audit(root, date(2026, 9, 2), date(2026, 9, 3))
        self.assertEqual(report["present_count"], 0)
        self.assertEqual(len(report["errors"]), 2)

    def test_reversed_window_fails(self):
        with self.assertRaises(ValueError):
            audit(Path("."), date(2026, 9, 3), date(2026, 9, 2))

    def test_future_generation_does_not_count_as_published(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_digest(root, "2026-09-02", "2026-09-20T16:00:00+08:00")
            report = audit(root, date(2026, 9, 2), date(2026, 9, 2),
                           now=datetime.fromisoformat("2026-09-20T15:00:00+08:00"))
        self.assertEqual(report["present_count"], 0)
        self.assertIn("in the future", report["errors"][0])

    def test_existing_but_wrong_markdown_does_not_fill_a_gap(self):
        for wrong_link in ("digests/2026/09/2026-09-19.md", "README.md"):
            with self.subTest(link=wrong_link), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                self.make_digest(root, "2026-09-20", "2026-09-20T09:00:00+08:00")
                target = root / wrong_link
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("# Not today's digest\n", encoding="utf-8")
                data_path = root / "data/2026/09/2026-09-20.json"
                payload = json.loads(data_path.read_text(encoding="utf-8"))
                payload["digest_path"] = wrong_link
                data_path.write_text(json.dumps(payload), encoding="utf-8")
                report = audit(root, date(2026, 9, 20), date(2026, 9, 20))
            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["present_count"], 0)
            self.assertIn("same archive day", report["errors"][0])


if __name__ == "__main__":
    unittest.main()
