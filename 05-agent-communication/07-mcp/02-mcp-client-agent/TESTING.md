# MCP Client Agent: test aur tinker kaise karein

## Setup
```bash
# repo root
source .venv/bin/activate
pip install -e ".[all]"
cp .env.example .env      # ek provider bharo, e.g. LLM_MODEL=groq:llama-3.3-70b-versatile + GROQ_API_KEY
cd 05-agent-communication/07-mcp/02-mcp-client-agent
```

## 1. Offline (koi key nahi)
```bash
python main.py --list                                # dono servers ke tools + resources
python main.py --offline "add groceries"             # fake LLM: add_note -> search_notes
python main.py --offline "calculate 12.5*4+3"        # utils server ka tool
python main.py --offline "delete note 1"             # y/N poochhega (destructive_hint)
```
Stderr pe colored trace aata hai: `[mcp-host:tool] notes__add_note({...})`. Yeh LLM ka tool call hai
jo bridge ne MCP server tak pahunchaya.

## 2. Real LLM ke saath
```bash
python main.py "Add a note to renew my passport next month, tag it todo. Then list all my todo notes."
python main.py "How many km is 26.2 miles? Also save it as a note titled marathon."
python main.py --prompt summarize_notes topic=todo   # MCP prompt (user-controlled) se task
```
Model badal ke compare karo:
```bash
LLM_MODEL=ollama:llama3.1 python main.py "..."
LLM_MODEL=gemini:gemini-2.5-flash python main.py "..."
```
Chhote models kabhi galat tool naam ya galat args dete hain. Dekho agent loop ke `ERROR:` messages
se woh kaise recover karta hai.

## 3. Remote server bhi jodo (03 project ke saath, 2 terminals)
Terminal 1:
```bash
cd ../03-mcp-http-transport && python mcp_http_server.py
```
Terminal 2 (token ke bina 401 aayega, isliye yeh 03 ke `main.py` se better dikhta hai):
```bash
cd ../03-mcp-http-transport && python main.py "add a note about remote MCP"
```

## 4. Offline tests
```bash
# repo root
.venv/bin/pytest 05-agent-communication/07-mcp/02-mcp-client-agent -v
```
- `test_bridge_converts_and_namespaces_tools`: schema bridge + `(DESTRUCTIVE)` marker
- `test_agent_calls_tools_across_two_servers`: ScriptedLLM do servers ke tools call karta hai, phir DB check hota hai
- `test_destructive_tool_needs_human_ok`: approval "n" → tool nahi chala
- `test_offline_brain_end_to_end_over_real_stdio`: asli subprocess servers

## Kya dekhna hai (debugging checklist)
- Tool list mein naam `server__tool` format mein hain?
- `ERROR:` wale tool results LLM ko ja rahe hain (crash nahi)?
- Program khatam hone pe koi python subprocess bacha to nahi? (`ps aux | grep mcp_`) Bridge ka `__exit__` sab band karta hai.

## Tinker karo
1. **Read-only agent**: `main.py` mein `MCPBridge(servers, allow={"notes__search_notes", "utils__calculate"})` karo, phir LLM se delete karwane ki koshish karo.
2. **Resource ko context mein daalo**: task se pehle `bridge.read_resource("notes", "notes://all")` ka output system prompt mein jodo. Ab LLM ko search tool ki zaroorat kam padegi. Yeh "app-controlled context" hai.
3. **Teesra server jodo**: Koi public MCP server (e.g. `npx -y @modelcontextprotocol/server-filesystem /tmp`) ko `StdioServerParameters(command="npx", args=[...])` se `default_servers()` mein add karo.
4. **Tool overload experiment**: ek fake server banao jisme 50 dummy tools hon. Dekho LLM ki accuracy aur token usage kaise badalte hain.
5. **Apni risky list**: annotations pe bharosa mat karo. `confirm_destructive` mein naam-based list (`delete`, `drop`, `send`) bhi jodo.
6. **Timeout**: `MCPBridge(..., read_timeout=0.001)` karo aur dekho slow tool pe kya error aata hai.
