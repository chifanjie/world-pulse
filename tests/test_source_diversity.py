from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.build_source_diversity import (
    SourceDiversityError,
    build_report,
    render_report,
    write_report,
)


class SourceDiversityTests(unittest.TestCase):
    def write_index(self, root: Path, entries: list[dict[str, object]]) -> None:
        index = root / "data" / "index.json"
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(
            json.dumps({"version": 1, "entries": entries}), encoding="utf-8"
        )

    def write_daily(
        self, root: Path, digest_date: str, items: list[dict[str, object]]
    ) -> str:
        relative = f"data/{digest_date[:4]}/{digest_date[5:7]}/{digest_date}.json"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "date": digest_date,
                    "generated_at": f"{digest_date}T09:00:00+08:00",
                    "items": items,
                }
            ),
            encoding="utf-8",
        )
        return relative

    @staticmethod
    def source(
        publisher: str,
        url: str,
        source_type: str = "primary",
        title: str = "Source",
    ) -> dict[str, str]:
        return {
            "publisher": publisher,
            "title": title,
            "url": url,
            "published_at": "2026-08-10",
            "source_type": source_type,
        }

    def test_aggregates_sections_regions_publishers_and_types(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            older_path = self.write_daily(
                root,
                "2026-08-10",
                [
                    {
                        "id": "world-event",
                        "category": "health-society",
                        "regions": ["Europe", "Global", "Europe"],
                        "title": "World event",
                        "confidence": "high",
                        "sources": [
                            self.source("WHO", "https://who.int/report"),
                            self.source(
                                "Reuters",
                                "https://reuters.com/report",
                                "wire",
                            ),
                        ],
                    }
                ],
            )
            newer_path = self.write_daily(
                root,
                "2026-08-11",
                [
                    {
                        "id": "ai-event",
                        "section": "ai-frontier",
                        "category": "technology",
                        "regions": ["Global"],
                        "title": "AI event",
                        "confidence": "medium",
                        "sources": [
                            self.source(
                                "Example Lab",
                                "https://example.org/model",
                                "model-card",
                            )
                        ],
                    }
                ],
            )
            self.write_index(
                root,
                [
                    {"date": "2026-08-11", "data_path": newer_path},
                    {"date": "2026-08-10", "data_path": older_path},
                ],
            )

            report = build_report(root)

            self.assertEqual(report["date_range"], {"start": "2026-08-10", "end": "2026-08-11"})
            self.assertEqual(report["counts"]["digests"], 2)
            self.assertEqual(report["counts"]["events"], 2)
            self.assertEqual(report["counts"]["world_events"], 1)
            self.assertEqual(report["counts"]["ai_events"], 1)
            self.assertEqual(report["counts"]["source_links"], 3)
            self.assertEqual(report["counts"]["single_source_events"], 1)
            self.assertEqual(report["events"][0]["id"], "ai-event")
            self.assertEqual(
                report["regions"],
                [
                    {"name": "Global", "event_count": 2},
                    {"name": "Europe", "event_count": 1},
                ],
            )
            self.assertEqual(
                {row["name"]: row["source_links"] for row in report["source_types"]},
                {"primary": 1, "wire": 1, "model-card": 1},
            )
            self.assertEqual(
                {row["name"] for row in report["publishers"]},
                {"WHO", "Reuters", "Example Lab"},
            )

    def test_deduplicates_equivalent_source_urls_within_an_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_path = self.write_daily(
                root,
                "2026-08-11",
                [
                    {
                        "id": "duplicate-source",
                        "title": "Duplicate source",
                        "regions": ["Global"],
                        "sources": [
                            self.source("Example", "https://EXAMPLE.org/report/"),
                            self.source(
                                "Example Duplicate",
                                "https://example.org/report#section",
                            ),
                        ],
                    }
                ],
            )
            self.write_index(
                root, [{"date": "2026-08-11", "data_path": data_path}]
            )

            report = build_report(root)

            self.assertEqual(report["counts"]["source_links"], 1)
            self.assertEqual(report["counts"]["unique_source_urls"], 1)
            self.assertTrue(report["events"][0]["single_source"])
            self.assertEqual(len(report["events"][0]["sources"]), 1)

    def test_missing_daily_file_has_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_index(
                root,
                [
                    {
                        "date": "2026-08-11",
                        "data_path": "data/2026/08/2026-08-11.json",
                    }
                ],
            )

            with self.assertRaisesRegex(SourceDiversityError, "is missing"):
                build_report(root)

    def test_invalid_json_has_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            relative = "data/2026/08/2026-08-11.json"
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{not-json", encoding="utf-8")
            self.write_index(
                root, [{"date": "2026-08-11", "data_path": relative}]
            )

            with self.assertRaisesRegex(SourceDiversityError, "invalid JSON"):
                build_report(root)

    def test_invalid_source_url_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_path = self.write_daily(
                root,
                "2026-08-11",
                [
                    {
                        "id": "bad-source",
                        "title": "Bad source",
                        "sources": [self.source("Example", "not-a-url")],
                    }
                ],
            )
            self.write_index(
                root, [{"date": "2026-08-11", "data_path": data_path}]
            )

            with self.assertRaisesRegex(SourceDiversityError, "HTTP\(S\) URL"):
                build_report(root)

    def test_generation_is_byte_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_path = self.write_daily(
                root,
                "2026-08-11",
                [
                    {
                        "id": "stable-event",
                        "title": "Stable event",
                        "regions": ["Asia", "Global"],
                        "sources": [
                            self.source("Example", "https://example.org/stable")
                        ],
                    }
                ],
            )
            self.write_index(
                root, [{"date": "2026-08-11", "data_path": data_path}]
            )

            first = render_report(build_report(root))
            output = write_report(root, Path("labs/source-diversity/data.json"))
            second = output.read_text(encoding="utf-8")
            output = write_report(root, Path("labs/source-diversity/data.json"))

            self.assertEqual(first, second)
            self.assertEqual(second, output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
