**Language:** [Hinglish](CONCEPTS.md) · English

# MCP Server (stdio): concepts

## What is MCP? In one line

**MCP (Model Context Protocol) = a "USB-C port" for AI apps.** A protocol for plugging tools and data
into any AI app (host) in one standard way.

Before MCP: every app (Claude Desktop, Cursor, your agent) wrote a separate integration for every
tool (GitHub, Slack, DB). **M apps × N tools = M×N integrations.**

After MCP: each tool builds an MCP server once, each app builds an MCP client once.
**M + N integrations.**

```
   BEFORE (M x N)                         AFTER MCP (M + N)

 Claude ──┬── GitHub                    Claude ──┐            ┌── GitHub server
          ├── Slack                     Cursor ──┼── MCP ─────┼── Slack server
 Cursor ──┼── GitHub                    MyAgent ─┘  (standard) └── Notes server (this project)
          ├── Slack
 MyAgent ─┴── ... new code every time
```

## Architecture: Host, Client, Server

```
┌──────────────────────── HOST (AI app) ─────────────────────────┐
│  e.g. Claude Desktop, Claude Code, Cursor, 02-mcp-client-agent │
│                                                                │
│   LLM  ◄──►  host logic (agent loop, UI, permissions)          │
│                  │              │                              │
│            ┌─────┴────┐   ┌─────┴────┐   one server = one      │
│            │ Client 1 │   │ Client 2 │   client (1:1)          │
│            └─────┬────┘   └─────┬────┘                         │
└──────────────────┼──────────────┼──────────────────────────────┘
                   │ stdio        │ HTTP
            ┌──────┴─────┐  ┌─────┴──────┐
            │  Server A  │  │  Server B  │   server = exposes tools/data
            │  (notes)   │  │  (remote)  │
            └────────────┘  └────────────┘
```

- **Host**: the user-facing app. It holds the LLM and the agent loop. The host also decides permissions and approvals.
- **Client**: the connector inside the host. One client per server.
- **Server**: a small program that exposes capabilities. **There is no LLM inside the server.** It only provides tools/data.

## The server's 3 primitives: who is in control?

| Primitive | What it is | Who decides when it is used | In this project |
|---|---|---|---|
| **Tools** | Functions that take actions (writes, API calls) | **Model** (the LLM calls them itself) | `add_note`, `search_notes`, `mark_done`, `delete_note` |
| **Resources** | Read-only data, identified by a URI | **Application/host** (what to put into context) | `notes://all`, template `notes://{note_id}` |
| **Prompts** | Reusable prompt templates | **User** (picks them in the UI like a slash command) | `summarize_notes(topic)`, `weekly_review()` |

```
 User  ──chooses──►  PROMPT    ("/weekly_review")
 Host  ──attaches──► RESOURCE  (put notes://all into the context)
 LLM   ──calls────►  TOOL      (add_note(title=..., body=...))
```

**Resource template**: a URI like `notes://{note_id}` contains a variable. The client discovers the
template via `resources/templates/list`, then reads `notes://7`.

### Client-side primitives (the server asks the host for something)
- **Sampling**: the server asks the host's LLM for a completion. This way the server does not need its own API key.
- **Elicitation**: the server asks the user for input mid-way (a form, a confirmation, or a URL).
- **Roots**: the host tells the server which folders/URIs it may touch.
  - According to the installed SDK, both roots and logging are **deprecated in the 2026-07-28 revision** (SEP-2577). That is why this server does not use `ctx.info()` logging.

## Tool annotations: "hints"
```python
@mcp.tool(annotations=ToolAnnotations(destructive_hint=True))
def delete_note(note_id: int): ...
```
`read_only_hint`, `destructive_hint` and `idempotent_hint` tell the host how risky a tool is.
The host can look at them and ask for approval (project 02 does exactly this).

⚠️ These are only **hints**. An untrusted server can lie. Do not rely on them alone for security.

## What goes over the wire: JSON-RPC 2.0

MCP messages are **JSON-RPC 2.0**. On stdio every message is one line (newline-delimited).
There are three kinds of messages:
- **request**: has an `id` and gets a response
- **response**: returns a `result` or an `error`
- **notification**: has no `id`, so no response comes back

### Lifecycle (handshake-era, protocol ≤ 2025-11-25)

```
 Client                                              Server
   │ ── initialize {protocolVersion, capabilities, ──► │
   │                clientInfo}                         │
   │ ◄── result {protocolVersion, capabilities,  ────── │   negotiate version + capabilities
   │             serverInfo, instructions}              │
   │ ── notifications/initialized ──────────────────► │   (notification, no reply)
   │                                                    │
   │ ── tools/list ─────────────────────────────────► │
   │ ◄── {tools:[{name, description, inputSchema,  ──── │
   │              annotations}]}                        │
   │ ── tools/call {name, arguments} ───────────────► │
   │ ◄── {content:[{type:text,...}], isError} ──────── │
   │ ── resources/read {uri} ───────────────────────► │
   │ ── prompts/get {name, arguments} ──────────────► │
   │           ...                                      │
   │ (stdio: client closes stdin => shutdown)           │
```

