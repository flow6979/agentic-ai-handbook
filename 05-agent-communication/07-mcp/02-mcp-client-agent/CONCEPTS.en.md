**Language:** [Hinglish](CONCEPTS.md) · English

# MCP Client Agent (building your own "host"): concepts

## Idea
In 01 we built a **server**. Now we build a **host**, which is the same kind of thing as Claude Desktop or
Cursor. The difference is that this one is **LLM-agnostic**: through `get_llm()` it can run Groq, Gemini, OpenAI,
Ollama, any LLM.

The host's job:
1. **connect** to servers (launch a stdio subprocess or use an HTTP URL)
2. **discover** their tools (`tools/list`)
3. convert MCP tool schemas into the **LLM's function-calling format**
4. **route** the LLM's tool calls to the right server (`tools/call`)
5. **permissions**: which tools are allowed, and asking the user before risky tools

## The full flow

```
 User: "add groceries note, then show grocery notes"
   │
   ▼
┌─────────────────────────── HOST (mcp_client_agent.py) ─────────────────────────────┐
│                                                                                    │
│  Agent loop (agentkit)            MCPBridge                                        │
│  ┌───────────────┐   tools=[notes__add_note, notes__search_notes, utils__calculate]│
│  │ LLM (any)     │◄───────────────── bridge.tools()  (MCP schema -> agentkit Tool) │
│  │ get_llm()     │                                                                 │
│  └──────┬────────┘                                                                 │
│         │ tool_call: notes__add_note(title=..)                                     │
│         ▼                                                                          │
│   approve? (destructive?) ──no──► "human rejected"                                 │
│         │ yes                                                                      │
│         ▼                                                                          │
│   split "notes__add_note" -> server="notes", tool="add_note"                       │
│         │                                                                          │
│   ┌─────┴──────┐                 ┌────────────┐                                    │
│   │ Client     │                 │ Client     │                                    │
│   │ (notes)    │                 │ (utils)    │                                    │
└───┼────────────┼─────────────────┼────────────┼────────────────────────────────────┘
    │ stdio      │                 │ stdio
    ▼                              ▼
 mcp_notes_server.py            mcp_utils_server.py
```

## Key concept 1: Schema bridge (MCP → function calling)
An MCP tool's `inputSchema` **is already JSON Schema**. LLM function calling also expects JSON Schema,
so the conversion is almost free:

```
MCP Tool                                   agentkit Tool (-> OpenAI/Anthropic/Gemini format)
{ name: "add_note",                        Tool(name="notes__add_note",
  description: "Create a note",    ──►          description="[notes] Create a note",
  inputSchema: {...JSON Schema...} }             parameters={...same JSON Schema...},
                                                 fn=lambda **kw: bridge._call("notes","add_note",kw))
```
After that, agentkit's provider adapter (in the core from 01) turns it into each LLM's format.
So there are 3 layers: **MCP schema → neutral Tool → provider wire format.**

## Key concept 2: Namespacing (multiple servers)
Two servers can have a tool with the same name (both have `search`). So names are built as
`<server>__<tool>`. The LLM sees `notes__search_notes`, and the bridge splits on `__` to send it to the right
server.

## Key concept 3: Sync agent + async protocol
The MCP client is **async**, and the connection has to stay alive inside one event loop. agentkit's loop
is **sync**. The solution is a **blocking portal**: a permanent event loop in a background thread,
into which the sync code "submits" coroutines.

```
main thread:   agent.run() ... tool.fn(**args) ──portal.call()──┐
                                                                  ▼
portal thread: [event loop]  client.call_tool(...)  (the session stays open)
```
This pattern is common in production too, whenever a sync framework has to talk to an async library.

## Key concept 4: Using the primitives correctly
| Primitive | How the host uses it | Code |
|---|---|---|
| Tools | Given to the LLM | `bridge.tools()` |
| Resources | The host/app reads them itself (not an LLM tool) | `bridge.read_resource("notes", "notes://all")` |
| Prompts | The user picks one → it becomes the task | `main.py --prompt summarize_notes topic=work` |
| Server `instructions` | Added to the system prompt | `bridge.instructions()` |

## Key concept 5: Permissions (the host's responsibility)
An MCP server can expose anything. **The host decides what to allow.**
- **Allowlist** (least privilege): `MCPBridge(servers, allow={"notes__search_notes"})` → a read-only agent
- **Human-in-the-loop**: based on the tools' `destructive_hint` annotations, `confirm_destructive()` asks y/N.
  (A hint can be untrusted, so in serious setups keep your own list of risky tools too.)
- **Tool errors**: an `isError` result is turned into `"ERROR: ..."` text and given to the LLM, so it can retry or find an alternative.

## Subtypes: the kinds of MCP clients
- **Desktop/IDE hosts**: Claude Desktop, Claude Code, Cursor, VS Code. They launch servers from a config file.
- **Framework adapters**: LangChain, OpenAI Agents SDK, Google ADK and others have built-in MCP adapters. Inside it is the same idea (`tools/list` → framework tools).
- **Custom host** (this project): you get full control, such as LLM choice, permissions, logging.
- **Server-as-client (proxy/gateway)**: an MCP server that is itself a client of other servers. Used for aggregation, auth, audit.

## When to use it / when not
✅ When your agent needs **third-party or shared tools**, and you want to plug in new servers without writing code.<br>
❌ When you only have 2-3 in-house functions. Then just use `@tool`; MCP's overhead (process, serialization) is wasted.

## Trade-offs
- **Tool overload**: 10 servers × 20 tools = 200 tools. The LLM gets confused and the prompt gets expensive too. Use an allowlist, or add a router step first that picks the relevant tools.
- **Latency**: every tool call is an extra IPC/HTTP hop.
- **Trust**: every server is an untrusted dependency (see the security section in 03).

## How this project uses it
| Concept | Where |
|---|---|
| Connect multiple servers (stdio/HTTP/in-process) | `mcp_bridge.py` → `MCPBridge.__enter__` (`Client(spec)` via portal) |
| Schema bridge + namespacing | `MCPBridge.tools()` |
| Result content blocks → text | `result_to_text()` |
| Resources / prompts / instructions | `read_resource`, `list_resources`, `get_prompt`, `instructions` |
| Allowlist | `MCPBridge(..., allow=...)` |
| Human approval for destructive tools | `mcp_client_agent.py` → `confirm_destructive()` |
| Host agent (LLM-agnostic) | `build_agent()` + `get_llm()` in `main.py` |
| Second server (multi-server) | `mcp_utils_server.py` (safe AST calculator, no `eval`) |
| Offline fake brain | `offline_llm()` |
