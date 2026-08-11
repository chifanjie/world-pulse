from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = Path("labs/source-diversity/data.json")


class SourceDiversityError(ValueError):
    """Raised when source-diversity input cannot be audited safely."""


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SourceDiversityError(f"{label} is missing: {path}") from exc
    except OSError as exc:
        raise SourceDiversityError(f"cannot read {label}: {path}: {exc}") from exc

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceDiversityError(
            f"{label} is invalid JSON: {path}:{exc.lineno}:{exc.colno}"
        ) from exc
    if not isinstance(payload, dict):
        raise SourceDiversityError(f"{label} must contain a JSON object: {path}")
    return payload


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceDiversityError(f"{label} must be a non-empty string")
    return value.strip()


def _optional_text(value: Any, fallback: str = "") -> str:
    if not isinstance(value, str):
        return fallback
    return value.strip() or fallback


def _parse_date(value: Any, label: str) -> str:
    raw = _required_text(value, label)
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise SourceDiversityError(f"{label} must be an ISO date: {raw}") from exc


def _resolve_inside(root: Path, relative: Any, label: str) -> Path:
    raw = _required_text(relative, label)
    candidate = (root / raw).resolve()
    resolved_root = root.resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise SourceDiversityError(f"{label} escapes the repository root: {raw}") from exc
    return candidate


def _canonical_url(raw: Any, label: str) -> tuple[str, str]:
    url = _required_text(raw, label)
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise SourceDiversityError(f"{label} must be an HTTP(S) URL: {url}")

    path = parsed.path
    if path not in {"", "/"}:
        path = path.rstrip("/")
    normalized = urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, "")
    )
    return normalized, url


def _dedupe_text(values: Any, fallback: str) -> list[str]:
    if values is None:
        return [fallback]
    if not isinstance(values, list):
        raise SourceDiversityError("item.regions must be a list when present")
    cleaned = {
        value.strip()
        for value in values
        if isinstance(value, str) and value.strip()
    }
    return sorted(cleaned or {fallback}, key=lambda value: (value.casefold(), value))


def _normalize_sources(sources: Any, item_label: str) -> list[dict[str, str]]:
    if sources is None:
        return []
    if not isinstance(sources, list):
        raise SourceDiversityError(f"{item_label}.sources must be a list")

    unique: dict[str, dict[str, str]] = {}
    for position, source in enumerate(sources):
        label = f"{item_label}.sources[{position}]"
        if not isinstance(source, dict):
            raise SourceDiversityError(f"{label} must be an object")
        canonical, display_url = _canonical_url(source.get("url"), f"{label}.url")
        candidate = {
            "publisher": _optional_text(
                source.get("publisher"), "Unknown publisher"
            ),
            "title": _optional_text(source.get("title"), "Untitled source"),
            "url": display_url,
            "source_type": _optional_text(
                source.get("source_type"), "unspecified"
            ),
            "published_at": _optional_text(source.get("published_at")),
        }
        # A URL represents one auditable source link per event. If malformed input
        # repeats it with conflicting metadata, a stable lexical choice prevents
        # source order from changing the generated report.
        previous = unique.get(canonical)
        if previous is None or tuple(candidate.values()) < tuple(previous.values()):
            unique[canonical] = candidate

    return sorted(
        unique.values(),
        key=lambda source: (
            source["publisher"].casefold(),
            source["source_type"].casefold(),
            source["url"],
        ),
    )


def _normalize_event(item: Any, digest_date: str, position: int) -> dict[str, Any]:
    label = f"{digest_date}.items[{position}]"
    if not isinstance(item, dict):
        raise SourceDiversityError(f"{label} must be an object")

    event_id = _required_text(item.get("id"), f"{label}.id")
    title = _required_text(item.get("title"), f"{label}.title")
    section = "ai" if item.get("section") == "ai-frontier" else "world"
    sources = _normalize_sources(item.get("sources"), label)
    return {
        "date": digest_date,
        "id": event_id,
        "section": section,
        "category": _optional_text(item.get("category"), "uncategorized"),
        "title": title,
        "regions": _dedupe_text(item.get("regions"), "Unspecified"),
        "confidence": _optional_text(item.get("confidence"), "unspecified"),
        "source_count": len(sources),
        "single_source": len(sources) == 1,
        "sources": sources,
    }


def _ranked_counts(
    counts: Counter[str], event_sets: dict[str, set[str]] | None = None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, count in counts.items():
        row: dict[str, Any] = {"name": name, "source_links": count}
        if event_sets is not None:
            row["event_count"] = len(event_sets[name])
        rows.append(row)
    return sorted(
        rows,
        key=lambda row: (-row["source_links"], row["name"].casefold(), row["name"]),
    )


def _ranked_regions(counts: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"name": name, "event_count": count}
        for name, count in sorted(
            counts.items(), key=lambda pair: (-pair[1], pair[0].casefold(), pair[0])
        )
    ]


