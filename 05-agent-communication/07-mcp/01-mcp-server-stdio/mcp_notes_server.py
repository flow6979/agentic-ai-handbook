"""Notes MCP server: tools + resources (static + template) + prompts, SQLite pe.

Yeh file ek MCP *server* hai. Isko koi bhi MCP *host* (Claude Desktop, Claude Code,
Cursor, ya hamara apna 02-mcp-client-agent) launch karke use kar sakta hai.

Run (stdio transport, host isko subprocess ki tarah chalata hai):
    python mcp_notes_server.py

SDK: official `mcp` Python SDK 2.x. v1 mein isko `FastMCP` kehte the, v2 mein naam
`MCPServer` ho gaya (from mcp.server.mcpserver import MCPServer).
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError
from mcp.types import ToolAnnotations

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes.sqlite3")

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    done INTEGER NOT NULL DEFAULT 0
)
"""


class NotesStore:
    """Plain SQLite wrapper. MCP se bilkul independent: business logic alag, protocol alag."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        with closing(self._conn()) as c:
            c.execute(SCHEMA)
            c.commit()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row(r: sqlite3.Row) -> dict:
        return {"id": r["id"], "title": r["title"], "body": r["body"], "tags": json.loads(r["tags"]), "done": bool(r["done"])}

    def add(self, title: str, body: str, tags: list[str]) -> dict:
        with closing(self._conn()) as c:
            cur = c.execute("INSERT INTO notes(title, body, tags) VALUES (?,?,?)", (title, body, json.dumps(tags)))
            c.commit()
            return self.get(cur.lastrowid)  # type: ignore[arg-type]

    def get(self, note_id: int) -> dict | None:
        with closing(self._conn()) as c:
            r = c.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
            return self._row(r) if r else None

    def search(self, query: str) -> list[dict]:
        q = f"%{query.lower()}%"
        with closing(self._conn()) as c:
            rows = c.execute(
                "SELECT * FROM notes WHERE lower(title) LIKE ? OR lower(body) LIKE ? OR lower(tags) LIKE ? ORDER BY id",
                (q, q, q),
            ).fetchall()
            return [self._row(r) for r in rows]

    def all(self) -> list[dict]:
        with closing(self._conn()) as c:
            return [self._row(r) for r in c.execute("SELECT * FROM notes ORDER BY id").fetchall()]

    def mark_done(self, note_id: int) -> bool:
        with closing(self._conn()) as c:
            n = c.execute("UPDATE notes SET done=1 WHERE id=?", (note_id,)).rowcount
            c.commit()
            return n > 0

    def delete(self, note_id: int) -> bool:
        with closing(self._conn()) as c:
            n = c.execute("DELETE FROM notes WHERE id=?", (note_id,)).rowcount
            c.commit()
            return n > 0


def build_server(db_path: str | None = None) -> MCPServer:
    """Fresh server banao. Tests har baar naya DB path dete hain."""
    store = NotesStore(db_path or os.getenv("NOTES_DB", DEFAULT_DB))
    mcp = MCPServer(
        "notes",
        version="1.0.0",
        instructions="A personal notes/tasks store. Search before adding duplicates. Notes have ids, tags and a done flag.",
    )

    # ---------------- TOOLS: model-controlled (LLM khud decide karta hai kab call karna hai) ----------------
    # Type hints + docstring se SDK JSON Schema banata hai; bilkul agentkit ke @tool jaisa.

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False))
    def add_note(title: str, body: str, tags: list[str] | None = None) -> str:
        """Create a new note. Use tags like 'work', 'todo'. Returns the created note as JSON."""
        return json.dumps(store.add(title, body, tags or []))

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
    def search_notes(query: str) -> str:
        """Search notes by text in title, body or tags. Returns a JSON list (can be empty)."""
        return json.dumps(store.search(query))

    @mcp.tool(annotations=ToolAnnotations(idempotent_hint=True))
    def mark_done(note_id: int) -> str:
        """Mark a note/task as done."""
        if not store.mark_done(note_id):
            # ToolError = "expected" failure: message model tak jata hai (is_error=True) taaki woh khud sudhare.
            raise ToolError(f"note {note_id} does not exist")
        return f"note {note_id} marked done"

    @mcp.tool(annotations=ToolAnnotations(destructive_hint=True))
    def delete_note(note_id: int) -> str:
        """Permanently delete a note. Destructive: hosts should ask the user before calling."""
        if not store.delete(note_id):
            raise ToolError(f"note {note_id} does not exist")
        return f"note {note_id} deleted"

    # ---------------- RESOURCES: application-controlled (host decide karta hai kya context mein daalna hai) ----

    @mcp.resource("notes://all", mime_type="application/json", description="Every note as a JSON list")
    def all_notes() -> str:
        return json.dumps(store.all())

    # Resource TEMPLATE: URI mein {variable}. Client `resources/templates/list` se isko discover karta hai.
    @mcp.resource("notes://{note_id}", mime_type="application/json", description="One note by id")
    def one_note(note_id: str) -> str:
        if not note_id.isdigit() or not (note := store.get(int(note_id))):
            raise ResourceNotFoundError(f"note {note_id} not found")
        return json.dumps(note)

    # ---------------- PROMPTS: user-controlled (user UI mein slash-command ki tarah choose karta hai) ----------

    @mcp.prompt(description="Summarize all notes about a topic")
    def summarize_notes(topic: str) -> str:
        return (
            f"Use the search_notes tool to find every note about '{topic}'. "
            "Then write a 3-bullet summary and list open (not done) items separately."
        )

    @mcp.prompt(description="Weekly review of open tasks")
    def weekly_review() -> str:
        open_items = [n for n in store.all() if not n["done"]]
        lines = "\n".join(f"- [{n['id']}] {n['title']}" for n in open_items) or "(none)"
        return f"Here are my open items:\n{lines}\n\nGroup them by tag and suggest the top 3 to do this week."

    return mcp


if __name__ == "__main__":
    # stdio: stdout pe sirf JSON-RPC messages jaate hain. Isliye server mein kabhi print() mat karna!
    build_server().run("stdio")
