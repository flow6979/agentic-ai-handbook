# MCP Server (stdio): concepts

## MCP kya hai? Ek line mein

**MCP (Model Context Protocol) = AI apps ke liye "USB-C port".** Tools aur data ko ek standard
tareeke se kisi bhi AI app (host) mein plug karne ka protocol.

MCP se pehle: har app (Claude Desktop, Cursor, tumhara agent) har tool (GitHub, Slack, DB) ke
liye alag integration likhta tha. **M apps × N tools = M×N integrations.**

MCP ke baad: har tool ek baar MCP server banata hai, har app ek baar MCP client banata hai.
**M + N integrations.**

```
   PEHLE (M x N)                          MCP KE BAAD (M + N)

 Claude ──┬── GitHub                    Claude ──┐            ┌── GitHub server
          ├── Slack                     Cursor ──┼── MCP ─────┼── Slack server
 Cursor ──┼── GitHub                    MyAgent ─┘  (standard) └── Notes server (yeh project)
          ├── Slack
 MyAgent ─┴── ... har baar naya code
```

## Architecture: Host, Client, Server

```
┌──────────────────────── HOST (AI app) ─────────────────────────┐
│  e.g. Claude Desktop, Claude Code, Cursor, 02-mcp-client-agent │
│                                                                │
│   LLM  ◄──►  host logic (agent loop, UI, permissions)          │
│                  │              │                              │
│            ┌─────┴────┐   ┌─────┴────┐   ek server = ek client │
│            │ Client 1 │   │ Client 2 │   (1:1 connection)      │
│            └─────┬────┘   └─────┬────┘                         │
└──────────────────┼──────────────┼──────────────────────────────┘
                   │ stdio        │ HTTP
            ┌──────┴─────┐  ┌─────┴──────┐
            │  Server A  │  │  Server B  │   server = tools/data expose karta hai
            │  (notes)   │  │  (remote)  │
            └────────────┘  └────────────┘
```

- **Host**: user-facing app. Isme LLM aur agent loop hote hain. Permissions aur approval bhi host decide karta hai.
- **Client**: host ke andar ka connector. Har server ke liye ek client.
- **Server**: chhota program jo capabilities expose karta hai. **Server ke andar koi LLM nahi hota.** Yeh bas tools/data deta hai.

## Server ke 3 primitives: kaun control karta hai?

| Primitive | Kya hai | Kaun decide karta hai kab use ho | Is project mein |
|---|---|---|---|
| **Tools** | Functions jo action lete hain (write, API call) | **Model** (LLM khud call karta hai) | `add_note`, `search_notes`, `mark_done`, `delete_note` |
| **Resources** | Read-only data, URI se pehchaana jata hai | **Application/host** (context mein kya daalna hai) | `notes://all`, template `notes://{note_id}` |
| **Prompts** | Reusable prompt templates | **User** (UI mein slash-command ki tarah choose karta hai) | `summarize_notes(topic)`, `weekly_review()` |

```
 User  ──chooses──►  PROMPT    ("/weekly_review")
 Host  ──attaches──► RESOURCE  (notes://all ko context mein daal do)
 LLM   ──calls────►  TOOL      (add_note(title=..., body=...))
```

**Resource template**: `notes://{note_id}` jaise URI mein variable hota hai. Client
`resources/templates/list` se template discover karta hai, phir `notes://7` padhta hai.

### Client-side primitives (server host se kuch maangta hai)
- **Sampling**: server host ke LLM se completion maangta hai. Isse server ko apni API key nahi chahiye hoti.
- **Elicitation**: server user se beech mein input maangta hai (form, confirmation, ya URL).
- **Roots**: host batata hai ki server kaunse folders/URIs chhoo sakta hai.
  - Installed SDK ke hisaab se roots aur logging dono **2026-07-28 revision mein deprecated** hain (SEP-2577). Isliye is server mein `ctx.info()` logging use nahi ki.

## Tool annotations: "hints"
```python
@mcp.tool(annotations=ToolAnnotations(destructive_hint=True))
def delete_note(note_id: int): ...
```
`read_only_hint`, `destructive_hint` aur `idempotent_hint` host ko batate hain ki tool kitna risky hai.
Host inhe dekh ke approval maang sakta hai (02 project yahi karta hai).

⚠️ Yeh sirf **hints** hain. Ek untrusted server jhooth bol sakta hai. Security ke liye inpe akele bharosa mat karo.

## Wire pe kya jata hai: JSON-RPC 2.0

MCP messages **JSON-RPC 2.0** hain. stdio pe har message ek line hota hai (newline-delimited).
Teen tarah ke messages hote hain:
- **request**: iska `id` hota hai aur response aata hai
- **response**: `result` ya `error` lautata hai
- **notification**: iska `id` nahi hota, isliye response bhi nahi aata

### Lifecycle (handshake-era, protocol ≤ 2025-11-25)

```
 Client                                              Server
   │ ── initialize {protocolVersion, capabilities, ──► │
   │                clientInfo}                         │
   │ ◄── result {protocolVersion, capabilities,  ────── │   version negotiate + capabilities
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
   │ (stdio: client stdin band karta hai => shutdown)   │
```

`python main.py --raw` chala ke yahi lines apni aankhon se dekho (`raw_jsonrpc_demo.py`).

