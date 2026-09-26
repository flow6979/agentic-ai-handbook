**Language:** [Hinglish](TESTING.md) · English

# PDF Chat: how to run, test and tinker

Setup (from the repo root): `source .venv/bin/activate && pip install -e ".[all]"`, set the LLM in `.env`.
Run all commands from the `04-rag/02-pdf-chat/` folder (or give the full path).

## 1. Build / inspect the sample PDF
```bash
cd 04-rag/02-pdf-chat
python make_sample_pdf.py               # rebuilds data/nimbuskart_handbook.pdf (4 pages)
python -c "from pypdf import PdfReader; print(PdfReader('data/nimbuskart_handbook.pdf').pages[2].extract_text())"
```

## 2. Offline chat (no key)
```bash
printf 'How many paid leave days do I get?\nand sick leave?\n\n' | python main.py chat --offline -v
```
Expected (roughly):
```
you> Every employee gets 24 days of paid leave per calendar year, credited at 2 days per month. [p.2]
you>   (standalone query: sick leave?)
Sick leave is separate: 12 days per year. [p.2]
```
The `(standalone query: ...)` line tells you the condense step ran.

## 3. Real LLM
```bash
python main.py ask data/nimbuskart_handbook.pdf "Can I carry forward unused leave?" -v
python main.py chat                     # interactive
python main.py ask ~/Downloads/koi.pdf "What is this document about?"
```
Try this in chat: "What is the parental leave?" → "what about the other parent?" → look at the standalone query.

## 4. Offline tests
```bash
pytest 04-rag/02-pdf-chat -v
```
| Test | What it proves |
|---|---|
| `test_load_pdf_pages_and_cleanup` | 4 pages, footer removed, hyphen joined |
| `test_chunks_keep_page_numbers` | each chunk's page + id format |
| `test_scanned_pdf_detected` | the "OCR" error on a text-less PDF |
| `test_condense_skipped_without_history` | no extra LLM call on the first question |
| `test_answer_cites_page_and_followup_is_condensed` | [p.N] citations, follow-up rewrite, history |

## What to look for
- With `-v`, the pages of the retrieved chunks. Is the answer's `[p.N]` one of them?
- Is the standalone query for the follow-up sensible? What does a real LLM write vs the offline fake?
- The table question ("hotel cap in non-metro cities?"): did the LLM read the right column?

## Tinker with it
1. **Turn off condensing**: make `condense_question` just `return question`. What does "what about the other parent?" retrieve now?
2. **Chunk size**: set `chunk_pages(size=150)`. Did the table row and header land in different chunks? Did the answer get worse?
3. **Simulate a scanned PDF**: in `make_sample_pdf.py`, make one page's lines an empty list and look at the `empty_pages` report.
4. **Tables as sentences**: in `PAGES`, write the table rows as "Hotel per night: metro 6000 rupees, non-metro 3500 rupees", rebuild the PDF and compare the non-metro question.
5. **History length**: set `max_turns=1` and run a chain of 3-4 follow-ups. When does it forget the context?
6. **Multiple PDFs**: call `PDFIndex.add_pdf()` twice (two different PDFs) and add the file name to the citation (`[handbook.pdf p.3]`).
