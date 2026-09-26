**Language:** [Hinglish](TESTING.md) · English

# Vector Store Persistence: how to run, test and tinker

Setup: from the repo root, `source .venv/bin/activate && pip install -e ".[all]"`.
Default DB file: `04-rag/04-vector-store-persistence/rag.sqlite3` (gitignored). You can change it with `--db`.

## 1. Ingest twice (to see incremental ingestion)
```bash
P=04-rag/04-vector-store-persistence/main.py
python $P ingest
# added=['nimbus_plus.md', ...] ... chunks_embedded=8
python $P ingest
# added=[] updated=[] deleted=[] unchanged=5 chunks_embedded=0     ◄── 0 embeddings!
```

## 2. Search / ask
```bash
python $P search "express shipping cost"
python $P ask "How long do UPI refunds take?" --offline      # fake LLM
python $P ask "How long do UPI refunds take?"                # real LLM (.env)
python $P stats
```

## 3. See update + delete sync
```bash
echo -e "\n\nWe now also ship to Nepal and Bhutan." >> 04-rag/04-vector-store-persistence/data/shipping.md
python $P ingest          # updated=['shipping.md']
python $P search "ship to Nepal"
git checkout 04-rag/04-vector-store-persistence/data/shipping.md   # revert
```

## 4. Peek inside the DB
```bash
sqlite3 04-rag/04-vector-store-persistence/rag.sqlite3 \
  "SELECT doc_id, substr(content_hash,1,12), chunk_count FROM documents;" \
  "SELECT id, length(embedding) FROM chunks LIMIT 3;"      # 2048 bytes = 512 float32
```

## 5. Offline tests
```bash
pytest 04-rag/04-vector-store-persistence -v
```
| Test | What it proves |
|---|---|
| `test_blob_roundtrip` | float32 BLOB encode/decode |
| `test_incremental_ingest_add_skip_update_delete` | 0 embeddings on the 2nd ingest; update + delete sync; chunks cascade |
| `test_persists_across_connections` | new connection = same data (restart simulation) |
| `test_filter_by_doc` | SQL WHERE filter |
| `test_embedder_mismatch_refused` | embedder with a different dim → error |

## Tinker with it
1. **Switch embedder**: run `EMBED_MODEL=ollama:nomic-embed-text python $P ingest` on the same DB. Read the error, then re-index with `--db new.sqlite3`.
2. **Chunk-level hashing**: add a `chunk_hash` column to the `chunks` table and re-embed only changed chunks in `upsert_document`. Create a long doc, change one line and compare the embed count.
3. **Scale test**: insert 20,000 fake chunks (random text) and measure `search` time (`time.perf_counter`). When did it start to feel slow?
4. **Metadata column**: make `category` a separate column and add a `search(category=...)` SQL filter.
5. **JSON vs BLOB**: store embeddings as JSON text and compare the DB file size.
6. **Real DB**: `pip install chromadb`, put the same `data/` into a Chroma collection and compare its API with this file.
