"""Render documents as text for models that only read text.

Used by delegate-extract (CLI), delegate-inference (binary --files) and
review-loop (text renditions of binary targets and references).

Python 3.9+ standard library only. Optional system tools are used when
present: macOS `textutil`; `swift` (Xcode Command Line Tools) for PDFKit text
and Vision OCR; `pdftotext`; `tesseract`; the `pypdf` module.

    extract_many(paths) -> {path: Result(text, method, warnings) | ExtractError}
    extract(path)       -> Result, or raises ExtractError
    needs_extract(path) -> True for formats that are not plain text
"""
from __future__ import annotations

import datetime as dt
import html.parser
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
SWIFT_SCRIPT = HERE / "extract_macos.swift"

TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml", ".xml", ".log"}
OOXML = {".docx": "docx", ".docm": "docx", ".pptx": "pptx", ".pptm": "pptx",
         ".xlsx": "xlsx", ".xlsm": "xlsx"}
ODF = {".odt": "odt", ".ods": "ods", ".odp": "odp"}
HTML_EXT = {".html", ".htm", ".xhtml"}
TEXTUTIL_EXT = {".doc", ".rtf", ".webarchive", ".rtfd"}
PDF_EXT = {".pdf"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".gif", ".bmp", ".heic", ".webp"}
BINARY_EXT = set(OOXML) | set(ODF) | TEXTUTIL_EXT | PDF_EXT | IMAGE_EXT


class ExtractError(Exception):
    """Extraction is unsupported or failed for this file."""


class Result:
    def __init__(self, text: str, method: str, warnings: list | None = None):
        self.text, self.method, self.warnings = text, method, warnings or []

    def render(self, label: str) -> str:
        head = f"<!-- extracted from {label} by delegate-extract ({self.method}) -->\n"
        warn = "".join(f"<!-- warning: {w} -->\n" for w in self.warnings)
        return head + warn + "\n" + self.text.rstrip() + "\n"


