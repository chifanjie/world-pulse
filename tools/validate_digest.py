#!/usr/bin/env python3
"""Validate World Pulse JSON files and their linked Markdown digests."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_CATEGORIES = {
    "politics",
    "economy",
    "markets",
    "technology",
    "science",
    "climate-environment",
    "health-society",
    "culture",
}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}
ALLOWED_SOURCE_TYPES = {"primary", "wire", "regional-media", "research"}


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_web_url(value: Any) -> bool:
    if not _nonempty_string(value):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _load_json(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, [f"cannot read valid UTF-8 JSON: {exc}"]
    if not isinstance(data, dict):
        return None, ["top-level JSON value must be an object"]
    return data, []


def validate_file(path: Path, root: Path = ROOT) -> list[str]:
    """Return human-readable validation errors for one data file."""
    path = path.resolve()
    root = root.resolve()
    data, errors = _load_json(path)
    if data is None:
        return errors

    date_value = data.get("date")
    if not _nonempty_string(date_value):
        errors.append("date must be a non-empty YYYY-MM-DD string")
    else:
        try:
            parsed_date = datetime.strptime(date_value, "%Y-%m-%d").date()
        except ValueError:
            errors.append("date must use YYYY-MM-DD and be a real calendar date")
        else:
            expected_name = f"{parsed_date.isoformat()}.json"
            if path.name != expected_name:
                errors.append(f"filename must match date: expected {expected_name}")

    if data.get("timezone") != "Asia/Shanghai":
        errors.append("timezone must be Asia/Shanghai")

    generated_at = data.get("generated_at")
    if not _nonempty_string(generated_at):
        errors.append("generated_at must be an ISO 8601 timestamp")
    else:
        try:
            timestamp = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                errors.append("generated_at must include a timezone offset")
        except ValueError:
            errors.append("generated_at must be a valid ISO 8601 timestamp")

    overview = data.get("overview")
    if not _nonempty_string(overview):
        errors.append("overview must be a non-empty string")

    digest_path_value = data.get("digest_path")
    digest_text = ""
    digest_path: Path | None = None
    if not _nonempty_string(digest_path_value):
        errors.append("digest_path must be a repository-relative path")
    else:
        digest_path = (root / digest_path_value).resolve()
        try:
            digest_path.relative_to(root)
        except ValueError:
            errors.append("digest_path must stay inside the repository")
            digest_path = None
        if digest_path is not None:
            if not digest_path.is_file():
                errors.append(f"linked digest does not exist: {digest_path_value}")
            else:
                try:
                    digest_text = digest_path.read_text(encoding="utf-8")
                except (OSError, UnicodeError) as exc:
                    errors.append(f"cannot read linked digest: {exc}")

    items = data.get("items")
    if not isinstance(items, list) or not items:
        errors.append("items must be a non-empty array")
        return errors
    if len(items) < 5:
        errors.append("items should contain at least five independently sourced events")

    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        prefix = f"items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue

        event_id = item.get("id")
        if not _nonempty_string(event_id):
            errors.append(f"{prefix}.id must be a non-empty string")
        elif event_id in seen_ids:
            errors.append(f"{prefix}.id is duplicated: {event_id}")
        else:
            seen_ids.add(event_id)
            if digest_text and f"<!-- event:{event_id} -->" not in digest_text:
                errors.append(f"digest is missing marker for event {event_id}")

        category = item.get("category")
        if category not in ALLOWED_CATEGORIES:
            errors.append(f"{prefix}.category is not allowed: {category!r}")

        regions = item.get("regions")
        if not isinstance(regions, list) or not regions or not all(
            _nonempty_string(region) for region in regions
        ):
            errors.append(f"{prefix}.regions must be a non-empty string array")

        for field in ("title", "summary", "why_it_matters", "uncertainty"):
            if not _nonempty_string(item.get(field)):
                errors.append(f"{prefix}.{field} must be a non-empty string")

        if item.get("confidence") not in ALLOWED_CONFIDENCE:
            errors.append(f"{prefix}.confidence must be high, medium, or low")

        sources = item.get("sources")
        if not isinstance(sources, list) or not sources:
            errors.append(f"{prefix}.sources must be a non-empty array")
            continue
        for source_index, source in enumerate(sources):
            source_prefix = f"{prefix}.sources[{source_index}]"
            if not isinstance(source, dict):
                errors.append(f"{source_prefix} must be an object")
                continue
            for field in ("publisher", "title", "published_at"):
                if not _nonempty_string(source.get(field)):
                    errors.append(f"{source_prefix}.{field} must be a non-empty string")
            url = source.get("url")
            if not _is_web_url(url):
                errors.append(f"{source_prefix}.url must be an HTTP(S) URL")
            elif digest_text and url not in digest_text:
                errors.append(f"digest is missing source URL for {event_id}")
            if source.get("source_type") not in ALLOWED_SOURCE_TYPES:
                errors.append(
                    f"{source_prefix}.source_type must be one of "
                    f"{sorted(ALLOWED_SOURCE_TYPES)}"
                )

    return errors


def default_files(root: Path = ROOT) -> list[Path]:
    return sorted(
        path
        for path in (root / "data").glob("*/*/*.json")
        if path.name != "index.json"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="JSON files to validate")
    args = parser.parse_args(argv)
    files = args.files or default_files()
    if not files:
        print("No daily data files found.", file=sys.stderr)
        return 2

    failed = False
    for path in files:
        errors = validate_file(path)
        if errors:
            failed = True
            print(f"FAIL {path}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"OK   {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
