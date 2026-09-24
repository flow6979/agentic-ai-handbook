# 07 · MCP (Model Context Protocol): agent ↔ tools/data ka standard

| Folder | Kya seekhoge |
|---|---|
| [01-mcp-server-stdio](01-mcp-server-stdio/) | Server banana: tools, resources (+template), prompts; stdio; raw JSON-RPC handshake |
| [02-mcp-client-agent](02-mcp-client-agent/) | Apna LLM-agnostic **host**: multi-server bridge, schema conversion, permissions |
| [03-mcp-http-transport](03-mcp-http-transport/) | Remote server: Streamable HTTP, legacy SSE, bearer/OAuth concepts, security (poisoning, rug pull, injection) |

```
01 (server) ──used by──► 02 (host/agent) ──same host, remote server──► 03 (HTTP + auth + security)
```
Order: 01 → 02 → 03. Har folder mein `CONCEPTS.md` (theory) aur `TESTING.md` (chalao + tinker) hain.

SDK: official `mcp` Python SDK **2.x** (`MCPServer`, jo v1 mein `FastMCP` tha). Protocol eras: handshake-era (≤ 2025-11-25) aur stateless 2026-07-28. Dono is code mein test hote hain.
