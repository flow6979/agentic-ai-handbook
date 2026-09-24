"""SQLite store: customers, orders, shipments, FAQs, refunds, escalations, sessions, messages.

Real company mein yeh alag services / Postgres hote. Idea same hai: agent ke tools
asli system of record se baat karte hain, LLM kabhi data 'yaad' ya 'invent' nahi karta.
"""
from __future__ import annotations

import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers(id TEXT PRIMARY KEY, name TEXT, email TEXT);
CREATE TABLE IF NOT EXISTS orders(
    id TEXT PRIMARY KEY, customer_id TEXT, item TEXT, amount REAL, status TEXT,
    created_at TEXT, internal_note TEXT);
CREATE TABLE IF NOT EXISTS shipments(order_id TEXT PRIMARY KEY, carrier TEXT, tracking_no TEXT, eta TEXT, last_event TEXT);
CREATE TABLE IF NOT EXISTS faqs(id INTEGER PRIMARY KEY, question TEXT, answer TEXT);
CREATE TABLE IF NOT EXISTS refunds(
    id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT UNIQUE, amount REAL, reason TEXT,
    approved_by TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS escalations(
    id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT, reason TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, customer_id TEXT, summary TEXT DEFAULT '', created_at REAL);
CREATE TABLE IF NOT EXISTS messages(
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, role TEXT, content TEXT, created_at REAL);
"""

SEED_CUSTOMERS = [("cust_1", "Asha Verma", "asha@example.com"), ("cust_2", "Rahul Mehta", "rahul@example.com")]
# internal_note kabhi customer tak nahi jaana chahiye: tools isse select hi nahi karte (data minimization)
SEED_ORDERS = [
    ("ORD-1001", "cust_1", "Wireless earbuds", 39.99, "shipped", "2026-09-18", "fraud check passed; profit margin 31%"),
    ("ORD-1002", "cust_1", "Mechanical keyboard", 129.00, "delivered", "2026-09-02", "VIP customer, supplier batch B7"),
    ("ORD-1003", "cust_2", "Yoga mat", 25.00, "delivered", "2026-09-10", "repeat buyer"),
    ("ORD-1004", "cust_1", "Phone case", 12.50, "processing", "2026-09-23", "awaiting stock"),
]
SEED_SHIPMENTS = [
    ("ORD-1001", "BlueDart", "BD77812345", "2026-09-26", "Departed Mumbai hub"),
    ("ORD-1002", "Delhivery", "DL55501234", "2026-09-06", "Delivered to front door"),
    ("ORD-1003", "Delhivery", "DL55509876", "2026-09-14", "Delivered, signed by customer"),
]
SEED_FAQS = [
    ("What is the return policy?", "You can return most items within 30 days of delivery for a full refund, as long as they are unused."),
    ("How long does a refund take?", "Refunds are processed within 5-7 business days after approval, back to the original payment method."),
    ("How long does shipping take?", "Standard shipping takes 3-5 business days; express shipping takes 1-2 business days."),
    ("Which payment methods do you accept?", "We accept UPI, credit and debit cards, net banking and cash on delivery."),
    ("How do I cancel an order?", "Orders can be cancelled free of charge until they are shipped, from the My Orders page."),
]

_STOP = {"the", "a", "an", "is", "are", "do", "does", "i", "my", "your", "you", "what", "how", "to", "of", "for", "on",
         "can", "which", "it", "in", "me", "we"}


def _terms(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w.rstrip("s") for w in words if w not in _STOP}  # crude stemming: refunds -> refund


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: request timeout ke liye agent alag thread mein chalta hai
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self.conn.executescript(SCHEMA)
        self.seed_if_empty()

    # --- low level ---------------------------------------------------------
    def _q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, args).fetchall()

    def _x(self, sql: str, args: tuple = ()) -> int:
        with self._lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur.lastrowid

    def seed_if_empty(self) -> None:
        if self._q("SELECT 1 FROM customers LIMIT 1"):
            return
        with self._lock:
            self.conn.executemany("INSERT INTO customers VALUES (?,?,?)", SEED_CUSTOMERS)
            self.conn.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?)", SEED_ORDERS)
            self.conn.executemany("INSERT INTO shipments VALUES (?,?,?,?,?)", SEED_SHIPMENTS)
            self.conn.executemany("INSERT INTO faqs(question, answer) VALUES (?,?)", SEED_FAQS)
            self.conn.commit()

    # --- business data ------------------------------------------------------
    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT id, name, email FROM customers WHERE id=?", (customer_id,))
        return dict(rows[0]) if rows else None

    def get_order(self, customer_id: str, order_id: str) -> dict[str, Any] | None:
        """Hamesha customer_id se scope karo: dusre customer ka order 'exist hi nahi karta' (authz)."""
        rows = self._q(
            "SELECT id, item, amount, status, created_at FROM orders WHERE id=? AND customer_id=?",
            (order_id.strip().upper(), customer_id),
        )
        return dict(rows[0]) if rows else None

    def get_shipment(self, order_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT carrier, tracking_no, eta, last_event FROM shipments WHERE order_id=?", (order_id.upper(),))
        return dict(rows[0]) if rows else None

    def search_faq(self, query: str, k: int = 2) -> list[dict[str, str]]:
        q = _terms(query)
        scored = []
        for r in self._q("SELECT question, answer FROM faqs"):
            overlap = len(q & _terms(r["question"] + " " + r["answer"]))
            if overlap:
                scored.append((overlap, len(q & _terms(r["question"])), dict(r)))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [s[2] for s in scored[:k]]

    def refund_exists(self, order_id: str) -> bool:
        return bool(self._q("SELECT 1 FROM refunds WHERE order_id=?", (order_id.upper(),)))

    def create_refund(self, order_id: str, amount: float, reason: str, approved_by: str) -> int:
        return self._x(
            "INSERT INTO refunds(order_id, amount, reason, approved_by, created_at) VALUES (?,?,?,?,?)",
            (order_id.upper(), amount, reason, approved_by, time.time()),
        )

    def list_refunds(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._q("SELECT order_id, amount, approved_by FROM refunds ORDER BY id")]

    def create_escalation(self, customer_id: str, reason: str) -> int:
        return self._x("INSERT INTO escalations(customer_id, reason, created_at) VALUES (?,?,?)",
                       (customer_id, reason, time.time()))

    def list_escalations(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._q("SELECT id, customer_id, reason FROM escalations ORDER BY id")]

    # --- sessions / memory ---------------------------------------------------
    def session_owner(self, session_id: str) -> str | None:
        rows = self._q("SELECT customer_id FROM sessions WHERE id=?", (session_id,))
        return rows[0]["customer_id"] if rows else None

    def create_session(self, session_id: str, customer_id: str) -> None:
        self._x("INSERT INTO sessions(id, customer_id, created_at) VALUES (?,?,?)", (session_id, customer_id, time.time()))

    def get_summary(self, session_id: str) -> str:
        rows = self._q("SELECT summary FROM sessions WHERE id=?", (session_id,))
        return rows[0]["summary"] if rows else ""

    def set_summary(self, session_id: str, summary: str) -> None:
        self._x("UPDATE sessions SET summary=? WHERE id=?", (summary, session_id))

    def add_message(self, session_id: str, role: str, content: str) -> None:
        self._x("INSERT INTO messages(session_id, role, content, created_at) VALUES (?,?,?,?)",
                (session_id, role, content, time.time()))

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self._q("SELECT id, role, content FROM messages WHERE session_id=? ORDER BY id", (session_id,))]

    def delete_messages(self, ids: list[int]) -> None:
        if ids:
            self._x(f"DELETE FROM messages WHERE id IN ({','.join('?' * len(ids))})", tuple(ids))
