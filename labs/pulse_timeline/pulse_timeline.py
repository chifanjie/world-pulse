#!/usr/bin/env python3
"""Build a deterministic, category-filterable timeline from daily JSON files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def collect_paths(paths: Iterable[str | Path]) -> list[Path]:
    """Expand files and directories into sorted daily JSON paths."""
    found: set[Path] = set()
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            candidates = path.rglob("*.json")
        else:
            candidates = [path]
        for candidate in candidates:
            if candidate.name != "index.json" and candidate.suffix.lower() == ".json":
                found.add(candidate.resolve())
    return sorted(found, key=lambda item: item.as_posix())


def load_daily(path: str | Path) -> list[dict[str, Any]]:
    """Load one daily file and return compact item records.

    The function intentionally accepts the repository's existing JSON shape and
    ignores optional fields so the timeline remains useful for older digests.
    """
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    date = payload.get("date")
    items = payload.get("items")
    if not isinstance(date, str) or not date:
        raise ValueError(f"{source}: missing date")
    if not isinstance(items, list):
        raise ValueError(f"{source}: items must be an array")

    records: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source}: every item must be an object")
        event_id = item.get("id")
        title = item.get("title")
        category = item.get("category")
        regions = item.get("regions", [])
        if not all(isinstance(value, str) and value for value in (event_id, title, category)):
            raise ValueError(f"{source}: item is missing id, title, or category")
        if not isinstance(regions, list) or not all(isinstance(region, str) for region in regions):
            raise ValueError(f"{source}: regions must be a string array")
        records.append(
            {
                "date": date,
                "id": event_id,
                "title": title,
                "category": category,
                "regions": sorted(regions),
            }
        )
    return records


def build_timeline(paths: Iterable[str | Path], category: str | None = None) -> dict[str, Any]:
    """Return sorted timeline entries and summary metadata."""
    entries = [record for path in collect_paths(paths) for record in load_daily(path)]
    if category:
        entries = [record for record in entries if record["category"] == category]
    entries.sort(key=lambda record: (record["date"], record["id"]))
    dates = sorted({record["date"] for record in entries})
    return {"count": len(entries), "dates": dates, "entries": entries}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="daily JSON files or directories")
    parser.add_argument("--category", help="keep only an exact category")
    args = parser.parse_args(argv)
    payload = build_timeline(args.paths, category=args.category)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
