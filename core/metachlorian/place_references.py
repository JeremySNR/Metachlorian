"""Optional, user-curated current names and visual clues for place recognition."""
from __future__ import annotations

import hashlib
import json


def reference_notes(settings) -> str:
    path = settings.data_dir / "place-references.json"
    if not path.exists():
        return ""
    if path.stat().st_size > 64_000:
        raise ValueError("place-references.json must be at most 64 KB")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise ValueError("place-references.json needs an entries array")
    if len(data["entries"]) > 40:
        raise ValueError("place-references.json supports at most 40 entries")
    keys = ("name", "venue", "destination", "area", "period", "evidence", "source_url")
    entries = []
    for entry in data["entries"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise ValueError("each place reference needs a name")
        entries.append({k: str(entry[k])[:600] for k in keys if entry.get(k)})
    return json.dumps(entries, ensure_ascii=False)


def reference_key(settings) -> str:
    return hashlib.sha256(reference_notes(settings).encode()).hexdigest()
