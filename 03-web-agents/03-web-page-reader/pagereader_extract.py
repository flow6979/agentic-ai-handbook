"""HTML -> readable text, sirf stdlib `html.parser` se ("readability-lite").

Web page mein asli content ke saath bahut kachra hota hai: <script>, <style>, nav menus,
footers, cookie banners. LLM ko yeh sab bhejna = tokens waste + confusion. Strategy:
  1. SKIP tags ke andar ka sab ignore karo (script/style/nav/footer/...)
  2. Block tags pe newline daalo taaki paragraphs alag rahein
  3. Headings ko '#' se mark karo (structure bacha rahe)
  4. <main>/<article> mila to sirf uska text lo (woh asli content hota hai)
"""
from __future__ import annotations

from html.parser import HTMLParser

SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "iframe",
             "template", "button", "select"}
BLOCK_TAGS = {"p", "div", "section", "article", "main", "li", "ul", "ol", "br", "tr", "table", "blockquote",
              "pre", "h1", "h2", "h3", "h4", "h5", "h6", "dd", "dt", "figcaption"}
HEADINGS = {"h1": "# ", "h2": "## ", "h3": "### "}
VOID_TAGS = {"br", "img", "hr", "input", "meta", "link", "source", "wbr"}


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.main_depth = 0
        self.in_title = False
        self.title = ""
        self.all_parts: list[str] = []
        self.main_parts: list[str] = []

    def _emit(self, s: str) -> None:
        self.all_parts.append(s)
        if self.main_depth:
            self.main_parts.append(s)

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        if tag in SKIP_TAGS and tag not in VOID_TAGS:
            self.skip_depth += 1
            return
        if tag in ("main", "article"):
            self.main_depth += 1
        if self.skip_depth:
            return
        if tag in BLOCK_TAGS:
            self._emit("\n")
        if tag in HEADINGS:
            self._emit(HEADINGS[tag])
        if tag == "li":
            self._emit("- ")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in SKIP_TAGS and tag not in VOID_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag in ("main", "article"):
            self.main_depth = max(0, self.main_depth - 1)
        if tag in BLOCK_TAGS and not self.skip_depth:
            self._emit("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title += data
            return
        if not self.skip_depth:
            self._emit(data)


def _tidy(parts: list[str]) -> str:
    lines = []
    for raw in "".join(parts).split("\n"):
        line = " ".join(raw.split())
        if line and line not in ("-", "#", "##", "###"):
            lines.append(line)
    return "\n".join(lines)


def extract_text(html: str, min_main_chars: int = 200) -> tuple[str, str]:
    """Returns (title, text)."""
    p = _Extractor()
    p.feed(html)
    p.close()
    main = _tidy(p.main_parts)
    text = main if len(main) >= min_main_chars else _tidy(p.all_parts)
    return " ".join(p.title.split()), text
