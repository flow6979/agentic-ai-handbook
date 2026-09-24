# Vector Store Persistence: kaise chalayein, test karein, tinker karein

Setup: repo root se `source .venv/bin/activate && pip install -e ".[all]"`.
Default DB file: `04-rag/04-vector-store-persistence/rag.sqlite3` (gitignored). `--db` se badal sakte ho.

## 1. Ingest do baar (incremental dekhna)
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
python $P ask "How long do UPI refunds take?" --offline      # nakli LLM
python $P ask "How long do UPI refunds take?"                # real LLM (.env)
python $P stats
```

## 3. Update + delete sync dekhna
```bash
echo -e "\n\nWe now also ship to Nepal and Bhutan." >> 04-rag/04-vector-store-persistence/data/shipping.md
python $P ingest          # updated=['shipping.md']
python $P search "ship to Nepal"
git checkout 04-rag/04-vector-store-persistence/data/shipping.md   # wapas
```

## 4. DB ke andar jhaanko
```bash
sqlite3 04-rag/04-vector-store-persistence/rag.sqlite3 \
  "SELECT doc_id, substr(content_hash,1,12), chunk_count FROM documents;" \
  "SELECT id, length(embedding) FROM chunks LIMIT 3;"      # 2048 bytes = 512 float32
```

## 5. Offline tests
```bash
pytest 04-rag/04-vector-store-persistence -v
```
| Test | Kya prove karta hai |
|---|---|
| `test_blob_roundtrip` | float32 BLOB encode/decode |
| `test_incremental_ingest_add_skip_update_delete` | 2nd ingest pe 0 embeddings; update + delete sync; chunks cascade |
| `test_persists_across_connections` | naya connection = same data (restart simulation) |
| `test_filter_by_doc` | SQL WHERE filter |
| `test_embedder_mismatch_refused` | alag dim ka embedder → error |

## Tinker karo
1. **Embedder switch**: `EMBED_MODEL=ollama:nomic-embed-text python $P ingest` same DB pe chalao. Error padho, phir `--db new.sqlite3` se re-index karo.
2. **Chunk-level hashing**: `chunks` table mein `chunk_hash` column jodo aur `upsert_document` mein sirf badle chunks re-embed karo. Ek lamba doc banao aur ek line badal ke embed count compare karo.
3. **Scale test**: 20,000 fake chunks insert karo (random text) aur `search` ka time naapo (`time.perf_counter`). Kab slow lagne laga?
4. **Metadata column**: `category` ko alag column banao aur `search(category=...)` SQL filter add karo.
5. **JSON vs BLOB**: embeddings JSON text mein store karke DB file size compare karo.
6. **Real DB**: `pip install chromadb` karke same `data/` ko Chroma collection mein daalo; API compare karo is file se.
