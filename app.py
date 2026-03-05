from __future__ import annotations

import html
import io
import re
import urllib.parse
import zipfile
import zlib
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "0.0.0.0"
PORT = 5000

FIELD_PATTERNS = {
    "invoice_number": [
        r"Doc\.\s*No\.?\s*[:\-]?\s*([A-Z0-9\-/]+)",
        r"Invoice\s*(?:No\.?|#)\s*[:\-]?\s*([A-Z0-9\-/]+)",
    ],
    "invoice_date": [
        r"Invoice\s*Date\s*[:\-]?\s*([0-9]{4}[./-][0-9]{2}[./-][0-9]{2})",
        r"Date\s*[:\-]?\s*([0-9]{4}[./-][0-9]{2}[./-][0-9]{2})",
    ],
    "supplier": [r"Supplier\s*[:\-]?\s*(.+?)\s{2,}", r"Seller\s*[:\-]?\s*(.+?)\s{2,}"],
    "customer": [r"Customer\s*[:\-]?\s*(.+?)\s{2,}", r"Buyer\s*[:\-]?\s*(.+?)\s{2,}"],
    "total_amount": [
        r"Grand\s*Total\s*[:\-]?\s*([0-9.,]+\s*[A-Z]{3})",
        r"Total\s*Amount\s*[:\-]?\s*([0-9.,]+\s*[A-Z]{3})",
        r"Total\s*[:\-]?\s*([0-9.,]+\s*[A-Z]{3})",
    ],
    "vat_amount": [r"VAT\s*[:\-]?\s*([0-9.,]+\s*[A-Z]{3})", r"Tax\s*[:\-]?\s*([0-9.,]+\s*[A-Z]{3})"],
}

HUNGARIAN_LABELS = {
    "invoice_number": "Számlaszám",
    "invoice_date": "Számla kelte",
    "supplier": "Kibocsátó",
    "customer": "Vevő",
    "total_amount": "Végösszeg",
    "vat_amount": "ÁFA / adó összege",
}


def _pdf_unescape(value: str) -> str:
    value = value.replace(r"\n", " ").replace(r"\r", " ").replace(r"\t", " ")
    value = value.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    return value


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    raw_text = pdf_bytes.decode("latin1", errors="ignore")
    chunks: list[str] = []

    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf_bytes, re.DOTALL):
        stream_data = match.group(1)
        candidates = [stream_data]
        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                candidates.append(zlib.decompress(stream_data, wbits))
            except Exception:
                pass

        for cand in candidates:
            text = cand.decode("latin1", errors="ignore")
            for grp in re.findall(r"\((.*?)\)\s*Tj", text, re.DOTALL):
                chunks.append(_pdf_unescape(grp))
            for arr in re.findall(r"\[(.*?)\]\s*TJ", text, re.DOTALL):
                parts = re.findall(r"\((.*?)\)", arr, re.DOTALL)
                chunks.extend(_pdf_unescape(p) for p in parts)

    extracted = " ".join(chunks).strip()
    if extracted:
        return re.sub(r"\s+", " ", extracted)

    rough = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-.,:/ ]{4,}", raw_text)
    return " ".join(rough[:800])


def parse_fields(text: str) -> dict[str, str]:
    parsed = {k: "" for k in FIELD_PATTERNS}
    compact_text = re.sub(r"\s+", " ", text)
    for field, patterns in FIELD_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, compact_text, re.IGNORECASE)
            if match:
                parsed[field] = match.group(1).strip(" ,;")
                break
    return parsed


