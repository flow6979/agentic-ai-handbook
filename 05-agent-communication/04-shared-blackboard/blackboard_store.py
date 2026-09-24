"""Blackboard = ek shared 'whiteboard' jispe saare agents padhte aur likhte hain.

Agents ek dusre se seedha baat NAHI karte. Woh sirf board dekhte hain:
"kya yahan kuch hai jo main aage badha sakta hoon?" -> haan to apna hissa likh do.

Do implementations, same interface:
    InMemoryBlackboard  -> dict + threading.Lock (ek process, multi-thread safe)
    SqliteBlackboard    -> SQLite table (process restart ke baad bhi state bachi rehti hai,
                           aur multiple processes ek file share kar sakte hain)
Real duniya mein: Redis hash, Postgres table, ya LangGraph ka shared `state`.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from typing import Any


class Blackboard(ABC):
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any: ...

    @abstractmethod
    def set(self, key: str, value: Any, *, author: str) -> None: ...

    @abstractmethod
    def delete(self, key: str, *, author: str) -> None: ...

    @abstractmethod
    def snapshot(self) -> dict[str, Any]: ...

    @abstractmethod
    def history(self) -> list[dict[str, Any]]:
        """Kisne kab kya likha: audit trail (debugging ke liye sona)."""

    def has(self, *keys: str) -> bool:
        snap = self.snapshot()
        return all(k in snap for k in keys)


class InMemoryBlackboard(Blackboard):
    def __init__(self):
        self._data: dict[str, Any] = {}
        self._log: list[dict[str, Any]] = []
        self._lock = threading.Lock()  # do threads ek saath likhein to data corrupt na ho

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key, value, *, author):
        with self._lock:
            self._data[key] = value
            self._log.append({"ts": time.time(), "op": "set", "key": key, "value": value, "author": author})

    def delete(self, key, *, author):
        with self._lock:
            self._data.pop(key, None)
            self._log.append({"ts": time.time(), "op": "delete", "key": key, "value": None, "author": author})

    def snapshot(self):
        with self._lock:
            return dict(self._data)

    def history(self):
        with self._lock:
            return list(self._log)


class SqliteBlackboard(Blackboard):
    def __init__(self, path: str = ":memory:"):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._conn:
            self._conn.execute("CREATE TABLE IF NOT EXISTS board (key TEXT PRIMARY KEY, value TEXT)")
            self._conn.execute("CREATE TABLE IF NOT EXISTS log (ts REAL, op TEXT, key TEXT, value TEXT, author TEXT)")

    def get(self, key, default=None):
        with self._lock:
            row = self._conn.execute("SELECT value FROM board WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value, *, author):
        v = json.dumps(value)
        with self._lock, self._conn:  # `with conn` = ek transaction
            self._conn.execute("INSERT INTO board VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, v))
            self._conn.execute("INSERT INTO log VALUES(?,?,?,?,?)", (time.time(), "set", key, v, author))

    def delete(self, key, *, author):
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM board WHERE key=?", (key,))
            self._conn.execute("INSERT INTO log VALUES(?,?,?,?,?)", (time.time(), "delete", key, None, author))

    def snapshot(self):
        with self._lock:
            return {k: json.loads(v) for k, v in self._conn.execute("SELECT key, value FROM board")}

    def history(self):
        with self._lock:
            rows = self._conn.execute("SELECT ts, op, key, value, author FROM log ORDER BY rowid").fetchall()
        return [{"ts": ts, "op": op, "key": k, "value": json.loads(v) if v else None, "author": a} for ts, op, k, v, a in rows]
