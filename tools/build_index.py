#!/usr/bin/env python3
"""Build data/index.json from the daily structured data files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def collect_entries(root: Path = ROOT) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted((root / "data").glob("*/*/*.json"), reverse=True):
        if path.name == "index.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("items", [])
        categories = sorted(
            {item.get("category") for item in items if item.get("category")}
        )
        regions = sorted(
            {
                region
                for item in items
                for region in item.get("regions", [])
                if region
            }
        )
        entries.append(
            {
                "date": data["date"],
                "digest_path": data["digest_path"],
                "data_path": path.relative_to(root).as_posix(),
                "generated_at": data["generated_at"],
                "item_count": len(items),
                "categories": categories,
                "regions": regions,
            }
        )
    entries.sort(key=lambda entry: entry["date"], reverse=True)
    return entries


def write_index(root: Path = ROOT) -> Path:
    output = root / "data" / "index.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "entries": collect_entries(root)}
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    output = write_index(args.root.resolve())
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
