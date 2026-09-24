"""Long-term memory: sessions ke beech yaad rehna.

  SemanticMemory : FACTS ("user vegetarian hai") → SQLite + embeddings, meaning se search
  EpisodicMemory : EPISODES ("12 Sep ko user ne Goa trip plan kiya") → JSONL log, time-ordered
(Procedural memory = "kaise karna hai" = prompts/instructions/lessons; dekho 06-reflection ka LessonMemory.)
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from agentkit import Embedder, cosine, get_embedder


@dataclass
class FactHit:
    id: int
    text: str
    category: str
    score: float


class SemanticMemory:
    def __init__(self, db_path: str | Path, embedder: Embedder | None = None, dedupe_threshold: float = 0.9):
        self.embedder = embedder or get_embedder("local")
        self.dedupe_threshold = dedupe_threshold
        self.db = sqlite3.connect(str(db_path))
        self.db.execute("""CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, text TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'other', embedding TEXT NOT NULL,
            created_at REAL NOT NULL, updated_at REAL NOT NULL)""")
        self.db.commit()

    def _rows(self, user_id: str) -> list[tuple]:
        return self.db.execute("SELECT id, text, category, embedding FROM facts WHERE user_id = ?", (user_id,)).fetchall()

    def add(self, user_id: str, text: str, category: str = "other") -> int:
        """Naya fact save karo. Lagbhag same fact pehle se hai to update (duplicate mat banao)."""
        vec = self.embedder.embed_one(text)
        now = time.time()
        for fid, _old, _cat, emb in self._rows(user_id):
            if cosine(vec, json.loads(emb)) >= self.dedupe_threshold:
                self.db.execute("UPDATE facts SET text=?, category=?, embedding=?, updated_at=? WHERE id=?",
                                (text, category, json.dumps(vec), now, fid))
                self.db.commit()
                return fid
        cur = self.db.execute(
            "INSERT INTO facts (user_id, text, category, embedding, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (user_id, text, category, json.dumps(vec), now, now))
        self.db.commit()
        return cur.lastrowid

    def search(self, user_id: str, query: str, k: int = 3, min_score: float = 0.05) -> list[FactHit]:
        """Query se sabse relevant facts (cosine similarity). Brute force: chhote data ke liye theek;
        bade scale pe vector DB (dekho 04-rag)."""
        q = self.embedder.embed_one(query)
        hits = [FactHit(fid, text, cat, cosine(q, json.loads(emb))) for fid, text, cat, emb in self._rows(user_id)]
        hits = [h for h in hits if h.score >= min_score]
        return sorted(hits, key=lambda h: h.score, reverse=True)[:k]

    def all(self, user_id: str) -> list[FactHit]:
        return [FactHit(fid, t, c, 1.0) for fid, t, c, _ in self._rows(user_id)]

    def delete(self, fact_id: int) -> None:
        """'Right to be forgotten': user bole 'yeh bhool jao' to delete karna possible hona chahiye."""
        self.db.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        self.db.commit()


class EpisodicMemory:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def log(self, user_id: str, summary: str) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps({"ts": time.time(), "user_id": user_id, "summary": summary}) + "\n")

    def recent(self, user_id: str, n: int = 3) -> list[dict]:
        if not self.path.exists():
            return []
        rows = [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]
        return [r for r in rows if r["user_id"] == user_id][-n:]
