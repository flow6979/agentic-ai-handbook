# 03 · Web Page Reader: test aur tinker kaise karein

## 1. Offline demo
```bash
python 03-web-agents/03-web-page-reader/main.py --offline
```
Fake "encyclopedia.example" site pe honeybee article padha jaata hai. Trace mein tool output dekho:
```
title: Honeybees - Example Encyclopedia
url: https://encyclopedia.example/wiki/honeybee
chunks: 1 of 1
<untrusted_web_content source="..."> ... waggle dance ... </untrusted_web_content>
```

## 2. Sirf extractor dekho (no LLM)
Yeh sabse useful debugging tool hai: dekho ki LLM ko *actually* kya text milta hai.
```bash
python 03-web-agents/03-web-page-reader/main.py --raw https://en.wikipedia.org/wiki/Waggle_dance
python 03-web-agents/03-web-page-reader/main.py --raw https://news.ycombinator.com
python 03-web-agents/03-web-page-reader/main.py --raw http://localhost:8000        # → FetchError (SSRF guard)
python 03-web-agents/03-web-page-reader/main.py --raw http://169.254.169.254/      # → FetchError
```

## 3. Real LLM run
```bash
python 03-web-agents/03-web-page-reader/main.py "Summarize https://en.wikipedia.org/wiki/Waggle_dance in 3 bullets"
python 03-web-agents/03-web-page-reader/main.py "What does https://docs.python.org/3/whatsnew/3.13.html say about the GIL?"
```
**Kya dekhna hai:**
- `chunks: 3 of 24`: poore page ka sirf relevant hissa gaya
- Answer mein URL cite hua ya nahi
- Koi private URL diya to tool `ERROR: FetchError: blocked host...` deta hai aur LLM user ko batata hai

## 4. Offline tests
```bash
.venv/bin/pytest 03-web-agents/03-web-page-reader -v
```
| Test | Kya prove karta hai |
|---|---|
| `test_extract_keeps_main_content_drops_junk` | Script, style, nav, cookie banner aur footer hat jaate hain |
| `test_ssrf_guard_blocks_internal_targets` (8 cases) | localhost, 10.x, metadata IP, IPv6 loopback, file:// aur ftp:// block hote hain |
| `test_redirect_followed_and_each_hop_checked` | Normal redirect follow hota hai, private IP pe redirect block hota hai |
| `test_robots_txt_respected` | `Disallow` wale paths nahi khulte |
| `test_content_types` | text allow hota hai, PDF reject hota hai |
| `test_size_limit_truncates` | Bade pages `max_bytes` pe kat jaate hain |
| `test_injection_is_flagged_and_cannot_close_the_wrapper` | Attacker ka fake closing tag neutralize hota hai |

## 5. Tinker karo 🔧
1. **Injection experiment (real LLM):** `main.py` mein offline fetcher rakho lekin `llm = get_llm()` kar do, phir poochho "Summarize https://encyclopedia.example/recipes" (yeh fixture page hidden injection text rakhta hai). Phir `SYSTEM` se security lines hata ke dobara chalao. Farak dekho.
2. **Better extraction:** `<table>` ko markdown table mein convert karo (`| a | b |`), taaki pricing pages sahi padhe jaayein.
3. **k aur chunk size tune karo:** `make_reader_tool(fetcher, k=1, chunk_chars=400)` vs `k=6, chunk_chars=2000`. Answer quality aur token count compare karo.
4. **DNS rebinding fix (advanced):** check ke baad hostname dobara resolve mat hone do. Resolved public IP pe hi connect karo (URL mein IP daalo aur `Host` header original hostname rakho; HTTPS ke liye SNI bhi sambhalna padega), ya saara traffic ek egress proxy se bhejo jo private IPs block kare.
5. **Allowlist mode:** `PageFetcher(allowed_domains={"wikipedia.org", "python.org"})` add karo. Kai production agents ko sirf trusted domains hi kholne diye jaate hain.
6. **Jina Reader compare karo:** `https://r.jina.ai/<url>` (no key, rate-limited) ek service hai jo page ko markdown mein deti hai. Apne extractor ka output isse compare karo.
