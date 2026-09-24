# PDF Chat: kaise chalayein, test karein, tinker karein

Setup (repo root se): `source .venv/bin/activate && pip install -e ".[all]"`, `.env` mein LLM set karo.
Sab commands `04-rag/02-pdf-chat/` folder se chalao (ya poora path do).

## 1. Sample PDF banao / dekho
```bash
cd 04-rag/02-pdf-chat
python make_sample_pdf.py               # data/nimbuskart_handbook.pdf (4 pages) dobara banata hai
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
`(standalone query: ...)` line batati hai ki condense step chala.

## 3. Real LLM
```bash
python main.py ask data/nimbuskart_handbook.pdf "Can I carry forward unused leave?" -v
python main.py chat                     # interactive
python main.py ask ~/Downloads/koi.pdf "What is this document about?"
```
Chat mein try karo: "What is the parental leave?" → "what about the other parent?" → standalone query dekho.

## 4. Offline tests
```bash
pytest 04-rag/02-pdf-chat -v
```
| Test | Kya prove karta hai |
|---|---|
| `test_load_pdf_pages_and_cleanup` | 4 pages, footer hata, hyphen joda |
| `test_chunks_keep_page_numbers` | har chunk ka page + id format |
| `test_scanned_pdf_detected` | text-less PDF pe "OCR" wala error |
| `test_condense_skipped_without_history` | pehle sawaal pe extra LLM call nahi |
| `test_answer_cites_page_and_followup_is_condensed` | [p.N] citations, follow-up rewrite, history |

## Kya dekhna hai
- `-v` mein retrieved chunks ke pages. Answer ka `[p.N]` unme se hi hai?
- Follow-up pe standalone query sensible hai? Real LLM kya likhta hai vs offline fake?
- Table wala sawaal ("hotel cap in non-metro cities?"): LLM ne sahi column padha?

## Tinker karo
1. **Condense band karo**: `condense_question` ko `return question` bana do. "what about the other parent?" ab kya retrieve karta hai?
2. **Chunk size**: `chunk_pages(size=150)` karo. Table row aur header alag chunks mein gaye? Answer bigda?
3. **Scanned PDF simulate**: `make_sample_pdf.py` mein kisi page ki lines khaali list kar do, dekho `empty_pages` report.
4. **Table ko sentences**: `PAGES` mein table rows ko "Hotel per night: metro 6000 rupees, non-metro 3500 rupees" likho, PDF dobara banao, non-metro wala sawaal compare karo.
5. **History length**: `max_turns=1` karke 3-4 follow-ups ki chain chalao. Kab context bhool jata hai?
6. **Multiple PDFs**: `PDFIndex.add_pdf()` do baar call karo (do alag PDFs), citation mein file name bhi jodo (`[handbook.pdf p.3]`).
