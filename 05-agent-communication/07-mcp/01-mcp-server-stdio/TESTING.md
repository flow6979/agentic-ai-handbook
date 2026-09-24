# MCP Server (stdio): test aur tinker kaise karein

## Setup (repo root se, ek baar)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
cd 05-agent-communication/07-mcp/01-mcp-server-stdio
```
Is project ko **LLM ya API key ki zaroorat nahi**. Server khud "dumb" hai, sirf tools/data deta hai.

## 1. Tour chalao (SDK client)
```bash
python main.py            # --offline bhi chalega, same cheez
```
Kya dekhna hai:
- `protocol=2026-07-28`: SDK ne naya stateless protocol negotiate kiya
- 4 tools aur unke `hints` (delete_note → `destructive_hint: True`)
- `mark_done(999)` → `is_error=True`, aur message model-friendly hai (ToolError)
- resources: `notes://all` + template `notes://{note_id}`
- prompts: `weekly_review` ka text DB ke asli open items se bana hai

## 2. Raw JSON-RPC dekho (SDK ke bina)
```bash
python main.py --raw
```
`-->` = client ne bheja, `<--` = server ne lautaya. Is order ko dhyaan se dekho:
`initialize` → `notifications/initialized` (iska koi reply nahi aata) → `tools/list` → `tools/call`.
Unknown tool bhi `isError: true` result deta hai, crash nahi.

## 3. Offline tests
```bash
# repo root se
.venv/bin/pytest 05-agent-communication/07-mcp/01-mcp-server-stdio -v
```
- `test_tools_resources_prompts_in_process`: `Client(server)` se in-process connection (fast, no subprocess)
- `test_real_stdio_subprocess`: asli subprocess, jaise Claude Desktop karta hai
- `test_raw_jsonrpc_handshake`: wire format pe assertions

## 4. MCP Inspector (official debugging UI)
Node.js chahiye:
```bash
npx @modelcontextprotocol/inspector python mcp_notes_server.py
```
Browser khulega. Wahan:
- **Tools** tab: `add_note` form bharo aur Run karo
- **Resources** tab: `notes://all` padho, template mein `note_id=1` daalo
- **Prompts** tab: `summarize_notes` try karo
- Neeche **raw JSON-RPC messages** bhi dikhte hain

Tip: Inspector `python` ko PATH se chalata hai. venv ka python dena ho to full path do:
`npx @modelcontextprotocol/inspector /path/to/repo/.venv/bin/python mcp_notes_server.py`

## 5. Claude Desktop / Claude Code / Cursor mein plug karo

**Claude Desktop**: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
ya `%APPDATA%\Claude\claude_desktop_config.json` (Windows):
```json
{
  "mcpServers": {
    "notes": {
      "command": "/ABSOLUTE/PATH/agentic-ai-handbook/.venv/bin/python",
      "args": ["/ABSOLUTE/PATH/agentic-ai-handbook/05-agent-communication/07-mcp/01-mcp-server-stdio/mcp_notes_server.py"],
      "env": { "NOTES_DB": "/ABSOLUTE/PATH/notes.sqlite3" }
    }
  }
}
```
Claude Desktop restart karo, phir likho: *"add a note to call mom tomorrow, tag it family"*.

**Claude Code** (CLI):
```bash
claude mcp add notes -- /ABS/PATH/.venv/bin/python /ABS/PATH/.../mcp_notes_server.py
claude mcp list
```
Session mein `/mcp` se status dekho.

**Cursor**: `~/.cursor/mcp.json` (ya project mein `.cursor/mcp.json`) mein upar jaisa hi `mcpServers` block daalo.

⚠️ Paths hamesha **absolute** do. Host kisi aur folder se launch karta hai, isliye relative path toot jaata hai.

## Tinker karo
1. **Naya tool**: `tag_stats()` banao jo har tag ka count lautaye. Inspector mein turant dikhega.
2. **Structured output**: ek tool ka return type `dict` ya Pydantic model karo, phir dekho `structured_content` aur `outputSchema` kaise badalte hain (`main.py` mein `r.structured_content` print karo).
3. **Naya resource template**: `notes://tag/{tag}` banao jo ek tag ke saare notes de. `list_resource_templates` mein check karo.
4. **stdout todo**: `add_note` mein ek `print("hi")` daalo aur `python main.py` chalao. Dekho client kaise tootta hai. Phir `print(..., file=sys.stderr)` se fix karo.
5. **Crash vs ToolError**: `mark_done` mein `ToolError` ki jagah `ValueError` raise karo. Model ko ab sirf generic message milega. Socho yeh security ke liye kyun achha hai.
6. **Prompt arguments**: `weekly_review(max_items: str = "3")` banao aur Inspector ke Prompts tab mein argument field dekho.