Run `python main.py --raw` to see these exact lines with your own eyes (`raw_jsonrpc_demo.py`).

### The new revision: 2026-07-28 (stateless)
The installed SDK (`mcp` 2.2.0) also speaks a new protocol era: **2026-07-28**. In it:
- There is **no** `initialize` handshake. The client first probes `server/discover`.
- Every request is complete on its own (a per-request envelope), so the server can stay stateless.
- Instead of server→client requests (sampling/elicitation), the server returns an **"input required"** result. The client gathers the input and retries the request.

`Client(...)` with the default `mode="auto"` tries the new era and falls back to the handshake on older servers.
That is why `main.py` shows `protocol=2026-07-28`, while the raw demo shows `2025-11-25`.
(These details come from the installed SDK's source. The spec keeps changing, so check modelcontextprotocol.io to confirm.)

## Transports

| Transport | How | When |
|---|---|---|
| **stdio** (this project) | The host launches the server as a subprocess; JSON-RPC over stdin/stdout | Local tools, single user, no network, no auth needed |
| **Streamable HTTP** | One HTTP endpoint (`/mcp`): POST requests, optional SSE stream | Remote/shared servers → **project 03** |
| HTTP+SSE (legacy) | GET `/sse` stream + POST `/messages` | Old clients (2024-11-05) → behind a flag in 03 |

⚠️ **The golden rule of stdio: never `print()` in the server.** stdout is the protocol channel,
and a single stray print will break the JSON-RPC stream. Send logs to `stderr`.

## Errors: two levels
- **Tool execution error** → `CallToolResult(isError=True, content=[message])`. This **is visible to the model**, so it can correct itself.
  - In the SDK, `raise ToolError("note 42 does not exist")` sends the message to the model.
  - Any other exception (a crash) shows the model only a generic "Error executing tool X". The real text stays on the server, so internals do not leak.
- **Protocol error** (unknown method, invalid params) → a JSON-RPC `error` object.

## When to build an MCP server, and when not to

✅ Build one when:
- the tools must be reused across **many apps/agents** (Claude Desktop + Cursor + your agent)
- the tools belong to another team/company and you need process isolation
- you want a standard permission/approval UI (the host's)

❌ Don't build one when:
- there is only one agent and the tools live in the same codebase. Plain function calling (agentkit `@tool`) is simpler and faster then.
- latency is very critical. Every call is an extra process/network hop.

## MCP vs Function calling vs A2A

| | Function calling | MCP | A2A |
|---|---|---|---|
| What it connects | LLM ↔ functions in your code | Agent/host ↔ **tools & data** | Agent ↔ **agent** |
| Where it runs | Same process | Separate process/server | Separate service (network) |
| Standard? | Provider-specific format | Open protocol | Open protocol |
| LLM on the other side? | No | No (the server is "dumb") | **Yes**, the remote agent thinks for itself |
| Interaction | one call → result | one call → result | **Task**: multi-turn, long-running, streaming |
| Example | `@tool def add()` | Notes server | Travel expert agent (08-a2a) |

In fact MCP **standardizes function calling**: an MCP tool's `inputSchema` is the same JSON
Schema that goes to the LLM in function calling (the bridge in 02 does exactly this).

## Security pitfalls (for server authors)
- **Input validation**: the SDK checks the schema, but business rules (does the id exist?) you must check yourself.
- **SQL injection**: use parameterized queries (`?`). There is no string concatenation in this project.
- **Least privilege**: keep destructive tools to a minimum. Mark them with `destructive_hint`.
- **Path traversal**: resource templates can receive params like `../../etc/passwd`. The SDK's `ResourceSecurity` defaults protect against this. Validate in your own handler too, like `note_id.isdigit()` here.
- **Secrets**: take API keys from env, never return them in tool output.

## How this project uses it

| Concept | Where |
|---|---|
| Building a server (`MCPServer`, `FastMCP` in v1) | `mcp_notes_server.py` → `build_server()` |
| Business logic, separate from the protocol | `NotesStore` class (SQLite only) |
| Tools + annotations + `ToolError` | `add_note`, `search_notes`, `mark_done`, `delete_note` |
| Static resource / resource template | `@mcp.resource("notes://all")`, `@mcp.resource("notes://{note_id}")` + `ResourceNotFoundError` |
| Prompts | `summarize_notes`, `weekly_review` |
| stdio transport | `build_server().run("stdio")` |
| Discovery + calls from the SDK client | `main.py` → `tour()` |
| Raw JSON-RPC handshake | `raw_jsonrpc_demo.py` |
| In-process testing (no subprocess) | `test_mcp_notes_server.py` → `Client(server)` |
