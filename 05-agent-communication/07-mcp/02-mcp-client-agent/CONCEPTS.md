# MCP Client Agent (apna "host" banana): concepts

## Idea
01 mein humne **server** banaya. Ab hum **host** banayenge, yaani wahi cheez jo Claude Desktop ya
Cursor hai. Farak itna hai ki yeh **LLM-agnostic** hai: `get_llm()` se Groq, Gemini, OpenAI,
Ollama, koi bhi LLM chal sakta hai.

Host ka kaam:
1. servers se **connect** karna (stdio subprocess launch ya HTTP URL)
2. unke **tools discover** karna (`tools/list`)
3. MCP tool schemas ko **LLM ke function-calling format** mein badalna
4. LLM ke tool calls ko sahi server tak **route** karna (`tools/call`)
5. **permissions**: kaunse tools allowed hain, aur risky tools pe user se poochhna

## Poora flow

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
MCP tool ka `inputSchema` **already JSON Schema hai**. LLM function calling bhi JSON Schema hi
maangta hai, isliye conversion almost free hai:

```
MCP Tool                                   agentkit Tool (-> OpenAI/Anthropic/Gemini format)
{ name: "add_note",                        Tool(name="notes__add_note",
  description: "Create a note",    ──►          description="[notes] Create a note",
  inputSchema: {...JSON Schema...} }             parameters={...same JSON Schema...},
                                                 fn=lambda **kw: bridge._call("notes","add_note",kw))
```
Uske baad agentkit ka provider adapter (01 wale core mein) isse har LLM ke format mein badal deta hai.
Yaani 3 layers hain: **MCP schema → neutral Tool → provider wire format.**

## Key concept 2: Namespacing (multiple servers)
Do servers mein same naam ka tool ho sakta hai (dono mein `search`). Isliye naam banate hain
`<server>__<tool>`. LLM ko `notes__search_notes` dikhta hai, aur bridge `__` se split karke sahi
server pe bhejta hai.

## Key concept 3: Sync agent + async protocol
MCP client **async** hai aur connection ek event loop mein zinda rehna chahiye. agentkit ka loop
**sync** hai. Solution hai **blocking portal**: ek background thread mein permanent event loop,
aur sync code usme coroutine "submit" karta hai.

```
main thread:   agent.run() ... tool.fn(**args) ──portal.call()──┐
                                                                  ▼
portal thread: [event loop]  client.call_tool(...)  (session open rehta hai)
```
Yeh pattern production mein bhi common hai jab sync framework ko async library se jodna ho.

## Key concept 4: Primitives ka sahi use
| Primitive | Host mein kaise | Code |
|---|---|---|
| Tools | LLM ko diye jaate hain | `bridge.tools()` |
| Resources | Host/app khud padhta hai (LLM tool nahi) | `bridge.read_resource("notes", "notes://all")` |
| Prompts | User choose karta hai → task ban jaata hai | `main.py --prompt summarize_notes topic=work` |
| Server `instructions` | System prompt mein jodte hain | `bridge.instructions()` |

## Key concept 5: Permissions (host ki zimmedari)
MCP server kuch bhi expose kar sakta hai. **Kya allow karna hai, yeh host decide karta hai.**
- **Allowlist** (least privilege): `MCPBridge(servers, allow={"notes__search_notes"})` → read-only agent
- **Human-in-the-loop**: tools ke `destructive_hint` annotations se `confirm_destructive()` y/N maangta hai.
  (Hint untrusted ho sakta hai, isliye serious setups mein apni khud ki risky-tool list bhi rakho.)
- **Tool errors**: `isError` result ko `"ERROR: ..."` text banake LLM ko dete hain, taaki woh retry kare ya alternative dhoondhe.

## Subtypes: MCP clients kaise-kaise hote hain
- **Desktop/IDE hosts**: Claude Desktop, Claude Code, Cursor, VS Code. Config file se servers launch karte hain.
- **Framework adapters**: LangChain, OpenAI Agents SDK, Google ADK waghera mein built-in MCP adapters hain. Andar same idea hai (`tools/list` → framework tools).
- **Custom host** (yeh project): poora control milta hai, jaise LLM choice, permissions, logging.
- **Server-as-client (proxy/gateway)**: ek MCP server jo khud doosre servers ka client ho. Aggregation, auth, audit ke liye.

## Kab use karein / kab nahi
✅ Jab tumhare agent ko **third-party ya shared tools** chahiye, aur bina code likhe naye servers plug karne hain.<br>
❌ Jab sirf 2-3 in-house functions hain. Tab seedha `@tool` use karo, MCP ka overhead (process, serialization) bekaar hai.

## Trade-offs
- **Tool overload**: 10 servers × 20 tools = 200 tools. LLM confuse hota hai aur prompt bhi mehenga ho jaata hai. Allowlist use karo, ya pehle ek router step lagao jo relevant tools chune.
- **Latency**: har tool call ek extra IPC/HTTP hop hai.
- **Trust**: har server ek untrusted dependency hai (03 ka security section dekho).

## Is project mein kaise use ho raha hai
| Concept | Kahan |
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
