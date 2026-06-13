import json
import os
import time
from pathlib import Path
from typing import List

from config import SESSION_DIR


def _ensure_dir():
    os.makedirs(SESSION_DIR, exist_ok=True)


def save_session(thread_id: str, summary: str, source: str = "", last_state: dict = None):
    _ensure_dir()
    path = os.path.join(SESSION_DIR, f"{thread_id}.json")
    data = {
        "thread_id": thread_id,
        "summary": summary,
        "source": source,
        "updated_at": time.time(),
    }
    if last_state:
        data["last_state"] = last_state
    else:
        try:
            existing = json.loads(Path(path).read_text(encoding="utf-8"))
            data["source"] = source or existing.get("source", "")
            data["last_state"] = existing.get("last_state", {})
        except Exception:
            pass
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def list_sessions(limit: int = 10) -> List[dict]:
    _ensure_dir()
    files = sorted(Path(SESSION_DIR).iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    results = []
    for f in files:
        if f.suffix != ".json":
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            results.append(data)
        except Exception:
            continue
    return results[:limit]


def search_sessions(query: str, limit: int = 5) -> List[dict]:
    results = []
    for f in Path(SESSION_DIR).glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            summary = data.get("summary", "")
            if query.lower() in summary.lower():
                results.append(data)
        except Exception:
            continue
    results.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
    return results[:limit]
