**Language:** Hinglish · [English](CONCEPTS.en.md)

# PDF Chat: concepts (Hinglish)

Project 01 mein humne plain markdown pe RAG kiya. Real duniya mein user **PDF upload** karta hai
(handbook, invoice, research paper, contract) aur chat karna chahta hai. Isme teen nayi problems aati hain:

1. PDF se **text nikaalna** hi mushkil hai
2. Answer mein **page number** chahiye ("p.3 pe likha hai")
3. User **follow-up** poochta hai ("aur sick leave?"), jo akele meaningless hai

## Flow

```
                 ┌─────────────── INGEST (upload pe ek baar) ───────────────┐
  handbook.pdf ──► pypdf.extract_text() per page ──► clean (hyphen, footer)
                                   │
                        text mila? ├── nahi (sab pages khaali) ──► "Scanned PDF hai, OCR chalao"
                                   │ haan
                                   ▼
                      chunk_pages(): har page ke andar chunks
                      id = "handbook.pdf:p3#0", page = 3
                                   │
                                   ▼
                              embed + store
                 └──────────────────────────────────────────────────────────┘

                 ┌─────────────── CHAT (har message) ───────────────────────┐
  "and sick leave?" + history
          │
          ▼
  [CONDENSE] LLM: history + follow-up ──► "How many sick leave days per year?"
          │                                 (history khaali ho to skip, LLM call bachao)
          ▼
  [RETRIEVE] standalone query se top-k chunks
          │
          ▼
  [ANSWER] system rules + last 4 turns + "[p.2] excerpt..." + QUESTION
          │
          ▼
  "Sick leave is 12 days per year. [p.2]"  ──► pages=[2], history mein save
                 └──────────────────────────────────────────────────────────┘
```

## 1. PDF text extraction: PDF "document" nahi, "drawing" hai

PDF andar se kaisa dikhta hai, yeh `make_sample_pdf.py` mein khud dekho:
```
BT /F1 11 Tf 50 790 Td (Every employee gets 24 days...) Tj T* ... ET
   font      position       yeh text yahan draw karo
```
PDF mein "paragraph", "table", "heading" jaisa kuch nahi hota, sirf **"yeh characters is x,y pe draw karo"**.
Extractor (pypdf) positions dekh ke text wapas jodne ki koshish karta hai. Isliye problems aati hain:

| Problem | Kya hota hai | Is project mein |
|---|---|---|
| Hyphenation | "reim-\nbursed" do tukde | `_clean()` jodta hai |
| Header/footer | har page pe "Page 3", company name | `_clean()` regex se hataata hai |
| Multi-column | dono columns ki lines mix ho jaati hain | nahi kiya (layout-aware parser chahiye) |
| **Tables** | rows/columns spaces mein bikhar jaate hain | caveat, neeche dekho |
| **Scanned PDF** | text hai hi nahi, sirf image | detect karke error |

### Scanned PDFs aur OCR
Scanner/phone se bani PDF mein pages **images** hain. `extract_text()` khaali string deta hai.
Humara code: agar **saare pages** khaali hain to `looks_scanned=True` aur saaf error:
"OCR chalao". Options (implement nahi kiye):
- **Tesseract / ocrmypdf**: free, local; PDF mein text layer jod deta hai
- **Cloud OCR**: AWS Textract, Google Document AI, Azure Document Intelligence (tables/forms bhi samajhte hain)
- **Vision LLM**: page ki image LLM ko do, woh markdown mein text likh de (mehenga, lekin layout achha samajhta hai)

Kuch pages khaali ho (mixed PDF) to `empty_pages` report mein aata hai.

### Tables ka caveat
Sample PDF ke page 3 pe ek table hai. pypdf se aisa niklta hai:
```
Category      Metro        Non-metro
Meals/day     1200         800
Hotel/night   6000         3500
```
Yahan to theek hai, lekin chunking ke baad agar header row ek chunk mein aur "Hotel/night 6000 3500"
doosre mein chala gaya, to LLM ko pata nahi "3500" kis column ka hai. Solutions:
- Table ko **alag element** ki tarah nikaalo (pdfplumber, Camelot, Unstructured, Docling)
- Har row ko sentence banao: "Hotel/night: Metro = 6000, Non-metro = 3500"
- Table ko ek unit rakho, kabhi beech se mat kaato

## 2. Page-aware chunking + citations
`chunk_pages()` **page ke andar** hi chunk karta hai, taaki har chunk ka exactly ek page ho.
Context mein har excerpt `[p.3] ...` ke saath jata hai, aur prompt bolta hai "cite like [p.3]".
Answer se regex `\[p\.(\d+)\]` se pages nikaalte hain. UI mein inhe clickable bana sakte ho
(PDF viewer us page pe khule), jisse user **verify** kar sake. Trust ke liye yeh bahut important hai.

Trade-off: paragraph do pages mein bata ho to do chunks mein toot jayega. Alternative: poore doc ko
chunk karo aur har chunk ke saath `page_start/page_end` metadata rakho.

## 3. Conversation memory + query condensation

```
 Turn 1: "How many paid leave days do I get?"   ──► retrieval theek
 Turn 2: "and sick leave?"                       ──► seedha embed kiya to?
                                                     "and", "sick", "leave" ... ho sakta hai chal jaaye
 Turn 3: "what about the other parent?"          ──► "other parent" kis cheez ka? retrieval fail
```
Retrieval ko history nahi dikhti. Solution: **Condense (query rewriting)**, jisme ek chhota LLM call
history + follow-up ko **standalone question** mein badal deta hai:
```
 history: "How many paid leave days?" / "24 days [p.2]"
 follow-up: "and sick leave?"
            │  CONDENSE
            ▼
 "How many sick leave days do employees get per year?"   ◄── ab yeh embed hoga
```
Details:
- History khaali ho to **skip** (extra LLM call ka paisa aur latency bachao)
- Sirf last N turns bhejo (`max_turns=4`), taaki prompt chhota rahe
- Final answer ke time bhi last 4 turns bhejte hain (continuity ke liye), lekin facts sirf excerpts se

Memory ke types (short):
- **Buffer memory**: last N messages (yahan yahi)
- **Summary memory**: purani baatein LLM se summarise karke rakho
- **Long-term / vector memory**: purani conversations ko bhi embed karke retrieve karo

## Kab kya use karein

| Situation | Approach |
|---|---|
| Chhoti PDF (<50 pages) + bade context wala model | Poori PDF prompt mein bhi daal sakte ho (long-context stuffing), RAG optional |
| Badi PDF / bahut saari PDFs | RAG (yeh project) |
| Scanned / forms / invoices | OCR ya Document AI pehle |
| Tables heavy (financial reports) | Table-aware parser + structured extraction |

## Is project mein kaise use ho raha hai

| Concept | File / function |
|---|---|
| PDF bana ke dekhna ki andar kya hai | `make_sample_pdf.py` (`build_pdf`, content stream ops) |
| Per-page extraction + cleanup | `pdfchat_core.py` → `load_pdf()`, `_clean()` |
| Scanned PDF detection | `PDFLoadReport.looks_scanned`, `PDFIndex.add_pdf()` raises |
| Page-aware chunks with overlap | `chunk_pages()` |
| Page citations | `ANSWER_SYSTEM` prompt, `[p.N]` regex in `PDFChat.ask()` |
| Query condensation | `CONDENSE_PROMPT`, `condense_question()` |
| Conversation buffer memory | `PDFChat.history` |
| CLI ask / chat | `main.py` |
| Offline fake LLM | `offline_pdf_llm()` |
