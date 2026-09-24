import shutil
from pathlib import Path

import pytest

from agentkit import get_embedder
from agentkit.embeddings import HashingEmbedder
from vstore_sqlite import SQLiteVectorStore, from_blob, split_paragraphs, to_blob

DATA = Path(__file__).parent / "data"


class CountingEmbedder(HashingEmbedder):
    """Kitne texts embed hue, gin'ta hai: incremental ingestion ko prove karne ke liye."""

    def __init__(self, dim=512):
        super().__init__(dim)
        self.count = 0

    def embed(self, texts):
        self.count += len(texts)
        return super().embed(texts)


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "docs"
    shutil.copytree(DATA, d)
    return d


def test_blob_roundtrip():
    v = [0.5, -1.25, 3.0]
    assert from_blob(to_blob(v)) == v


def test_split_paragraphs_size():
    text = "\n\n".join(["p" * 100] * 10)
    assert all(len(c) <= 500 for c in split_paragraphs(text, 500))


def test_incremental_ingest_add_skip_update_delete(tmp_path, folder):
    emb = CountingEmbedder()
    store = SQLiteVectorStore(tmp_path / "v.db", emb)

    r1 = store.ingest_folder(folder)
    assert len(r1.added) == 5 and r1.chunks_embedded > 0
    first_count = emb.count

    r2 = store.ingest_folder(folder)  # kuch nahi badla
    assert len(r2.unchanged) == 5 and r2.chunks_embedded == 0
    assert emb.count == first_count  # ek bhi text dobara embed nahi hua

    (folder / "shipping.md").write_text("# Shipping\n\nWe now ship to Nepal.")
    (folder / "refund_policy.md").unlink()
    r3 = store.ingest_folder(folder)
    assert r3.updated == ["shipping.md"] and r3.deleted == ["refund_policy.md"]
    assert store.db.execute("SELECT COUNT(*) FROM chunks WHERE doc_id='refund_policy.md'").fetchone()[0] == 0
    assert store.search("ship to Nepal", 1)[0].doc_id == "shipping.md"


def test_persists_across_connections(tmp_path, folder):
    db = tmp_path / "v.db"
    s1 = SQLiteVectorStore(db, get_embedder("local"))
    s1.ingest_folder(folder)
    s1.close()
    s2 = SQLiteVectorStore(db, get_embedder("local"))  # naya process jaisa
    assert s2.stats()["documents"] == 5
    assert s2.search("How long do card refunds take?", 1)[0].doc_id == "refund_policy.md"


def test_filter_by_doc(tmp_path, folder):
    s = SQLiteVectorStore(tmp_path / "v.db", get_embedder("local"))
    s.ingest_folder(folder)
    assert {h.doc_id for h in s.search("refund", 5, doc_id="warranty.md")} == {"warranty.md"}


def test_embedder_mismatch_refused(tmp_path):
    db = tmp_path / "v.db"
    SQLiteVectorStore(db, HashingEmbedder(512), "local").close()
    with pytest.raises(ValueError, match="Re-index"):
        SQLiteVectorStore(db, HashingEmbedder(256), "local")
