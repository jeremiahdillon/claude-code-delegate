#!/usr/bin/env python3
"""Write small test documents into DIR (standard library only).

  make_fixtures.py DIR

Creates sample.docx, sample.xlsx, sample.pptx, sample.odt, sample.ods,
sample.html, sample.pdf (one page with a text layer; xref offsets computed)
and blank.pdf (one page with no text layer).
"""
import sys
import zipfile
from pathlib import Path

d = Path(sys.argv[1])
d.mkdir(parents=True, exist_ok=True)

CT = '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
RELS = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def zipit(name, files):
    with zipfile.ZipFile(d / name, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in files.items():
            z.writestr(k, v)


# docx: a heading, a paragraph, a list item, a table
zipit("sample.docx", {
    "[Content_Types].xml": CT + '<Default Extension="xml" ContentType="application/xml"/>'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
    "_rels/.rels": RELS + f'<Relationship Id="rId1" Type="{R}/officeDocument" Target="word/document.xml"/></Relationships>',
    "word/document.xml": f'<w:document xmlns:w="{W}"><w:body>'
    '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Quarterly Review</w:t></w:r></w:p>'
    '<w:p><w:r><w:t xml:space="preserve">Revenue grew </w:t></w:r><w:r><w:t>12 percent.</w:t></w:r></w:p>'
    '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>First point</w:t></w:r></w:p>'
    '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Region</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Sales</w:t></w:r></w:p></w:tc></w:tr>'
    '<w:tr><w:tc><w:p><w:r><w:t>North</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>40</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
    '</w:body></w:document>',
})

# xlsx: shared string, number, formula, date-formatted and currency-formatted cells
zipit("sample.xlsx", {
    "[Content_Types].xml": CT + '<Default Extension="xml" ContentType="application/xml"/>'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
    "_rels/.rels": RELS + f'<Relationship Id="rId1" Type="{R}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
    "xl/workbook.xml": f'<workbook xmlns="{S}" xmlns:r="{R}"><sheets><sheet name="Budget" sheetId="1" r:id="rId1"/></sheets></workbook>',
    "xl/_rels/workbook.xml.rels": RELS + f'<Relationship Id="rId1" Type="{R}/worksheet" Target="worksheets/sheet1.xml"/>'
    f'<Relationship Id="rId2" Type="{R}/sharedStrings" Target="sharedStrings.xml"/>'
    f'<Relationship Id="rId3" Type="{R}/styles" Target="styles.xml"/></Relationships>',
    "xl/sharedStrings.xml": f'<sst xmlns="{S}"><si><t>Rent</t></si><si><t>Total</t></si></sst>',
    "xl/styles.xml": f'<styleSheet xmlns="{S}"><numFmts count="1"><numFmt numFmtId="164" formatCode="&quot;$&quot;#,##0.00"/></numFmts>'
    '<cellXfs count="3"><xf numFmtId="0"/><xf numFmtId="14"/><xf numFmtId="164"/></cellXfs></styleSheet>',
    "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{S}"><sheetData>'
    '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" s="2"><v>1200.5</v></c></row>'
    '<row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2" s="2"><f>SUM(B1:B1)*2</f><v>2401</v></c></row>'
    '<row r="3"><c r="A3" s="1"><v>45658</v></c></row>'
    '</sheetData></worksheet>',
})

# pptx: one slide with a title and a note
zipit("sample.pptx", {
    "[Content_Types].xml": CT + '<Default Extension="xml" ContentType="application/xml"/></Types>',
    "ppt/presentation.xml": f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst></p:presentation>',
    "ppt/_rels/presentation.xml.rels": RELS + f'<Relationship Id="rId2" Type="{R}/slide" Target="slides/slide1.xml"/></Relationships>',
    "ppt/slides/slide1.xml": f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree><p:sp><p:txBody>'
    '<a:p><a:r><a:t>Market Overview</a:t></a:r></a:p><a:p><a:r><a:t>Three competitors</a:t></a:r></a:p>'
    '</p:txBody></p:sp></p:spTree></p:cSld></p:sld>',
    "ppt/slides/_rels/slide1.xml.rels": RELS + f'<Relationship Id="rId1" Type="{R}/notesSlide" Target="../notesSlides/notesSlide1.xml"/></Relationships>',
    "ppt/notesSlides/notesSlide1.xml": f'<p:notes xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree><p:sp><p:txBody>'
    '<a:p><a:r><a:t>Mention pricing</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:notes>',
})

ODF_NS = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
          'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
          'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"')
zipit("sample.odt", {
    "mimetype": "application/vnd.oasis.opendocument.text",
    "content.xml": f'<office:document-content {ODF_NS}><office:body><office:text>'
    '<text:h text:outline-level="2">Method</text:h><text:p>We sampled<text:s/>forty firms.</text:p>'
    '</office:text></office:body></office:document-content>',
})
zipit("sample.ods", {
    "mimetype": "application/vnd.oasis.opendocument.spreadsheet",
    "content.xml": f'<office:document-content {ODF_NS}><office:body><office:spreadsheet>'
    '<table:table table:name="Tax"><table:table-row>'
    '<table:table-cell office:value-type="float" office:value="100"><text:p>100</text:p></table:table-cell>'
    '<table:table-cell table:formula="of:=[.A1]*0.2" office:value-type="float" office:value="20"><text:p>20</text:p></table:table-cell>'
    '</table:table-row></table:table></office:spreadsheet></office:body></office:document-content>',
})

(d / "sample.html").write_text(
    "<html><head><style>p{color:red}</style><script>var x=1;</script></head><body>"
    "<h2>Findings</h2><p>See <a href='https://example.com/src'>the source</a>.</p>"
    "<ul><li>alpha</li><li>beta</li></ul></body></html>")


def pdf(name, content: bytes):
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    (d / name).write_bytes(bytes(out))


pdf("sample.pdf", b"BT /F1 36 Tf 72 700 Td (Hello Delegate Extract) Tj ET")
pdf("blank.pdf", b"0 0 1 rg 72 600 200 100 re f")
print(d)