def _daily_rows(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_date[event["date"]].append(event)
    rows = []
    for digest_date in sorted(by_date, reverse=True):
        daily = by_date[digest_date]
        rows.append(
            {
                "date": digest_date,
                "event_count": len(daily),
                "world_event_count": sum(
                    event["section"] == "world" for event in daily
                ),
                "ai_event_count": sum(event["section"] == "ai" for event in daily),
                "source_links": sum(event["source_count"] for event in daily),
                "single_source_events": sum(event["single_source"] for event in daily),
            }
        )
    return rows


def build_report(root: Path = REPO_ROOT) -> dict[str, Any]:
    root = root.resolve()
    index = _read_json(root / "data" / "index.json", "data index")
    entries = index.get("entries")
    if not isinstance(entries, list):
        raise SourceDiversityError("data index entries must be a list")

    normalized_entries: list[tuple[str, Path]] = []
    seen_paths: set[Path] = set()
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SourceDiversityError(f"data index entries[{position}] must be an object")
        digest_date = _parse_date(entry.get("date"), f"entries[{position}].date")
        data_path = _resolve_inside(
            root, entry.get("data_path"), f"entries[{position}].data_path"
        )
        if data_path in seen_paths:
            continue
        seen_paths.add(data_path)
        normalized_entries.append((digest_date, data_path))
    normalized_entries.sort(key=lambda entry: (entry[0], entry[1].as_posix()))

    events_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    latest_generated_at = ""
    for index_date, data_path in normalized_entries:
        daily = _read_json(data_path, f"daily data for {index_date}")
        digest_date = _parse_date(daily.get("date"), f"{data_path}.date")
        if digest_date != index_date:
            raise SourceDiversityError(
                f"data index date {index_date} does not match {data_path}: {digest_date}"
            )
        generated_at = _optional_text(daily.get("generated_at"))
        latest_generated_at = max(latest_generated_at, generated_at)
        items = daily.get("items")
        if not isinstance(items, list):
            raise SourceDiversityError(f"{data_path}.items must be a list")
        for position, item in enumerate(items):
            event = _normalize_event(item, digest_date, position)
            key = (digest_date, event["id"])
            if key in events_by_key:
                raise SourceDiversityError(
                    f"duplicate event id within {digest_date}: {event['id']}"
                )
            events_by_key[key] = event

    events = sorted(
        events_by_key.values(),
        key=lambda event: (
            -date.fromisoformat(event["date"]).toordinal(),
            event["section"],
            event["id"],
        ),
    )

    region_counts: Counter[str] = Counter()
    publisher_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    publisher_events: dict[str, set[str]] = defaultdict(set)
    type_events: dict[str, set[str]] = defaultdict(set)
    unique_source_urls: set[str] = set()

    for event in events:
        event_key = f"{event['date']}:{event['id']}"
        region_counts.update(event["regions"])
        for source in event["sources"]:
            publisher = source["publisher"]
            source_type = source["source_type"]
            publisher_counts[publisher] += 1
            type_counts[source_type] += 1
            publisher_events[publisher].add(event_key)
            type_events[source_type].add(event_key)
            canonical, _ = _canonical_url(source["url"], "normalized source URL")
            unique_source_urls.add(canonical)

    dates = _daily_rows(events)
    start_date = min((event["date"] for event in events), default=None)
    end_date = max((event["date"] for event in events), default=None)
    source_links = sum(event["source_count"] for event in events)

    return {
        "schema_version": 1,
        "built_from": "data/index.json",
        "latest_digest_generated_at": latest_generated_at or None,
        "date_range": {"start": start_date, "end": end_date},
        "counts": {
            "digests": len(normalized_entries),
            "events": len(events),
            "world_events": sum(event["section"] == "world" for event in events),
            "ai_events": sum(event["section"] == "ai" for event in events),
            "source_links": source_links,
            "unique_source_urls": len(unique_source_urls),
            "single_source_events": sum(event["single_source"] for event in events),
            "zero_source_events": sum(event["source_count"] == 0 for event in events),
        },
        "dates": dates,
        "regions": _ranked_regions(region_counts),
        "publishers": _ranked_counts(publisher_counts, publisher_events),
        "source_types": _ranked_counts(type_counts, type_events),
        "events": events,
    }


def render_report(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_report(root: Path = REPO_ROOT, output: Path = DEFAULT_OUTPUT) -> Path:
    root = root.resolve()
    destination = output if output.is_absolute() else root / output
    destination = destination.resolve()
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise SourceDiversityError(
            f"output escapes the repository root: {destination}"
        ) from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_report(build_report(root)), encoding="utf-8")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the deterministic World Pulse source-diversity dataset."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="World Pulse repository root (defaults to the current checkout).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output path, relative to the repository root by default.",
    )
    args = parser.parse_args()
    try:
        destination = write_report(args.root, args.output)
    except SourceDiversityError as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"Wrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
