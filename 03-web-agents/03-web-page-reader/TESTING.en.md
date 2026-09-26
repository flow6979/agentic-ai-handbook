**Language:** [Hinglish](TESTING.md) · English

# 03 · Web Page Reader: how to test and tinker

## 1. Offline demo
```bash
python 03-web-agents/03-web-page-reader/main.py --offline
```
It reads a honeybee article on a fake "encyclopedia.example" site. Look at the tool output in the trace:
```
title: Honeybees - Example Encyclopedia
url: https://encyclopedia.example/wiki/honeybee
chunks: 1 of 1
<untrusted_web_content source="..."> ... waggle dance ... </untrusted_web_content>
```

## 2. Look at the extractor alone (no LLM)
This is the most useful debugging tool: see what text the LLM *actually* receives.
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
**What to look for:**
- `chunks: 3 of 24`: only the relevant part of the page was sent
- Whether the answer cites the URL
- If you give a private URL, the tool returns `ERROR: FetchError: blocked host...` and the LLM tells the user

## 4. Offline tests
```bash
.venv/bin/pytest 03-web-agents/03-web-page-reader -v
```
| Test | What it proves |
|---|---|
| `test_extract_keeps_main_content_drops_junk` | Script, style, nav, cookie banner and footer are removed |
| `test_ssrf_guard_blocks_internal_targets` (8 cases) | localhost, 10.x, the metadata IP, IPv6 loopback, file:// and ftp:// are blocked |
| `test_redirect_followed_and_each_hop_checked` | A normal redirect is followed, a redirect to a private IP is blocked |
| `test_robots_txt_respected` | `Disallow` paths are not opened |
| `test_content_types` | text is allowed, PDF is rejected |
| `test_size_limit_truncates` | Large pages are cut at `max_bytes` |
| `test_injection_is_flagged_and_cannot_close_the_wrapper` | The attacker's fake closing tag is neutralized |

## 5. Tinker 🔧
1. **Injection experiment (real LLM):** in `main.py`, keep the offline fetcher but set `llm = get_llm()`, then ask "Summarize https://encyclopedia.example/recipes" (this fixture page hides injection text). Then remove the security lines from `SYSTEM` and run it again. Compare.
2. **Better extraction:** convert `<table>` into a markdown table (`| a | b |`) so pricing pages are read correctly.
3. **Tune k and the chunk size:** `make_reader_tool(fetcher, k=1, chunk_chars=400)` vs `k=6, chunk_chars=2000`. Compare answer quality and token count.
4. **DNS rebinding fix (advanced):** do not let the hostname be resolved again after the check. Connect to the resolved public IP itself (put the IP in the URL and keep the original hostname in the `Host` header; for HTTPS you also have to handle SNI), or send all traffic through an egress proxy that blocks private IPs.
5. **Allowlist mode:** add `PageFetcher(allowed_domains={"wikipedia.org", "python.org"})`. Many production agents are only allowed to open trusted domains.
6. **Compare with Jina Reader:** `https://r.jina.ai/<url>` (no key, rate-limited) is a service that returns a page as markdown. Compare your extractor's output with it.
