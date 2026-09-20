#!/usr/bin/env python3
"""Report missing and late-published digests without inventing content."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHANGHAI = timezone(timedelta(hours=8))


def audit(root: Path, since: date, through: date, *, now: datetime | None = None) -> dict[str, object]:
    if since > through:
        raise ValueError("since must not be after through")
    now = now or datetime.now(SHANGHAI)
    if now.tzinfo is None:
        raise ValueError("now must include timezone")
    present: set[date] = set()
    late: list[str] = []
    errors: list[str] = []
    for path in sorted((root / "data").glob("*/*/*.json")):
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if not since <= day <= through:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("date") != day.isoformat():
                raise ValueError("archive date does not match filename")
            expected_data = f"data/{day:%Y/%m}/{day.isoformat()}.json"
            if path.relative_to(root).as_posix() != expected_data:
                raise ValueError("JSON archive directory does not match date")
            expected_digest = f"digests/{day:%Y/%m}/{day.isoformat()}.md"
            if payload.get("digest_path") != expected_digest:
                raise ValueError("digest_path must point to the same archive day")
            linked = (root / payload["digest_path"]).resolve()
            linked.relative_to(root.resolve())
            if not linked.is_file():
                raise ValueError("linked Markdown is missing")
            generated = datetime.fromisoformat(payload["generated_at"].replace("Z", "+00:00"))
            if generated.tzinfo is None:
                raise ValueError("generated_at must include timezone")
            if generated > now:
                raise ValueError("generated_at is in the future")
            published_day = generated.astimezone(SHANGHAI).date()
            if published_day < day:
                raise ValueError("generated_at predates the archive day")
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            errors.append(f"{path.relative_to(root).as_posix()}: {exc}")
            continue
        present.add(day)
        if published_day > day:
            late.append(day.isoformat())
    expected = [since + timedelta(days=offset) for offset in range((through - since).days + 1)]
    missing = [day.isoformat() for day in expected if day not in present]
    return {
        "status": "attention" if missing or errors else "complete",
        "scope": "local archive only; does not prove a GitHub push",
        "since": since.isoformat(), "through": through.isoformat(),
        "expected_count": len(expected), "present_count": len(present),
        "latest_digest": max(present).isoformat() if present else None,
        "missing_dates": missing, "late_published_dates": late, "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True, type=date.fromisoformat)
    parser.add_argument("--through", type=date.fromisoformat, default=datetime.now(SHANGHAI).date())
    args = parser.parse_args(argv)
    try:
        report = audit(ROOT, args.since, args.through)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["status"] == "attention" else 0


if __name__ == "__main__":
    raise SystemExit(main())
