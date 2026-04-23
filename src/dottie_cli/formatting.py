from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def iso_to_date(value: str | None) -> str:
    if not value:
        return "-"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return value


def iso_to_datetime(value: str | None) -> str:
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M UTC")
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True))


def print_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> None:
    if not rows:
        print("(no rows)")
        return

    widths: list[int] = []
    for key, label in columns:
        cell_width = max(len(str(row.get(key, ""))) for row in rows)
        widths.append(max(len(label), cell_width))

    header = "  ".join(label.ljust(widths[idx]) for idx, (_, label) in enumerate(columns))
    divider = "  ".join("-" * width for width in widths)
    print(header)
    print(divider)
    for row in rows:
        print("  ".join(str(row.get(key, "")).ljust(widths[idx]) for idx, (key, _) in enumerate(columns)))

