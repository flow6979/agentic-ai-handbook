"""Tiny pure-Python PDF writer (reportlab installed nahi hai, aur samajhne ke liye achha hai).

PDF andar se kya hai? Numbered "objects" + ek xref table (har object ka byte offset):
  1 Catalog -> 2 Pages -> [Page, Page, ...] -> har Page ka content stream (text drawing commands)
Text commands: BT (begin text) /F1 11 Tf (font) 50 790 Td (position) (hello) Tj (draw) ET (end)

Isliye PDF se text nikaalna "reading" nahi, drawing commands ko reverse karna hai. Scanned PDF mein
text commands hote hi nahi (sirf image), wahan OCR chahiye.

    python 04-rag/02-pdf-chat/make_sample_pdf.py   # data/nimbuskart_handbook.pdf banata hai
"""
from __future__ import annotations

import textwrap
from pathlib import Path

PAGES = [
    ("NimbusKart Employee Handbook - Welcome and Working Hours", [
        "This handbook explains the policies that apply to all NimbusKart employees in India.",
        "Core working hours are 11 AM to 5 PM IST. Outside core hours, employees choose their own schedule.",
        "Employees may work from home up to 3 days per week. Tuesdays and Thursdays are office days for all teams.",
        "The probation period for new employees is 3 months. During probation the notice period is 15 days;",
        "after confirmation the notice period is 60 days.",
    ]),
    ("Leave Policy", [
        "Every employee gets 24 days of paid leave per calendar year, credited at 2 days per month.",
        "Up to 10 unused paid leave days can be carried forward to the next year. The rest lapse on 31 December.",
        "Sick leave is separate: 12 days per year. A doctor's note is required for sick leave longer than 2 days.",
        "Parental leave is 26 weeks for the birthing parent and 6 weeks for the other parent.",
        "Leave requests must be raised in the HR portal at least 7 days in advance, except sick leave.",
    ]),
    ("Travel and Expenses", [
        "Domestic flights must be booked in economy class through the NimbusTravel portal.",
        "The daily meal allowance during business travel is 1200 rupees in metro cities and 800 rupees elsewhere.",
        "Hotel stays are capped at 6000 rupees per night in metro cities.",
        "Expense claims must be submitted within 30 days of the trip with itemised receipts.",
        "Claims are reimbursed with the next monthly salary after manager approval.",
        "Expense limits table:",
        "Category      Metro        Non-metro",
        "Meals/day     1200         800",
        "Hotel/night   6000         3500",
    ]),
    ("IT and Security", [
        "Company laptops must have full-disk encryption and automatic screen lock after 5 minutes.",
        "Passwords must be at least 14 characters. Multi-factor authentication is mandatory for all accounts.",
        "Lost or stolen devices must be reported to security@nimbuskart.example within 1 hour.",
        "Personal USB drives are blocked on company laptops. Use the approved cloud drive for file sharing.",
        "Security awareness training must be completed every 6 months.",
    ]),
]


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _content_stream(title: str, lines: list[str], page_no: int) -> bytes:
    ops = ["BT", "/F1 16 Tf", "18 TL", "50 790 Td", f"({_esc(title)}) Tj", "T*", "/F1 11 Tf", "15 TL", "T*"]
    for para in lines:
        for wrapped in textwrap.wrap(para, 88) or [""]:
            ops += [f"({_esc(wrapped)}) Tj", "T*"]
        ops.append("T*")
    ops += ["ET", "BT", "/F1 9 Tf", "290 30 Td", f"(Page {page_no}) Tj", "ET"]
    return "\n".join(ops).encode("latin-1")


def build_pdf(pages: list[tuple[str, list[str]]]) -> bytes:
    objects: list[bytes] = []
    n = len(pages)
    page_ids = [4 + 2 * i for i in range(n)]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {n} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, (title, lines) in enumerate(pages):
        stream = _content_stream(title, lines, i + 1)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {page_ids[i] + 1} 0 R >>".encode()
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


if __name__ == "__main__":
    path = Path(__file__).parent / "data" / "nimbuskart_handbook.pdf"
    path.write_bytes(build_pdf(PAGES))
    print(f"wrote {path} ({len(PAGES)} pages)")