def needs_extract(path) -> bool:
    """True if the file is not plain text: a known binary format, or NUL bytes early on."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext in BINARY_EXT or ext in HTML_EXT:
        return True
    if ext in TEXT_EXT:
        return False
    try:
        with p.open("rb") as f:
            return b"\x00" in f.read(8192)
    except OSError:
        return False


# ---------------------------------------------------------------- helpers

def _decode(raw: bytes) -> str:
    for bom, enc in ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16")):
        if raw.startswith(bom):
            return raw.decode(enc, errors="replace")
    return raw.decode("utf-8", errors="replace")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _attr(el, name: str):
    """Attribute by local name, whatever its namespace."""
    for k, v in el.attrib.items():
        if _local(k) == name:
            return v
    return None


def _cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ").strip()


def _pipe_table(rows: list) -> str:
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return ""
    w = max(len(r) for r in rows)
    rows = [r + [""] * (w - len(r)) for r in rows]
    out = ["| " + " | ".join(_cell(c) for c in rows[0]) + " |", "|" + "---|" * w]
    out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows[1:]]
    return "\n".join(out)


def _xml(z: zipfile.ZipFile, name: str):
    try:
        return ET.fromstring(z.read(name))
    except KeyError:
        return None


def _rels(z: zipfile.ZipFile, name: str) -> dict:
    """Relationship id -> (target path inside the zip, type)."""
    base = name.rsplit("/_rels/", 1)[0]
    root = _xml(z, name)
    out = {}
    if root is None:
        return out
    for r in root:
        tgt = r.get("Target", "")
        if tgt.startswith("/"):
            path = tgt.lstrip("/")
        else:
            path = os.path.normpath(os.path.join(base, tgt)).replace("\\", "/")
        out[r.get("Id")] = (path, r.get("Type", "").rsplit("/", 1)[-1])
    return out


# ---------------------------------------------------------------- docx

def _docx_para(p) -> str:
    parts = []
    for el in p.iter():
        t = _local(el.tag)
        if t == "t" and el.text:
            parts.append(el.text)
        elif t == "tab":
            parts.append("\t")
        elif t in ("br", "cr"):
            parts.append("\n")
    return "".join(parts)


def _docx(path: Path) -> Result:
    with zipfile.ZipFile(path) as z:
        root = _xml(z, "word/document.xml")
        if root is None:
            raise ExtractError("not a Word document (no word/document.xml)")
        body = next((c for c in root if _local(c.tag) == "body"), root)
        out = []
        for el in body:
            t = _local(el.tag)
            if t == "p":
                text = _docx_para(el)
                style = ""
                list_item = False
                for pr in el:
                    if _local(pr.tag) == "pPr":
                        for x in pr:
                            if _local(x.tag) == "pStyle":
                                style = (_attr(x, "val") or "").lower()
                            elif _local(x.tag) == "numPr":
                                list_item = True
                if not text.strip():
                    out.append("")
                    continue
                m = re.match(r"heading\s*(\d)", style)
                if m:
                    out.append("#" * min(int(m.group(1)), 6) + " " + text.strip())
                elif style == "title":
                    out.append("# " + text.strip())
                elif list_item or style.startswith("list"):
                    out.append("- " + text.strip())
                else:
                    out.append(text)
            elif t == "tbl":
                rows = []
                for tr in el.iter():
                    if _local(tr.tag) == "tr":
                        rows.append(["\n".join(_docx_para(p) for p in tc.iter() if _local(p.tag) == "p")
                                     for tc in tr if _local(tc.tag) == "tc"])
                out += ["", _pipe_table(rows), ""]
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
        return Result(text, "docx")


# ---------------------------------------------------------------- pptx

def _drawing_text(root) -> list:
    paras = []
    for p in root.iter():
        if _local(p.tag) == "p":
            s = "".join(t.text or "" for t in p.iter() if _local(t.tag) == "t")
            if s.strip():
                paras.append(s)
    return paras


def _pptx(path: Path) -> Result:
    with zipfile.ZipFile(path) as z:
        pres = _xml(z, "ppt/presentation.xml")
        rels = _rels(z, "ppt/_rels/presentation.xml.rels")
        order = []
        if pres is not None:
            for el in pres.iter():
                if _local(el.tag) == "sldId":
                    rid = next((v for k, v in el.attrib.items() if k.startswith("{") and _local(k) == "id"), None)
                    if rid in rels:
                        order.append(rels[rid][0])
        if not order:
            order = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                           key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)))
        out = []
        for i, slide in enumerate(order, 1):
            root = _xml(z, slide)
            if root is None:
                continue
            out.append(f"## Slide {i}")
            out += _drawing_text(root)
            srels = _rels(z, slide.replace("ppt/slides/", "ppt/slides/_rels/") + ".rels")
            for tgt, typ in srels.values():
                if typ == "notesSlide":
                    nroot = _xml(z, tgt)
                    notes = [p for p in _drawing_text(nroot) if not p.strip().isdigit()] if nroot is not None else []
                    if notes:
                        out.append("")
                        out.append("Speaker notes:")
                        out += ["> " + n for n in notes]
            out.append("")
        return Result("\n".join(out).strip(), "pptx")


# ---------------------------------------------------------------- xlsx

BUILTIN_FMT = {1: "0", 2: "0.00", 3: "#,##0", 4: "#,##0.00", 5: "$#,##0_);($#,##0)",
               6: "$#,##0_);[Red]($#,##0)", 7: "$#,##0.00_);($#,##0.00)",
               8: "$#,##0.00_);[Red]($#,##0.00)", 11: "0.00E+00", 12: "# ?/?", 13: "# ??/??",
               37: "#,##0 ;(#,##0)", 38: "#,##0 ;[Red](#,##0)", 39: "#,##0.00;(#,##0.00)",
               40: "#,##0.00;[Red](#,##0.00)", 48: "##0.0E+0"}
DATE_IDS = set(range(14, 23)) | {45, 46, 47}
PCT_IDS = {9, 10}


def _is_date_fmt(code: str) -> bool:
    s = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', "", code)   # drop literals, colours, escapes
    return bool(re.search(r"[dmyhs]", s, re.I)) and not re.fullmatch(r"[#0,.\s%E+\-]*", s)


def _col_letter(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _serial_to_iso(v: float, date1904: bool) -> str:
    base = dt.datetime(1904, 1, 1) if date1904 else dt.datetime(1899, 12, 30)
    d = base + dt.timedelta(days=v)
    if abs(v - int(v)) < 1e-9:
        return d.date().isoformat()
    return d.isoformat(sep=" ", timespec="seconds")


def _xlsx(path: Path) -> Result:
    with zipfile.ZipFile(path) as z:
        wb = _xml(z, "xl/workbook.xml")
        if wb is None:
            raise ExtractError("not an Excel workbook (no xl/workbook.xml)")
        rels = _rels(z, "xl/_rels/workbook.xml.rels")
        date1904 = any(_local(e.tag) == "workbookPr" and (_attr(e, "date1904") in ("1", "true"))
                       for e in wb.iter())
        shared = []
        sst = _xml(z, "xl/sharedStrings.xml")
        if sst is not None:
            for si in sst:
                shared.append("".join(t.text or "" for t in si.iter() if _local(t.tag) == "t"))
        fmts, xf_fmt = {}, []
        st = _xml(z, "xl/styles.xml")
        if st is not None:
            for el in st.iter():
                if _local(el.tag) == "numFmt":
                    fmts[int(_attr(el, "numFmtId"))] = _attr(el, "formatCode") or ""
            for el in st:
                if _local(el.tag) == "cellXfs":
                    xf_fmt = [int(_attr(x, "numFmtId") or 0) for x in el]
        out = []
        for sh in wb.iter():
            if _local(sh.tag) != "sheet":
                continue
            name = _attr(sh, "name")
            rid = next((v for k, v in sh.attrib.items() if _local(k) == "id" and "relationships" in k), None)
            if rid not in rels:
                continue
            root = _xml(z, rels[rid][0])
            out.append(f"## Sheet: {name}")
            if root is None:
                out.append("(missing sheet part)")
                continue
            shared_f = {}
            lines = []
            for c in root.iter():
                if _local(c.tag) != "c":
                    continue
                ref, typ = c.get("r", "?"), c.get("t", "n")
                v = f = None
                is_text = None
                for ch in c:
                    tn = _local(ch.tag)
                    if tn == "v":
                        v = ch.text
                    elif tn == "f":
                        if ch.text:
                            f = ch.text
                            if ch.get("t") == "shared" and ch.get("si") is not None:
                                shared_f[ch.get("si")] = (ref, ch.text)
                        elif ch.get("t") == "shared" and ch.get("si") in shared_f:
                            mref, mtext = shared_f[ch.get("si")]
                            f = f"{mtext}  (shared formula from {mref}, adjusted relative to it)"
                    elif tn == "is":
                        is_text = "".join(t.text or "" for t in ch.iter() if _local(t.tag) == "t")
                if typ == "s" and v is not None:
                    val = shared[int(v)] if int(v) < len(shared) else f"<shared string {v}>"
                elif typ == "inlineStr":
                    val = is_text or ""
                elif typ == "b":
                    val = "TRUE" if v == "1" else "FALSE"
                elif typ in ("str", "e"):
                    val = v or ""
                elif v is None:
                    val = None
                else:
                    val = v
                    s_idx = int(c.get("s", "0"))
                    fid = xf_fmt[s_idx] if s_idx < len(xf_fmt) else 0
                    code = fmts.get(fid) or BUILTIN_FMT.get(fid, "")
                    try:
                        num = float(v)
                        if fid in DATE_IDS or (fid in fmts and _is_date_fmt(fmts[fid])):
                            val = _serial_to_iso(num, date1904)
                        elif fid in PCT_IDS or ("%" in code and not _is_date_fmt(code)):
                            val = f"{num * 100:g}%"
                        elif fid not in (0, 49):
                            val = f"{v} [fmt: {json.dumps(code) if code else 'id ' + str(fid)}]"
                    except ValueError:
                        pass
                if val is None and f is None:
                    continue
                lines.append(f"{ref} = {val if val is not None else ''}")
                if f is not None:
                    lines.append(f"  ƒ ={f}")
            out += lines or ["(empty)"]
            out.append("")
        return Result("\n".join(out).strip(), "xlsx (cell = cached value; ƒ = formula)")


# ---------------------------------------------------------------- odf

def _odf_text(el) -> str:
    parts = [el.text or ""]
    for ch in el:
        t = _local(ch.tag)
        if t == "s":
            parts.append(" " * int(_attr(ch, "c") or 1))
        elif t == "tab":
            parts.append("\t")
        elif t == "line-break":
            parts.append("\n")
        else:
            parts.append(_odf_text(ch))
        parts.append(ch.tail or "")
    return "".join(parts)


def _odf(path: Path, kind: str) -> Result:
    with zipfile.ZipFile(path) as z:
        root = _xml(z, "content.xml")
        if root is None:
            raise ExtractError("not an OpenDocument file (no content.xml)")
    body = next((e for e in root.iter() if _local(e.tag) in ("text", "spreadsheet", "presentation")
                 and _local(root.tag) == "document-content"), root)
    out = []
    if kind == "ods":
        for tbl in body.iter():
            if _local(tbl.tag) != "table":
                continue
            out.append(f"## Sheet: {_attr(tbl, 'name')}")
            r = 0
            for row in tbl.iter():
                if _local(row.tag) != "table-row":
                    continue
                rrep = int(_attr(row, "number-rows-repeated") or 1)
                cells = []
                col = 0
                for cell in row:
                    if _local(cell.tag) not in ("table-cell", "covered-table-cell"):
                        continue
                    crep = int(_attr(cell, "number-columns-repeated") or 1)
                    vt = _attr(cell, "value-type")
                    val = (_attr(cell, "date-value") or _attr(cell, "time-value")
                           or _attr(cell, "value") or _attr(cell, "boolean-value"))
                    if vt == "percentage" and val is not None:
                        val = f"{float(val) * 100:g}%"
                    if val is None:
                        val = "\n".join(_odf_text(p) for p in cell if _local(p.tag) == "p") or None
                    formula = _attr(cell, "formula")
                    for k in range(min(crep, 1 if (val is None and formula is None) else crep)):
                        col += 1
                        if val is not None or formula is not None:
                            cells.append((col, val, formula))
                    if val is None and formula is None:
                        col += crep - 1
                for k in range(min(rrep, 1 if not cells else rrep)):
                    r += 1
                    for col_i, val, formula in cells:
                        out.append(f"{_col_letter(col_i)}{r} = {val if val is not None else ''}")
                        if formula:
                            out.append(f"  ƒ {formula}")
                if not cells:
                    r += rrep - 1
            out.append("")
        return Result("\n".join(out).strip(), "ods (cell = value; ƒ = formula)")
    if kind == "odp":
        n = 0
        for page in body.iter():
            if _local(page.tag) == "page":
                n += 1
                out.append(f"## Slide {n}" + (f": {_attr(page, 'name')}" if _attr(page, "name") else ""))
                out += [_odf_text(p) for p in page.iter() if _local(p.tag) == "p" and _odf_text(p).strip()]
                out.append("")
        return Result("\n".join(out).strip(), "odp")

    def walk(el, depth=0):
        for ch in el:
            t = _local(ch.tag)
            if t == "h":
                out.append("#" * min(int(_attr(ch, "outline-level") or 1), 6) + " " + _odf_text(ch).strip())
            elif t == "p":
                out.append(_odf_text(ch))
            elif t == "list":
                for item in ch:
                    for p in item.iter():
                        if _local(p.tag) == "p" and _odf_text(p).strip():
                            out.append("  " * depth + "- " + _odf_text(p).strip())
            elif t == "table":
                rows = [["\n".join(_odf_text(p) for p in c.iter() if _local(p.tag) == "p")
                         for c in r if _local(c.tag) == "table-cell"]
                        for r in ch.iter() if _local(r.tag) == "table-row"]
                out.extend(["", _pipe_table(rows), ""])
            elif t in ("section", "text"):
                walk(ch, depth)
    walk(body)
    return Result(re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip(), "odt")


# ---------------------------------------------------------------- html

class _HTML(html.parser.HTMLParser):
    BLOCK = {"p", "div", "section", "article", "li", "tr", "br", "table", "ul", "ol",
             "header", "footer", "blockquote", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.href, self.prefix = [], 0, None, ""

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"):
            self.skip += 1
        elif re.fullmatch(r"h[1-6]", tag):
            self.out.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "li":
            self.out.append("\n- ")
        elif tag in ("td", "th"):
            self.out.append(" | ")
        elif tag in self.BLOCK:
            self.out.append("\n")
        elif tag == "a":
            self.href = dict(attrs).get("href")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template"):
            self.skip = max(0, self.skip - 1)
        elif tag == "a" and self.href:
            if not self.href.startswith(("#", "javascript:")):
                self.out.append(f" ({self.href})")
            self.href = None
        elif tag in self.BLOCK or re.fullmatch(r"h[1-6]", tag):
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(re.sub(r"\s+", " ", data))


def _html(path: Path) -> Result:
    p = _HTML()
    p.feed(_decode(path.read_bytes()))
    text = "".join(p.out)
    text = "\n".join(l.strip() for l in text.splitlines())
    return Result(re.sub(r"\n{3,}", "\n\n", text).strip(), "html")


# ---------------------------------------------------------------- system tools

def _run(cmd: list, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _textutil(path: Path) -> Result:
    if not shutil.which("textutil"):
        raise ExtractError(f"{path.suffix} needs macOS textutil, which is not available here")
    r = _run(["textutil", "-convert", "txt", "-stdout", str(path)])
    if r.returncode != 0:
        raise ExtractError(f"textutil failed: {r.stderr.strip()[:200]}")
    return Result(r.stdout, "textutil")


_SWIFT_OK = None


def swift_available() -> bool:
    """Only true when the Command Line Tools are installed; never invokes the
    /usr/bin/swift shim blind (without them it can pop an install dialog)."""
    global _SWIFT_OK
    if _SWIFT_OK is None:
        ok = False
        if SWIFT_SCRIPT.exists() and shutil.which("xcode-select"):
            try:
                r = _run(["xcode-select", "-p"], timeout=10)
                ok = r.returncode == 0 and Path(r.stdout.strip()).exists() and bool(shutil.which("swift"))
            except (OSError, subprocess.SubprocessError):
                ok = False
        _SWIFT_OK = ok
    return _SWIFT_OK


def _swift(mode: str, args: list) -> dict:
    """Run the bundled script once for many files. -> {path: payload}"""
    r = _run(["swift", str(SWIFT_SCRIPT), mode, *args], timeout=900)
    if r.returncode != 0:
        raise ExtractError(f"swift {mode} failed: {(r.stderr or r.stdout).strip()[-300:]}")
    out = {}
    for line in r.stdout.splitlines():
        if line.startswith("{"):
            d = json.loads(line)
            out[d["path"]] = d
    return out


def _ocr_images(paths: list) -> dict:
    """-> {path: (text, method) | ExtractError}"""
    res = {}
    if shutil.which("tesseract"):
        for p in paths:
            r = _run(["tesseract", p, "-", "--psm", "3"])
            res[p] = ((r.stdout, "OCR: tesseract") if r.returncode == 0
                      else ExtractError(f"tesseract failed: {r.stderr.strip()[:200]}"))
        return res
    if swift_available():
        try:
            got = _swift("ocr", paths)
        except ExtractError as e:
            return {p: e for p in paths}
        for p in paths:
            d = got.get(p)
            res[p] = ((d["text"], "OCR: macOS Vision") if d and "text" in d
                      else ExtractError((d or {}).get("error", "Vision OCR produced nothing")))
        return res
    return {p: ExtractError("OCR needs tesseract, or macOS with the Xcode Command Line Tools")
            for p in paths}


def _pdfs(paths: list) -> dict:
    """-> {path: Result | ExtractError}"""
    res = {}
    if swift_available():
        tmp = tempfile.mkdtemp(prefix="delegate-extract-")
        try:
            got = _swift("pdf", [tmp, *paths])
            need_ocr = []
            for p in paths:
                d = got.get(p)
                if not d or "pages" not in d:
                    res[p] = ExtractError((d or {}).get("error", "PDFKit could not open the file"))
                    continue
                need_ocr += [pg["image"] for pg in d["pages"] if pg.get("image")]
            ocr = _ocr_images(need_ocr) if need_ocr else {}
            for p in paths:
                if p in res:
                    continue
                parts, warns, method = [], [], "PDFKit"
                for i, pg in enumerate(got[p]["pages"], 1):
                    text = pg.get("text") or ""
                    if pg.get("image"):
                        o = ocr.get(pg["image"])
                        if isinstance(o, tuple) and o[0].strip():
                            text, method = o[0], f"PDFKit + {o[1]} for pages without text"
                            warns.append(f"page {i} has no text layer; text is from OCR")
                        elif isinstance(o, tuple):
                            warns.append(f"page {i} has no text layer, and OCR found no text")
                        else:
                            warns.append(f"page {i} has no text layer (scanned?) and OCR failed: {o}")
                    elif not text.strip():
                        warns.append(f"page {i} has no text layer (scanned?)")
                    parts.append(f"<!-- page {i} -->\n{text.strip()}")
                res[p] = Result("\n\n".join(parts), method, warns)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return res
    for p in paths:
        try:
            res[p] = _pdf_fallback(Path(p))
        except ExtractError as e:
            res[p] = e
    return res


def _pdf_fallback(path: Path) -> Result:
    if shutil.which("pdftotext"):
        r = _run(["pdftotext", "-layout", str(path), "-"])
        if r.returncode == 0:
            pages = r.stdout.split("\f")
            if pages and not pages[-1].strip():
                pages = pages[:-1]
            warns = [f"page {i} has no text layer (scanned?)" for i, t in enumerate(pages, 1) if not t.strip()]
            return Result("\n\n".join(f"<!-- page {i} -->\n{t.strip()}" for i, t in enumerate(pages, 1)),
                          "pdftotext", warns)
    try:
        import pypdf  # type: ignore
    except ImportError:
        raise ExtractError("PDF needs macOS with the Xcode Command Line Tools, pdftotext (poppler) "
                           "or the pypdf module; none is available")
    reader = pypdf.PdfReader(str(path))
    pages = [(pg.extract_text() or "") for pg in reader.pages]
    warns = [f"page {i} has no text layer (scanned?)" for i, t in enumerate(pages, 1) if not t.strip()]
    return Result("\n\n".join(f"<!-- page {i} -->\n{t.strip()}" for i, t in enumerate(pages, 1)),
                  "pypdf", warns)


# ---------------------------------------------------------------- dispatch

def _one(path: Path) -> Result:
    ext = path.suffix.lower()
    try:
        if ext in OOXML:
            return {"docx": _docx, "pptx": _pptx, "xlsx": _xlsx}[OOXML[ext]](path)
        if ext in ODF:
            return _odf(path, ODF[ext])
    except zipfile.BadZipFile:
        raise ExtractError(f"{path.name} is not a valid {ext} file (bad zip)")
    except ET.ParseError as e:
        raise ExtractError(f"{path.name}: malformed XML ({e})")
    if ext in HTML_EXT:
        return _html(path)
    if ext in TEXTUTIL_EXT:
        return _textutil(path)
    raw = path.read_bytes()
    if b"\x00" in raw[:8192]:
        raise ExtractError(f"{path.name}: unsupported binary format ({ext or 'no extension'})")
    if ext == ".tsv" or ext == ".csv":
        return Result(_decode(raw), ext[1:])
    return Result(_decode(raw), "text")


def extract_many(paths: list) -> dict:
    """Extract several files, batching PDFs and images so the swift helper
    starts once. -> {str(path): Result | ExtractError}"""
    res, pdfs, images = {}, [], []
    for p in map(str, paths):
        ext = Path(p).suffix.lower()
        if ext in PDF_EXT:
            pdfs.append(p)
        elif ext in IMAGE_EXT:
            images.append(p)
        else:
            try:
                res[p] = _one(Path(p))
            except ExtractError as e:
                res[p] = e
            except OSError as e:
                res[p] = ExtractError(str(e))
    if pdfs:
        res.update(_pdfs(pdfs))
    if images:
        for p, o in _ocr_images(images).items():
            if isinstance(o, tuple):
                res[p] = Result(o[0], o[1], ["text is from OCR"] if o[0].strip() else ["OCR found no text"])
            else:
                res[p] = o
    return res


def extract(path) -> Result:
    r = extract_many([path])[str(path)]
    if isinstance(r, ExtractError):
        raise r
    return r
