#!/usr/bin/env python3
"""Search archived digest events offline and return their source links."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable


def collect_paths(paths: Iterable[str | Path]) -> list[Path]:
    """Expand daily JSON files and directories into a stable, de-duplicated list."""
    found: set[Path] = set()
    for raw_path in paths:
        path = Path(raw_path)
        candidates = path.rglob("*.json") if path.is_dir() else [path]
        for candidate in candidates:
            if candidate.name != "index.json" and candidate.suffix.lower() == ".json":
                found.add(candidate.resolve())
    return sorted(found, key=lambda item: item.as_posix())


def load_records(path: str | Path) -> list[dict[str, Any]]:
    """Load compact searchable records while rejecting malformed archive entries."""
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{source}: cannot read valid UTF-8 JSON: {exc}") from exc

    day = payload.get("date") if isinstance(payload, dict) else None
    items = payload.get("items") if isinstance(payload, dict) else None
    try:
        parsed_day = date.fromisoformat(day)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{source}: date must be YYYY-MM-DD") from exc
    if parsed_day.isoformat() != day:
        raise ValueError(f"{source}: date must be YYYY-MM-DD")
    if not isinstance(items, list):
        raise ValueError(f"{source}: items must be an array")

    records: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source}: every item must be an object")
        required = (item.get("id"), item.get("title"), item.get("category"))
        if not all(isinstance(value, str) and value.strip() for value in required):
            raise ValueError(f"{source}: item is missing id, title, or category")
        regions = item.get("regions", [])
        if not isinstance(regions, list) or not all(
            isinstance(region, str) and region.strip() for region in regions
        ):
            raise ValueError(f"{source}: regions must be a string array")
        sources = item.get("sources", [])
        if not isinstance(sources, list) or any(not isinstance(row, dict) for row in sources):
            raise ValueError(f"{source}: sources must be an array of objects")
        searchable = [item.get(key, "") for key in ("title", "summary", "why_it_matters", "uncertainty")]
        if not all(isinstance(value, str) for value in searchable):
            raise ValueError(f"{source}: searchable text fields must be strings")
        records.append(
            {
                "date": day,
                "id": item["id"],
                "title": item["title"],
                "category": item["category"],
                "regions": sorted(set(regions), key=str.casefold),
                "section": "ai-frontier" if item.get("section") == "ai-frontier" else "world",
                "confidence": item.get("confidence"),
                "sources": [
                    {
                        key: row[key]
                        for key in ("publisher", "title", "url")
                        if isinstance(row.get(key), str)
                    }
                    for row in sources
                ],
                "_search": " ".join(searchable).casefold(),
            }
        )
    return records


def search_digests(
    paths: Iterable[str | Path],
    *,
    queries: Iterable[str] = (),
    category: str | None = None,
    region: str | None = None,
    section: str | None = None,
    since: str | None = None,
    through: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Search event text and metadata; every query phrase must match the event."""
    try:
        start = date.fromisoformat(since) if since else None
        end = date.fromisoformat(through) if through else None
    except ValueError as exc:
        raise ValueError("date filters must use YYYY-MM-DD") from exc
    if since and start.isoformat() != since:
        raise ValueError("--since must use YYYY-MM-DD")
    if through and end.isoformat() != through:
        raise ValueError("--through must use YYYY-MM-DD")
    if start and end and start > end:
        raise ValueError("--since must not be after --through")
    if limit < 1:
        raise ValueError("limit must be at least 1")
    phrases = [query.strip().casefold() for query in queries if query.strip()]

    records = [record for path in collect_paths(paths) for record in load_records(path)]
    matches = []
    for record in records:
        record_day = date.fromisoformat(record["date"])
        if start and record_day < start or end and record_day > end:
            continue
        if category and record["category"].casefold() != category.casefold():
            continue
        if region and not any(region.casefold() == value.casefold() for value in record["regions"]):
            continue
        if section and record["section"] != section:
            continue
        if any(phrase not in record["_search"] for phrase in phrases):
            continue
        matches.append({key: value for key, value in record.items() if key != "_search"})

    matches.sort(key=lambda record: (record["date"], record["id"]))
    total = len(matches)
    entries = matches[:limit]
    return {
        "matched_count": total,
        "returned_count": len(entries),
        "dates": sorted({entry["date"] for entry in entries}),
        "entries": entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="daily JSON files or directories")
    parser.add_argument("--query", action="append", default=[], help="case-insensitive phrase; repeat to require all phrases")
    parser.add_argument("--category", help="exact category, case-insensitive")
    parser.add_argument("--region", help="exact region label, case-insensitive")
    parser.add_argument("--section", choices=("world", "ai-frontier"))
    parser.add_argument("--since", help="inclusive start date (YYYY-MM-DD)")
    parser.add_argument("--through", help="inclusive end date (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=50, help="maximum entries to return (default: 50)")
    args = parser.parse_args(argv)
    try:
        result = search_digests(
            args.paths,
            queries=args.query,
            category=args.category,
            region=args.region,
            section=args.section,
            since=args.since,
            through=args.through,
            limit=args.limit,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
