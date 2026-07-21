from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import JobRecord


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def append_jsonl(path: Path, record: JobRecord) -> None:
    ensure_parent_dir(path)
    with path.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json(ensure_ascii=False))
        f.write("\n")


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, Any]) -> None:
    ensure_parent_dir(path)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