def xml_escape(raw: str) -> str:
    return (
        raw.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def paragraph_xml(text: str) -> str:
    safe = xml_escape(text)
    return f"<w:p><w:r><w:t xml:space=\"preserve\">{safe}</w:t></w:r></w:p>"


def create_docx(parsed: dict[str, str], original_text: str) -> bytes:
    paragraphs = [
        paragraph_xml("Külföldi számla magyar fordítása"),
        paragraph_xml("Automatikusan generált kivonat könyvelési ellenőrzéshez."),
    ]

    for key, label in HUNGARIAN_LABELS.items():
        value = parsed.get(key) or "Nincs automatikusan felismerve"
        paragraphs.append(paragraph_xml(f"{label}: {value}"))

    paragraphs.append(paragraph_xml("Eredeti szövegkivonat:"))
    excerpt = original_text[:3000] if original_text else "A PDF-ből nem sikerült olvasható szöveget kinyerni."
    paragraphs.append(paragraph_xml(excerpt))
    paragraphs.append(paragraph_xml(f"Generálás ideje: {datetime.now():%Y-%m-%d %H:%M}"))

    document_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:w10="urn:schemas-microsoft-com:office:word" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml" xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml" xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" mc:Ignorable="w14 w15 wp14">
  <w:body>
    {''.join(paragraphs)}
    <w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>
  </w:body>
</w:document>'''

    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>'''

    rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def render_form(message: str = "") -> bytes:
    msg_html = f'<p class="alert">{html.escape(message)}</p>' if message else ""
    page = f"""<!doctype html>
<html lang='hu'>
<head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Számla fordító</title>
<style>
body{{font-family:Arial,sans-serif;background:#eef4ff;margin:0;display:grid;place-items:center;min-height:100vh}}
.card{{max-width:680px;background:white;padding:2rem;border-radius:14px;box-shadow:0 8px 24px rgba(0,0,0,.15)}}
button{{background:#0b5ed7;color:#fff;border:0;padding:.8rem 1rem;border-radius:8px;font-weight:700;cursor:pointer}}
.alert{{background:#ffe3e3;color:#8a1111;padding:.7rem;border-radius:8px}}
</style></head>
<body><main class='card'><h1>Külföldi számla → magyar Word dokumentum</h1>
<p>Töltsd fel a számlát PDF-ben, majd egy kattintással elkészül a magyar fordítás.</p>
{msg_html}
<form method='post' action='/generate' enctype='multipart/form-data'>
<label for='invoice_file'>Számla (PDF):</label><br/><br/>
<input id='invoice_file' type='file' name='invoice_file' accept='application/pdf' required /><br/><br/>
<button type='submit'>Word fordítás készítése</button>
</form></main></body></html>"""
    return page.encode("utf-8")


class InvoiceHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        body = render_form()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/generate":
            self.send_error(404)
            return

        ctype = self.headers.get("Content-Type", "")
        match = re.search(r"boundary=(.+)", ctype)
        if "multipart/form-data" not in ctype or not match:
            self.respond_form("Hibás kérés: hiányzó feltöltési adatok.")
            return

        boundary = match.group(1).encode()
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)

        parts = body.split(b"--" + boundary)
        file_name = "invoice"
        file_data = b""

        for part in parts:
            if b'name="invoice_file"' in part:
                header, _, data = part.partition(b"\r\n\r\n")
                data = data.rsplit(b"\r\n", 1)[0]
                name_match = re.search(br'filename="([^"]+)"', header)
                if name_match:
                    file_name = name_match.group(1).decode(errors="ignore")
                file_data = data
                break

        if not file_data:
            self.respond_form("Nem sikerült fájlt beolvasni.")
            return

        if not file_name.lower().endswith(".pdf"):
            self.respond_form("Csak PDF fájl tölthető fel.")
            return

        text = extract_text_from_pdf(file_data)
        parsed = parse_fields(text)
        docx_bytes = create_docx(parsed, text)

        out_name = f"{Path(file_name).stem}_magyar_forditas.docx"
        quoted = urllib.parse.quote(out_name)

        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted}")
        self.send_header("Content-Length", str(len(docx_bytes)))
        self.end_headers()
        self.wfile.write(docx_bytes)

    def respond_form(self, message: str):
        body = render_form(message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), InvoiceHandler)
    print(f"Server running on http://{HOST}:{PORT}")
    server.serve_forever()
