**Language:** [Hinglish](TESTING.md) · English

# MCP Client Agent: how to test and tinker

## Setup
```bash
# repo root
source .venv/bin/activate
pip install -e ".[all]"
cp .env.example .env      # fill in one provider, e.g. LLM_MODEL=groq:llama-3.3-70b-versatile + GROQ_API_KEY
cd 05-agent-communication/07-mcp/02-mcp-client-agent
```

## 1. Offline (no key)
```bash
python main.py --list                                # tools + resources of both servers
python main.py --offline "add groceries"             # fake LLM: add_note -> search_notes
python main.py --offline "calculate 12.5*4+3"        # a tool from the utils server
python main.py --offline "delete note 1"             # will ask y/N (destructive_hint)
```
A colored trace appears on stderr: `[mcp-host:tool] notes__add_note({...})`. This is the LLM's tool call
that the bridge delivered to the MCP server.

## 2. With a real LLM
```bash
python main.py "Add a note to renew my passport next month, tag it todo. Then list all my todo notes."
python main.py "How many km is 26.2 miles? Also save it as a note titled marathon."
python main.py --prompt summarize_notes topic=todo   # a task from an MCP prompt (user-controlled)
```
Switch models and compare:
```bash
LLM_MODEL=ollama:llama3.1 python main.py "..."
LLM_MODEL=gemini:gemini-3.8-flash python main.py "..."
```
Small models sometimes give a wrong tool name or wrong args. Watch how the agent loop recovers from the
`ERROR:` messages.

## 3. Add a remote server too (with project 03, 2 terminals)
Terminal 1:
```bash
cd ../03-mcp-http-transport && python mcp_http_server.py
```
Terminal 2 (without a token you get a 401, which is why this is better shown with 03's `main.py`):
```bash
cd ../03-mcp-http-transport && python main.py "add a note about remote MCP"
```

## 4. Offline tests
```bash
# repo root
.venv/bin/pytest 05-agent-communication/07-mcp/02-mcp-client-agent -v
```
- `test_bridge_converts_and_namespaces_tools`: schema bridge + the `(DESTRUCTIVE)` marker
- `test_agent_calls_tools_across_two_servers`: ScriptedLLM calls tools on two servers, then the DB is checked
- `test_destructive_tool_needs_human_ok`: approval "n" → the tool did not run
- `test_offline_brain_end_to_end_over_real_stdio`: real subprocess servers

## What to look for (debugging checklist)
- Are the names in the tool list in `server__tool` format?
- Are tool results with `ERROR:` going to the LLM (not crashing)?
- Is any python subprocess left behind when the program ends? (`ps aux | grep mcp_`) The bridge's `__exit__` closes everything.

## Tinker with it
1. **Read-only agent**: in `main.py` use `MCPBridge(servers, allow={"notes__search_notes", "utils__calculate"})`, then try to get the LLM to delete something.
2. **Put a resource into context**: before the task, add the output of `bridge.read_resource("notes", "notes://all")` to the system prompt. Now the LLM will need the search tool less. This is "app-controlled context".
3. **Add a third server**: add some public MCP server (e.g. `npx -y @modelcontextprotocol/server-filesystem /tmp`) to `default_servers()` via `StdioServerParameters(command="npx", args=[...])`.
4. **Tool overload experiment**: build a fake server with 50 dummy tools. Watch how the LLM's accuracy and token usage change.
5. **Your own risky list**: don't trust the annotations. Add a name-based list (`delete`, `drop`, `send`) to `confirm_destructive` too.
6. **Timeout**: set `MCPBridge(..., read_timeout=0.001)` and see what error you get on a slow tool.
