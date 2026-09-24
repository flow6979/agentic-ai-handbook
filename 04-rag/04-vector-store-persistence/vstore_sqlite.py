"""Persistent vector store on SQLite + incremental ingestion.

Tables:
  meta(key, value)                       embedder name + dimension (mismatch pe error)
  documents(doc_id, content_hash, ...)   har source file ka hash: badla ya nahi?
  chunks(id, doc_id, text, embedding)    embedding = float32 BLOB

Search = brute force (saare vectors load karke cosine). Chhote/medium data ke liye theek;
bade data ke liye ANN index (HNSW) wala DB chahiye. CONCEPTS.md dekho.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from array import array
from dataclasses import dataclass, field
from pathlib import Path

from agentkit import Embedder, cosine

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    chunk_count INTEGER NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    text TEXT NOT NULL,
    metadata TEXT NOT NULL,
    embedding BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
"""


def to_blob(vec: list[float]) -> bytes:
    """float32 bytes: JSON se ~4x chhota aur parse karne mein fast."""
    return array("f", vec).tobytes()


def from_blob(blob: bytes) -> list[float]:
    a = array("f")
    a.frombytes(blob)
    return a.tolist()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_paragraphs(text: str, size: int = 500) -> list[str]:
    """Simple chunker: paragraphs jodo jab tak size na ho (project 01 mein detailed chunkers hain)."""
    chunks, buf = [], ""
    for para in [p.strip() for p in text.split("\n\n") if p.strip()]:
        if buf and len(buf) + len(para) + 2 > size:
            chunks.append(buf)
            buf = para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf:
        chunks.append(buf)
    return chunks


@dataclass
class IngestReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    chunks_embedded: int = 0

    def __str__(self) -> str:
        return (f"added={self.added} updated={self.updated} deleted={self.deleted} "
                f"unchanged={len(self.unchanged)} chunks_embedded={self.chunks_embedded}")


@dataclass
class Hit:
    id: str
    doc_id: str
    text: str
    score: float
    metadata: dict


class SQLiteVectorStore:
    def __init__(self, path: str | Path, embedder: Embedder, embedder_name: str = "local"):
        self.path = str(path)
        self.embedder = embedder
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self._check_embedder(embedder_name)

    def _check_embedder(self, name: str) -> None:
        """Alag embedder ke vectors mix mat karo: dimensions/space alag hote hain, search garbage ho jayega."""
        dim = len(self.embedder.embed_one("dimension probe"))
        row = dict(self.db.execute("SELECT key, value FROM meta").fetchall())
        if not row:
            self.db.executemany("INSERT INTO meta VALUES (?, ?)", [("embedder", name), ("dim", str(dim))])
            self.db.commit()
        elif row["embedder"] != name or int(row["dim"]) != dim:
            raise ValueError(
                f"DB was built with embedder={row['embedder']} dim={row['dim']}, now {name} dim={dim}. "
                "Re-index into a new DB (delete the file) instead of mixing vectors."
            )

    # -------------------------------------------------------- ingestion
    def upsert_document(self, doc_id: str, text: str, metadata: dict | None = None) -> str:
        """Returns 'added' | 'updated' | 'unchanged'. Hash same hai to embed hi nahi karte (paise bache)."""
        h = content_hash(text)
        row = self.db.execute("SELECT content_hash FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
        if row and row[0] == h:
            return "unchanged"
        chunks = split_paragraphs(text)
        vectors = self.embedder.embed(chunks) if chunks else []
        with self.db:  # transaction: aadha-adhoora update kabhi nahi dikhega
            self.db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            self.db.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?) ON CONFLICT(doc_id) DO UPDATE SET "
                "content_hash=excluded.content_hash, chunk_count=excluded.chunk_count, updated_at=excluded.updated_at",
                (doc_id, h, len(chunks), time.time()),
            )
            self.db.executemany(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
                [(f"{doc_id}#{i}", doc_id, i, c, json.dumps(metadata or {}), to_blob(v))
                 for i, (c, v) in enumerate(zip(chunks, vectors))],
            )
        self._last_embedded = len(chunks)
        return "updated" if row else "added"

    def delete_document(self, doc_id: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))  # chunks CASCADE se

    def ingest_folder(self, folder: str | Path, exts: tuple[str, ...] = (".md", ".txt")) -> IngestReport:
        """Folder ko DB se sync karo: naye add, badle update, hataaye delete, baaki skip."""
        rep = IngestReport()
        seen = set()
        for p in sorted(Path(folder).iterdir()):
            if p.suffix.lower() not in exts:
                continue
            seen.add(p.name)
            self._last_embedded = 0
            status = self.upsert_document(p.name, p.read_text(encoding="utf-8"), {"path": str(p)})
            getattr(rep, status).append(p.name)
            rep.chunks_embedded += self._last_embedded
        existing = {r[0] for r in self.db.execute("SELECT doc_id FROM documents")}
        for gone in sorted(existing - seen):
            self.delete_document(gone)
            rep.deleted.append(gone)
        return rep

    # -------------------------------------------------------- query
    def search(self, query: str, k: int = 4, doc_id: str | None = None) -> list[Hit]:
        q = self.embedder.embed_one(query)
        sql, params = "SELECT id, doc_id, text, metadata, embedding FROM chunks", ()
        if doc_id:  # metadata filter SQL mein hi: kam rows load
            sql, params = sql + " WHERE doc_id = ?", (doc_id,)
        hits = [Hit(i, d, t, cosine(q, from_blob(e)), json.loads(m)) for i, d, t, m, e in self.db.execute(sql, params)]
        return sorted(hits, key=lambda h: h.score, reverse=True)[:k]

    def stats(self) -> dict:
        docs = self.db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        chunks = self.db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        meta = dict(self.db.execute("SELECT key, value FROM meta").fetchall())
        return {"documents": docs, "chunks": chunks, **meta, "file": self.path}

    def close(self) -> None:
        self.db.close()
