from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import SessionData

DB_PATH = Path("./session_store.sqlite3")


class SessionStore:
    _instance = None

    @classmethod
    def get_instance(cls, db_path: Path = DB_PATH) -> "SessionStore":
        if cls._instance is None:
            cls._instance = cls(db_path=db_path)
        return cls._instance

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self._init()

    def _init(self) -> None:
        con = sqlite3.connect(self.db_path)
        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                  session_id TEXT PRIMARY KEY,
                  json TEXT NOT NULL,
                  updated_at INTEGER NOT NULL
                )
                """
            )
            con.commit()
        finally:
            con.close()

    @staticmethod
    def _looks_like_owner_key(val: object) -> bool:
        return isinstance(val, str) and (
            val.startswith("user:") or val.startswith("admin:")
        )

    def _normalize_owner_fields_in_dict(self, js: dict) -> dict:
        """Ensure owner_key is present for new switch-mode design.

        Migration rules:
        - If owner_key missing and owner_user_id looks like an owner_key => copy to owner_key
        - If owner_key exists and owner_user_id missing => copy owner_key to owner_user_id (legacy sync)
        """
        try:
            ok = js.get("owner_key")
            ou = js.get("owner_user_id")

            if not ok and self._looks_like_owner_key(ou):
                js["owner_key"] = ou

            if self._looks_like_owner_key(js.get("owner_key")) and not js.get("owner_user_id"):
                js["owner_user_id"] = js["owner_key"]
        except Exception:
            pass
        return js

    def upsert(self, data: SessionData) -> None:
        # SessionData validator already syncs owner_key <-> owner_user_id
        js = data.model_dump(mode="json")
        js = self._normalize_owner_fields_in_dict(js)
        js["updated_at_iso"] = datetime.utcnow().isoformat()

        con = sqlite3.connect(self.db_path)
        try:
            con.execute(
                "REPLACE INTO sessions(session_id, json, updated_at) VALUES (?, ?, ?)",
                (data.session_id, json.dumps(js, ensure_ascii=False), int(time.time())),
            )
            con.commit()
        finally:
            con.close()

    def get(self, session_id: str) -> Optional[SessionData]:
        con = sqlite3.connect(self.db_path)
        try:
            cur = con.execute("SELECT json FROM sessions WHERE session_id=?", (session_id,))
            row = cur.fetchone()
            if not row:
                return None

            js = json.loads(row[0]) if row[0] else {}
            if not isinstance(js, dict):
                return None

            js2 = self._normalize_owner_fields_in_dict(js)
            obj = SessionData(**js2)

            # Auto-heal DB if migration changed something
            try:
                migrated = (js.get("owner_key") != js2.get("owner_key")) or (
                    js.get("owner_user_id") != js2.get("owner_user_id")
                )
                if migrated:
                    self.upsert(obj)
            except Exception:
                pass

            return obj
        finally:
            con.close()

    def update_fields(self, session_id: str, **fields):
        data = self.get(session_id)
        if not data:
            return None
        for k, v in fields.items():
            setattr(data, k, v)
        self.upsert(data)
        return data

    def delete(self, session_id: str) -> None:
        con = sqlite3.connect(self.db_path)
        try:
            con.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
            con.commit()
        finally:
            con.close()

    def cleanup(self, ttl_hours: int = 24) -> None:
        now = int(time.time())
        cutoff = now - ttl_hours * 3600
        con = sqlite3.connect(self.db_path)
        try:
            con.execute("DELETE FROM sessions WHERE updated_at < ?", (cutoff,))
            con.commit()
        finally:
            con.close()
