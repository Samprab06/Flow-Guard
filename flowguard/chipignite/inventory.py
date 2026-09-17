"""Inventory local corpus paths without requiring a checkout or network."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


def inventory_path(root: str | Path, *, extensions: Iterable[str] = (".v", ".sv", ".vh", ".json")) -> dict[str, Any]:
    root = Path(root)
    allowed = {x.lower() for x in extensions}
    files = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in allowed):
        data = path.read_bytes()
        files.append({"path": str(path.relative_to(root)), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return {"root": str(root), "file_count": len(files), "files": files}


def write_inventory(root: str | Path, output: str | Path) -> dict[str, Any]:
    value = inventory_path(root)
    Path(output).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value
