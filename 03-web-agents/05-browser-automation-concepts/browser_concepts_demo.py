"""Browser agent ka loop samjhane ke liye ek FAKE browser (Playwright install kiye bina).

Real browser agent (browser-use, Playwright MCP, computer-use) ka loop:

    observe (page ka accessibility tree / screenshot)
        -> LLM decide kare: click / type / goto / done
        -> action chalao
        -> naya observe ...

Yahan `FakeBrowser` ek chhoti si shop website simulate karta hai (search -> product -> add to cart),
aur agentkit ka normal `Agent` tools ke through usse chalata hai. Har element ka ek `ref` id hai
(jaise Playwright MCP ke snapshots mein hota hai) taaki LLM ko CSS selectors na likhne padein.

Run:
    python 03-web-agents/05-browser-automation-concepts/browser_concepts_demo.py            # offline demo
    python 03-web-agents/05-browser-automation-concepts/browser_concepts_demo.py --schema   # tool schemas dekho
    python 03-web-agents/05-browser-automation-concepts/browser_concepts_demo.py --playwright  # same flow ka real Playwright code
    python 03-web-agents/05-browser-automation-concepts/browser_concepts_demo.py --live "..."  # real LLM, fake browser
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field

from agentkit import Agent, ScriptedLLM, Tool, call, get_llm, tool, tool_response


@dataclass
class Element:
    ref: str
    role: str  # accessibility role: link, button, textbox, heading, text
    name: str  # accessible name (label/visible text)
    goto: str | None = None  # click karne pe kaunsa page khulega
    value: str = ""


@dataclass
class FakeBrowser:
    url: str = "https://shop.example/"
    cart: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    _query: str = ""

    def elements(self) -> list[Element]:
        """Current page ka accessibility tree (flattened). Real browser mein yeh
        `page.locator("body").aria_snapshot()` ya Playwright MCP ka `browser_snapshot` deta hai."""
        if self.url == "https://shop.example/":
            return [
                Element("e1", "heading", "Example Shop"),
                Element("e2", "textbox", "Search products", value=self._query),
                Element("e3", "button", "Search", goto="https://shop.example/search"),
                Element("e4", "link", "Cart", goto="https://shop.example/cart"),
            ]
        if self.url == "https://shop.example/search":
            items = [("e5", "Mechanical Keyboard K2 - ₹4,999"), ("e6", "Mechanical Keyboard Pro - ₹8,499")]
            if "keyboard" not in self._query.lower():
                return [Element("e1", "text", f"No results for {self._query!r}"), Element("e9", "link", "Home", goto="https://shop.example/")]
            return [Element("e1", "heading", f"Results for {self._query!r}")] + [
                Element(ref, "link", name, goto=f"https://shop.example/p/{ref}") for ref, name in items
            ]
        if self.url.startswith("https://shop.example/p/"):
            name = {"e5": "Mechanical Keyboard K2 - ₹4,999", "e6": "Mechanical Keyboard Pro - ₹8,499"}[self.url.rsplit("/", 1)[1]]
            return [Element("e1", "heading", name), Element("e7", "button", "Add to cart"), Element("e4", "link", "Cart", goto="https://shop.example/cart")]
        if self.url == "https://shop.example/cart":
            return [Element("e1", "heading", "Your cart")] + [Element(f"c{i}", "text", n) for i, n in enumerate(self.cart)]
        return [Element("e1", "text", "404")]

    def snapshot(self) -> str:
        lines = [f"url: {self.url}"]
        for e in self.elements():
            val = f' value="{e.value}"' if e.role == "textbox" else ""
            lines.append(f"- [{e.ref}] {e.role} \"{e.name}\"{val}")
        return "\n".join(lines)

    def _find(self, ref: str) -> Element:
        for e in self.elements():
            if e.ref == ref:
                return e
        raise ValueError(f"no element [{ref}] on this page; take a new snapshot")

    def click(self, ref: str) -> str:
        e = self._find(ref)
        self.history.append(f"click {ref} ({e.name})")
        if e.name == "Add to cart":
            product = self.elements()[0].name
            self.cart.append(product)
            return f"Added {product!r} to cart.\n" + self.snapshot()
        if e.goto:
            self.url = e.goto
        return self.snapshot()

    def type_text(self, ref: str, text: str) -> str:
        e = self._find(ref)
        if e.role != "textbox":
            raise ValueError(f"[{ref}] is a {e.role}, not a textbox")
        self._query = text
        self.history.append(f"type {ref} {text!r}")
        return self.snapshot()


def make_browser_tools(b: FakeBrowser) -> list[Tool]:
    @tool
    def browser_snapshot() -> str:
        """Return the current page as an accessibility tree with element refs like [e3]."""
        return b.snapshot()

    @tool
    def browser_click(ref: str) -> str:
        """Click the element with this ref (from the latest snapshot)."""
        return b.click(ref)

    @tool
    def browser_type(ref: str, text: str) -> str:
        """Type text into a textbox element."""
        return b.type_text(ref, text)

    return [browser_snapshot, browser_click, browser_type]


SYSTEM = """You control a web browser through tools. Always start with browser_snapshot.
Use element refs like e3 exactly as shown in the latest snapshot. After each action, read the new
snapshot before deciding the next step. Stop and report when the goal is done."""

GOAL = "Add the cheapest mechanical keyboard to the cart and tell me its price."

PLAYWRIGHT_EQUIVALENT = '''# pip install playwright && playwright install chromium
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto("https://shop.example/")
    print(page.locator("body").aria_snapshot())       # observe: accessibility (ARIA) tree the LLM sees
    page.get_by_role("textbox", name="Search products").fill("mechanical keyboard")
    page.get_by_role("button", name="Search").click()  # act
    page.get_by_role("link", name="Mechanical Keyboard K2").click()
    page.get_by_role("button", name="Add to cart").click()
    page.screenshot(path="cart.png")                   # vision-based agents send this image instead
    browser.close()
'''


def offline_llm() -> ScriptedLLM:
    return ScriptedLLM([
        tool_response(call("browser_snapshot")),
        tool_response(call("browser_type", ref="e2", text="mechanical keyboard")),
        tool_response(call("browser_click", ref="e3")),
        tool_response(call("browser_click", ref="e5"), text="K2 at ₹4,999 is cheaper than Pro at ₹8,499."),
        tool_response(call("browser_click", ref="e7")),
        "Done: added 'Mechanical Keyboard K2' to the cart. Price: ₹4,999 (cheaper of the two results).",
    ])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("goal", nargs="?", default=GOAL)
    p.add_argument("--offline", action="store_true", help="(default) scripted LLM")
    p.add_argument("--live", action="store_true", help="use a real LLM (get_llm) against the fake browser")
    p.add_argument("--schema", action="store_true", help="print tool JSON schemas the LLM receives")
    p.add_argument("--playwright", action="store_true", help="print the equivalent real Playwright script")
    args = p.parse_args()

    browser = FakeBrowser()
    tools = make_browser_tools(browser)
    if args.schema:
        print(json.dumps([t.spec.__dict__ for t in tools], indent=2, ensure_ascii=False))
        return
    if args.playwright:
        print(PLAYWRIGHT_EQUIVALENT)
        return

    llm = get_llm() if args.live else offline_llm()
    result = Agent(llm, tools, SYSTEM, name="browser", max_steps=12).run(args.goal)
    print("\n" + result.output)
    print(f"\n[actions: {browser.history}]\n[cart: {browser.cart}]")


if __name__ == "__main__":
    main()
