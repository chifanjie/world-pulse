import json
import tempfile
import unittest
from pathlib import Path

from labs.digest_search.digest_search import collect_paths, search_digests


class DigestSearchTests(unittest.TestCase):
    def write_daily(self, root: Path, day: str, items: list[dict]) -> Path:
        path = root / f"{day}.json"
        path.write_text(json.dumps({"date": day, "items": items}), encoding="utf-8")
        return path

    def test_combines_phrase_date_category_region_and_section_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = self.write_daily(
                root,
                "2026-09-25",
                [
                    {
                        "id": "canada-retail",
                        "title": "加拿大零售数据",
                        "summary": "七月销量回落",
                        "category": "economy",
                        "regions": ["Canada", "North America"],
                        "sources": [{"publisher": "Statistics Canada", "url": "https://example.test/source"}],
                    },
                    {
                        "id": "ai-test",
                        "title": "代理部署评测",
                        "summary": "容器化测试",
                        "category": "technology",
                        "regions": ["Global"],
                        "section": "ai-frontier",
                    },
                ],
            )
            result = search_digests(
                [path], queries=["加拿大", "销量"], category="ECONOMY", region="canada",
                section="world", since="2026-09-25", through="2026-09-25",
            )
            self.assertEqual(result["matched_count"], 1)
            self.assertEqual(result["entries"][0]["id"], "canada-retail")
            self.assertEqual(result["entries"][0]["sources"][0]["publisher"], "Statistics Canada")

    def test_directory_scan_excludes_index_and_results_are_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_daily(root, "2026-09-24", [{"id": "z", "title": "同一主题", "category": "science"}])
            self.write_daily(root, "2026-09-23", [{"id": "b", "title": "同一主题", "category": "science"}])
            (root / "index.json").write_text("not a digest", encoding="utf-8")
            result = search_digests([root, root], queries=["同一", "主题"], limit=1)
            self.assertEqual(result["matched_count"], 2)
            self.assertEqual(result["returned_count"], 1)
            self.assertEqual(result["entries"][0]["id"], "b")
            self.assertEqual(collect_paths([root]), sorted(collect_paths([root])))

    def test_invalid_json_fields_dates_and_limits_are_not_silently_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bad_json = root / "bad.json"
            bad_json.write_text("{", encoding="utf-8")
            with self.assertRaises(ValueError):
                search_digests([bad_json])
            invalid_day = self.write_daily(root, "2026-09-25", [{"id": "x", "title": "x", "category": "x"}])
            with self.assertRaises(ValueError):
                search_digests([invalid_day], since="2026-09-31")
            with self.assertRaises(ValueError):
                search_digests([invalid_day], limit=0)


if __name__ == "__main__":
    unittest.main()
