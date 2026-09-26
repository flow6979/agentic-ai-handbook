**Language:** [Hinglish](README.md) · English

# 07 · MCP (Model Context Protocol): the standard for agent ↔ tools/data

| Folder | What you will learn |
|---|---|
| [01-mcp-server-stdio](01-mcp-server-stdio/) | Building a server: tools, resources (+template), prompts; stdio; the raw JSON-RPC handshake |
| [02-mcp-client-agent](02-mcp-client-agent/) | Your own LLM-agnostic **host**: multi-server bridge, schema conversion, permissions |
| [03-mcp-http-transport](03-mcp-http-transport/) | Remote server: Streamable HTTP, legacy SSE, bearer/OAuth concepts, security (poisoning, rug pull, injection) |

```
01 (server) ──used by──► 02 (host/agent) ──same host, remote server──► 03 (HTTP + auth + security)
```
Order: 01 → 02 → 03. Every folder has a `CONCEPTS.md` (theory) and a `TESTING.md` (run + tinker).

SDK: the official `mcp` Python SDK **2.x** (`MCPServer`, which was `FastMCP` in v1). Protocol eras: handshake-era (≤ 2025-11-25) and stateless 2026-07-28. Both are tested in this code.
