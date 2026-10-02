#!/bin/bash
# Self-test for delegate-extract / extract.py (no API calls, no cost).
# Usage: delegate/tests/extract_selftest.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
DX="$HERE/../bin/delegate-extract"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0; skip=0
ok()   { pass=$((pass+1)); echo "  ok   $1"; }
bad()  { fail=$((fail+1)); echo "  FAIL $1"; echo "$2" | sed 's/^/       /' | head -8; }
skp()  { skip=$((skip+1)); echo "  skip $1"; }
expect() { # name expected_exit expected_substring -- command...
  local name=$1 want=$2 grep=$3; shift 4
  local out; out=$("$@" 2>&1); local rc=$?
  if [ "$rc" = "$want" ] && echo "$out" | grep -q -- "$grep"; then ok "$name"; else bad "$name (exit $rc, want $want)" "$out"; fi
}

python3 "$HERE/make_fixtures.py" "$T" >/dev/null
F="$T"

expect "docx heading"                 0 "^# Quarterly Review"      -- "$DX" "$F/sample.docx"
expect "docx runs joined"             0 "Revenue grew 12 percent." -- "$DX" "$F/sample.docx"
expect "docx list item"               0 "^- First point"           -- "$DX" "$F/sample.docx"
expect "docx table"                   0 "| North | 40 |"           -- "$DX" "$F/sample.docx"
expect "xlsx sheet name"              0 "## Sheet: Budget"         -- "$DX" "$F/sample.xlsx"
expect "xlsx shared string"           0 "A1 = Rent"                -- "$DX" "$F/sample.xlsx"
expect "xlsx formula shown"           0 "ƒ =SUM(B1:B1)\*2"         -- "$DX" "$F/sample.xlsx"
expect "xlsx cached value"            0 "B2 = 2401"                -- "$DX" "$F/sample.xlsx"
expect "xlsx currency format kept"    0 'B1 = 1200.5 \[fmt:'       -- "$DX" "$F/sample.xlsx"
expect "xlsx date as ISO"             0 "A3 = 2025-01-01"          -- "$DX" "$F/sample.xlsx"
expect "pptx slide text"              0 "Market Overview"          -- "$DX" "$F/sample.pptx"
expect "pptx speaker notes"           0 "> Mention pricing"        -- "$DX" "$F/sample.pptx"
expect "odt heading"                  0 "^## Method"               -- "$DX" "$F/sample.odt"
expect "odt spaces"                   0 "We sampled forty firms."  -- "$DX" "$F/sample.odt"
expect "ods formula"                  0 "ƒ of:=\[.A1\]\*0.2"       -- "$DX" "$F/sample.ods"
expect "html drops script, keeps link" 0 "the source (https://example.com/src)" -- "$DX" "$F/sample.html"
expect "html drops script text"       0 "clean"                    -- bash -c "'$DX' '$F/sample.html' | grep -q 'var x' || echo clean"
expect "--out-dir writes files"       0 "EXTRACTED:"               -- "$DX" "$F/sample.docx" --out-dir "$T/out"
expect "out file exists"              0 "Quarterly"                -- cat "$T/out/sample.docx.md"
printf 'x\0y' > "$F/blob.bin"
expect "unknown binary -> exit 2"     2 "unsupported binary"       -- "$DX" "$F/blob.bin"
echo "SECRET=1" > "$F/.env"
expect "deny list -> exit 3"          3 "deny pattern"             -- "$DX" "$F/.env"
printf 'not a zip' > "$F/broken.docx"
expect "corrupt docx -> exit 2"       2 "bad zip"                  -- "$DX" "$F/broken.docx"

# PDF: on macOS PDFKit must parse the generated fixture; elsewhere any backend.
backend=$(python3 -c "
import sys; sys.path.insert(0, '$HERE/../lib'); import extract, shutil
if extract.swift_available(): print('pdfkit')
elif shutil.which('pdftotext'): print('pdftotext')
else:
    try:
        import pypdf; print('pypdf')
    except ImportError: print('none')")
if [ "$backend" = none ]; then
  if [ "$(uname)" = Darwin ]; then bad "pdf backend on macOS" "no swift (Command Line Tools), pdftotext or pypdf"; else skp "pdf (no backend)"; fi
else
  expect "pdf text ($backend)"         0 "Hello Delegate Extract"   -- "$DX" "$F/sample.pdf"
  expect "pdf page marker"             0 "<!-- page 1 -->"          -- "$DX" "$F/sample.pdf"
  expect "pdf without text is flagged" 0 "no text layer"            -- "$DX" "$F/blank.pdf"
fi

# OCR: tesseract, or Vision via swift. The image is rendered from the PDF fixture.
if command -v sips >/dev/null && sips -s format png "$F/sample.pdf" --out "$F/scan.png" >/dev/null 2>&1; then
  if command -v tesseract >/dev/null; then
    expect "image OCR (tesseract)"     0 "Delegate"                 -- "$DX" "$F/scan.png"
  else skp "image OCR (tesseract not installed)"; fi
  vision=$(python3 -c "import sys; sys.path.insert(0, '$HERE/../lib'); import extract; print(extract.swift_available())")
  if [ "$vision" = True ]; then
    expect "image OCR (Vision)"        0 "Delegate"                 -- env PATH=/usr/bin:/bin:/usr/sbin /usr/bin/python3 "$DX" "$F/scan.png"
  else skp "image OCR (Vision: no Command Line Tools)"; fi
else
  skp "image OCR (no way to render a test image)"
fi

echo
echo "extract selftest: $pass passed, $fail failed, $skip skipped"
[ "$fail" = 0 ]