### Nayi revision: 2026-07-28 (stateless)
Installed SDK (`mcp` 2.2.0) ek naya protocol era bhi bolta hai: **2026-07-28**. Isme:
- `initialize` handshake **nahi** hota. Client pehle `server/discover` probe karta hai.
- Har request apne aap mein complete hoti hai (per-request envelope), isliye server stateless reh sakta hai.
- Server→client requests (sampling/elicitation) ki jagah server ek **"input required"** result lautata hai. Client input laake request retry karta hai.

`Client(...)` default `mode="auto"` pe naya try karta hai aur purane server pe handshake pe fallback karta hai.
Isliye `main.py` mein `protocol=2026-07-28` dikhta hai, aur raw demo mein `2025-11-25`.
(Yeh details installed SDK ke source se li hain. Spec badalta rehta hai, confirm karne ke liye modelcontextprotocol.io dekho.)

## Transports

| Transport | Kaise | Kab |
|---|---|---|
| **stdio** (yeh project) | Host server ko subprocess ki tarah launch karta hai; stdin/stdout pe JSON-RPC | Local tools, single user, koi network nahi, auth ki zaroorat nahi |
| **Streamable HTTP** | Ek HTTP endpoint (`/mcp`): POST requests, optional SSE stream | Remote/shared servers → **03 project** |
| HTTP+SSE (legacy) | GET `/sse` stream + POST `/messages` | Purane clients (2024-11-05) → 03 mein flag se |

⚠️ **stdio ka golden rule: server mein kabhi `print()` mat karo.** stdout protocol ka channel hai,
aur ek stray print JSON-RPC stream tod dega. Logs `stderr` pe bhejo.

## Errors: do levels
- **Tool execution error** → `CallToolResult(isError=True, content=[message])`. Yeh **model ko dikhta hai**, taaki woh sudhaar sake.
  - SDK mein `raise ToolError("note 42 does not exist")` karo, toh message model tak jaata hai.
  - Koi aur exception (crash) aaye to model ko sirf generic "Error executing tool X" dikhta hai. Asli text server pe hi rehta hai, taaki internals leak na hon.
- **Protocol error** (unknown method, invalid params) → JSON-RPC `error` object.

## Kab MCP server banana chahiye, kab nahi

✅ Banao jab:
- tools ko **kai apps/agents** mein reuse karna hai (Claude Desktop + Cursor + tumhara agent)
- tools doosri team/company ke hain aur process isolation chahiye
- ek standard permission/approval UI chahiye (host ka)

❌ Mat banao jab:
- sirf ek agent hai aur tools usi codebase mein hain. Tab plain function calling (agentkit `@tool`) simple aur tez hai.
- latency bahut critical hai. Har call ek extra process/network hop hai.

## MCP vs Function calling vs A2A

| | Function calling | MCP | A2A |
|---|---|---|---|
| Kya jodta hai | LLM ↔ tumhare code ke functions | Agent/host ↔ **tools & data** | Agent ↔ **agent** |
| Kahan chalta hai | Same process | Alag process/server | Alag service (network) |
| Standard? | Provider-specific format | Open protocol | Open protocol |
| Doosri side mein LLM? | Nahi | Nahi (server "dumb" hota hai) | **Haan**, remote agent khud sochta hai |
| Interaction | ek call → result | ek call → result | **Task**: multi-turn, long-running, streaming |
| Example | `@tool def add()` | Notes server | Travel expert agent (08-a2a) |

Asal mein MCP **function calling ko standardize** karta hai: MCP tool ka `inputSchema` wahi JSON
Schema hai jo LLM ko function calling mein jaata hai (02 ka bridge bilkul yahi karta hai).

## Security pitfalls (server author ke liye)
- **Input validation**: SDK schema check karta hai, lekin business rules (id exist karti hai ya nahi) tumhe khud check karne hain.
- **SQL injection**: parameterized queries (`?`) use karo. Is project mein string concat nahi hai.
- **Least privilege**: destructive tools kam rakho. Unhe `destructive_hint` se mark karo.
- **Path traversal**: resource templates mein `../../etc/passwd` jaise params aa sakte hain. SDK ke `ResourceSecurity` defaults isse bachate hain. Apne handler mein bhi validate karo, jaise yahan `note_id.isdigit()`.
- **Secrets**: API keys env se lo, tool output mein kabhi mat lautao.

## Is project mein kaise use ho raha hai

| Concept | Kahan |
|---|---|
| Server banana (`MCPServer`, v1 ka `FastMCP`) | `mcp_notes_server.py` → `build_server()` |
| Business logic, protocol se alag | `NotesStore` class (sirf SQLite) |
| Tools + annotations + `ToolError` | `add_note`, `search_notes`, `mark_done`, `delete_note` |
| Static resource / resource template | `@mcp.resource("notes://all")`, `@mcp.resource("notes://{note_id}")` + `ResourceNotFoundError` |
| Prompts | `summarize_notes`, `weekly_review` |
| stdio transport | `build_server().run("stdio")` |
| SDK client se discovery + calls | `main.py` → `tour()` |
| Raw JSON-RPC handshake | `raw_jsonrpc_demo.py` |
| In-process testing (subprocess ke bina) | `test_mcp_notes_server.py` → `Client(server)` |
