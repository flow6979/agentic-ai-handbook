**Language:** [Hinglish](CONCEPTS.md) · English

# PDF Chat: concepts (English)

In project 01 we did RAG on plain markdown. In the real world a user **uploads a PDF**
(handbook, invoice, research paper, contract) and wants to chat with it. That brings three new problems:

1. Just **extracting the text** from a PDF is hard
2. The answer needs a **page number** ("it says so on p.3")
3. The user asks a **follow-up** ("and sick leave?"), which is meaningless on its own

## Flow

```
                 ┌─────────────── INGEST (once, on upload) ─────────────────┐
  handbook.pdf ──► pypdf.extract_text() per page ──► clean (hyphen, footer)
                                   │
                        got text?  ├── no (all pages empty) ──► "It is a scanned PDF, run OCR"
                                   │ yes
                                   ▼
                      chunk_pages(): chunks inside each page
                      id = "handbook.pdf:p3#0", page = 3
                                   │
                                   ▼
                              embed + store
                 └──────────────────────────────────────────────────────────┘

                 ┌─────────────── CHAT (every message) ─────────────────────┐
  "and sick leave?" + history
          │
          ▼
  [CONDENSE] LLM: history + follow-up ──► "How many sick leave days per year?"
          │                                 (skip if history is empty, save an LLM call)
          ▼
  [RETRIEVE] top-k chunks for the standalone query
          │
          ▼
  [ANSWER] system rules + last 4 turns + "[p.2] excerpt..." + QUESTION
          │
          ▼
  "Sick leave is 12 days per year. [p.2]"  ──► pages=[2], saved in history
                 └──────────────────────────────────────────────────────────┘
```

## 1. PDF text extraction: a PDF is a "drawing", not a "document"

See for yourself what a PDF looks like inside, in `make_sample_pdf.py`:
```
BT /F1 11 Tf 50 790 Td (Every employee gets 24 days...) Tj T* ... ET
   font      position       draw this text here
```
A PDF has no "paragraph", "table" or "heading", only **"draw these characters at this x,y"**.
The extractor (pypdf) looks at positions and tries to stitch the text back together. That is why problems come up:

| Problem | What happens | In this project |
|---|---|---|
| Hyphenation | "reim-\nbursed" becomes two pieces | `_clean()` joins them |
| Header/footer | "Page 3", company name on every page | `_clean()` removes them with a regex |
| Multi-column | lines from both columns get mixed | not done (needs a layout-aware parser) |
| **Tables** | rows/columns scatter into spaces | caveat, see below |
| **Scanned PDF** | there is no text at all, only an image | detected, raises an error |

### Scanned PDFs and OCR
In a PDF made by a scanner/phone, the pages are **images**. `extract_text()` returns an empty string.
Our code: if **all pages** are empty, `looks_scanned=True` and a clear error:
"run OCR". Options (not implemented):
- **Tesseract / ocrmypdf**: free, local; adds a text layer to the PDF
- **Cloud OCR**: AWS Textract, Google Document AI, Azure Document Intelligence (they understand tables/forms too)
- **Vision LLM**: give the page image to an LLM and it writes the text as markdown (expensive, but understands layout well)

If only some pages are empty (a mixed PDF), they show up in the `empty_pages` report.

### The table caveat
Page 3 of the sample PDF has a table. pypdf extracts it like this:
```
Category      Metro        Non-metro
Meals/day     1200         800
Hotel/night   6000         3500
```
That is fine here, but if after chunking the header row lands in one chunk and "Hotel/night 6000 3500"
in another, the LLM does not know which column "3500" belongs to. Solutions:
- Extract the table as a **separate element** (pdfplumber, Camelot, Unstructured, Docling)
- Turn each row into a sentence: "Hotel/night: Metro = 6000, Non-metro = 3500"
- Keep the table as one unit, never cut it in the middle

## 2. Page-aware chunking + citations
`chunk_pages()` chunks **inside a page** only, so every chunk has exactly one page.
Each excerpt goes into the context with `[p.3] ...`, and the prompt says "cite like [p.3]".
We extract pages from the answer with the regex `\[p\.(\d+)\]`. In a UI you can make them clickable
(the PDF viewer opens on that page), so the user can **verify**. This matters a lot for trust.

Trade-off: a paragraph split across two pages will break into two chunks. Alternative: chunk the whole doc
and keep `page_start/page_end` metadata on each chunk.

## 3. Conversation memory + query condensation

```
 Turn 1: "How many paid leave days do I get?"   ──► retrieval is fine
 Turn 2: "and sick leave?"                       ──► what if we embed it directly?
                                                     "and", "sick", "leave" ... it might still work
 Turn 3: "what about the other parent?"          ──► "other parent" of what? retrieval fails
```
Retrieval does not see the history. Solution: **Condense (query rewriting)**, where one small LLM call
turns history + follow-up into a **standalone question**:
```
 history: "How many paid leave days?" / "24 days [p.2]"
 follow-up: "and sick leave?"
            │  CONDENSE
            ▼
 "How many sick leave days do employees get per year?"   ◄── this is what gets embedded now
```
Details:
- **Skip** when the history is empty (save the cost and latency of an extra LLM call)
- Send only the last N turns (`max_turns=4`) to keep the prompt small
- The final answer also gets the last 4 turns (for continuity), but facts come only from the excerpts

Types of memory (short):
- **Buffer memory**: the last N messages (used here)
- **Summary memory**: summarise older messages with the LLM and keep the summary
- **Long-term / vector memory**: embed old conversations too and retrieve them

## When to use what

| Situation | Approach |
|---|---|
| Small PDF (<50 pages) + a model with a big context | You can put the whole PDF in the prompt (long-context stuffing), RAG optional |
| Big PDF / many PDFs | RAG (this project) |
| Scanned / forms / invoices | OCR or Document AI first |
| Table heavy (financial reports) | Table-aware parser + structured extraction |

## How this project uses it

| Concept | File / function |
|---|---|
| Build a PDF to see what is inside | `make_sample_pdf.py` (`build_pdf`, content stream ops) |
| Per-page extraction + cleanup | `pdfchat_core.py` → `load_pdf()`, `_clean()` |
| Scanned PDF detection | `PDFLoadReport.looks_scanned`, `PDFIndex.add_pdf()` raises |
| Page-aware chunks with overlap | `chunk_pages()` |
| Page citations | `ANSWER_SYSTEM` prompt, `[p.N]` regex in `PDFChat.ask()` |
| Query condensation | `CONDENSE_PROMPT`, `condense_question()` |
| Conversation buffer memory | `PDFChat.history` |
| CLI ask / chat | `main.py` |
| Offline fake LLM | `offline_pdf_llm()` |
