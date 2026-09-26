**Language:** [Hinglish](TESTING.md) · English

# MCP Server (stdio): how to test and tinker

## Setup (from the repo root, once)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
cd 05-agent-communication/07-mcp/01-mcp-server-stdio
```
This project **needs no LLM or API key**. The server itself is "dumb": it only provides tools/data.

## 1. Run the tour (SDK client)
```bash
python main.py            # --offline also works, same thing
```
What to look for:
- `protocol=2026-07-28`: the SDK negotiated the new stateless protocol
- 4 tools and their `hints` (delete_note → `destructive_hint: True`)
- `mark_done(999)` → `is_error=True`, and the message is model-friendly (ToolError)
- resources: `notes://all` + template `notes://{note_id}`
- prompts: the `weekly_review` text is built from the real open items in the DB

## 2. See the raw JSON-RPC (without the SDK)
```bash
python main.py --raw
```
`-->` = sent by the client, `<--` = returned by the server. Watch this order carefully:
`initialize` → `notifications/initialized` (it gets no reply) → `tools/list` → `tools/call`.
An unknown tool also returns an `isError: true` result, not a crash.

## 3. Offline tests
```bash
# from the repo root
.venv/bin/pytest 05-agent-communication/07-mcp/01-mcp-server-stdio -v
```
- `test_tools_resources_prompts_in_process`: in-process connection via `Client(server)` (fast, no subprocess)
- `test_real_stdio_subprocess`: a real subprocess, just like Claude Desktop does it
- `test_raw_jsonrpc_handshake`: assertions on the wire format

## 4. MCP Inspector (official debugging UI)
Requires Node.js:
```bash
npx @modelcontextprotocol/inspector python mcp_notes_server.py
```
A browser opens. There:
- **Tools** tab: fill in the `add_note` form and click Run
- **Resources** tab: read `notes://all`, put `note_id=1` into the template
- **Prompts** tab: try `summarize_notes`
- The **raw JSON-RPC messages** are shown at the bottom too

Tip: the Inspector runs `python` from your PATH. To use the venv's python, give the full path:
`npx @modelcontextprotocol/inspector /path/to/repo/.venv/bin/python mcp_notes_server.py`

## 5. Plug it into Claude Desktop / Claude Code / Cursor

**Claude Desktop**: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):
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
Restart Claude Desktop, then write: *"add a note to call mom tomorrow, tag it family"*.

**Claude Code** (CLI):
```bash
claude mcp add notes -- /ABS/PATH/.venv/bin/python /ABS/PATH/.../mcp_notes_server.py
claude mcp list
```
Check the status inside a session with `/mcp`.

**Cursor**: put the same `mcpServers` block as above into `~/.cursor/mcp.json` (or `.cursor/mcp.json` in the project).

⚠️ Always give **absolute** paths. The host launches from some other folder, so relative paths break.

## Tinker with it
1. **New tool**: build `tag_stats()` that returns a count per tag. It shows up in the Inspector right away.
2. **Structured output**: make one tool return a `dict` or a Pydantic model, then see how `structured_content` and `outputSchema` change (print `r.structured_content` in `main.py`).
3. **New resource template**: build `notes://tag/{tag}` that returns all notes for one tag. Check it in `list_resource_templates`.
4. **Break stdout**: put a `print("hi")` in `add_note` and run `python main.py`. Watch how the client breaks. Then fix it with `print(..., file=sys.stderr)`.
5. **Crash vs ToolError**: raise a `ValueError` instead of `ToolError` in `mark_done`. The model now only gets a generic message. Think about why this is good for security.
6. **Prompt arguments**: make `weekly_review(max_items: str = "3")` and look at the argument field in the Inspector's Prompts tab.
