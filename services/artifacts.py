# services/artifacts.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

ART_DIR = Path("sessions_artifacts")


def session_dir(session_id: str) -> Path:
    """
    Return artifact directory for a session. Always creates the folder.
    """
    if not session_id or not str(session_id).strip():
        raise ValueError("session_id is required")
    d = ART_DIR / str(session_id).strip()
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_manifest(session_id: str, data: Dict[str, Any], filename: str = "sections_manifest.json") -> str:
    """
    Writes a JSON manifest into the session artifact directory.

    This is the ONLY artifact we persist for CI now (no normalized.xlsx).
    """
    if not isinstance(data, dict):
        raise ValueError("data must be a dict")

    p = session_dir(session_id) / filename
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(p)


def read_manifest(session_id: str, filename: str = "sections_manifest.json") -> Optional[Dict[str, Any]]:
    """
    Convenience helper: read manifest back (returns None if missing).
    """
    p = session_dir(session_id) / filename
    if not p.exists():
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)
