// macOS helper for extract.py: PDF text via PDFKit, OCR via Vision.
// Runs interpreted (`swift extract_macos.swift ...`); needs the Xcode Command
// Line Tools. One JSON object per input file on stdout.
//
//   swift extract_macos.swift pdf <tmp-dir> <file.pdf>...
//       {"path": ..., "pages": [{"text": ...} | {"text": "", "image": "<png>"}]}
//       Pages with no text layer are rendered to PNG in <tmp-dir> for OCR.
//   swift extract_macos.swift ocr <image>...
//       {"path": ..., "text": ...}
//   Failures: {"path": ..., "error": ...}
import AppKit
import Foundation
import PDFKit
import Vision

func emit(_ obj: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: obj),
       let s = String(data: data, encoding: .utf8) {
        print(s)
    }
}

func renderPNG(_ page: PDFPage, to url: URL) -> Bool {
    let box = page.bounds(for: .mediaBox)
    let scale: CGFloat = 2.0
    let w = Int(box.width * scale), h = Int(box.height * scale)
    guard w > 0, h > 0,
          let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                              space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return false }
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.scaleBy(x: scale, y: scale)
    page.draw(with: .mediaBox, to: ctx)
    guard let img = ctx.makeImage() else { return false }
    let rep = NSBitmapImageRep(cgImage: img)
    guard let data = rep.representation(using: .png, properties: [:]) else { return false }
    return (try? data.write(to: url)) != nil
}

func ocr(_ path: String) -> [String: Any] {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        return ["path": path, "error": "cannot read image"]
    }
    // Flatten onto white: transparent backgrounds read as black to Vision.
    let w = cg.width, h = cg.height
    guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                              space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
        return ["path": path, "error": "cannot allocate image buffer"]
    }
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
    guard let flat = ctx.makeImage() else { return ["path": path, "error": "cannot flatten image"] }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = true
    do {
        try VNImageRequestHandler(cgImage: flat, options: [:]).perform([req])
    } catch {
        return ["path": path, "error": "Vision failed: \(error)"]
    }
    let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    return ["path": path, "text": lines.joined(separator: "\n")]
}

let args = Array(CommandLine.arguments.dropFirst())
guard let mode = args.first else {
    FileHandle.standardError.write("usage: pdf <tmp-dir> <files...> | ocr <files...>\n".data(using: .utf8)!)
    exit(2)
}

if mode == "pdf", args.count >= 2 {
    let tmp = URL(fileURLWithPath: args[1])
    for (fi, path) in args.dropFirst(2).enumerated() {
        guard let doc = PDFDocument(url: URL(fileURLWithPath: path)) else {
            emit(["path": path, "error": "PDFKit could not open the file"])
            continue
        }
        if doc.isLocked {
            emit(["path": path, "error": "the PDF is encrypted"])
            continue
        }
        var pages: [[String: Any]] = []
        for i in 0..<doc.pageCount {
            guard let page = doc.page(at: i) else { pages.append(["text": ""]); continue }
            let text = page.string ?? ""
            if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                let png = tmp.appendingPathComponent("f\(fi)-p\(i + 1).png")
                pages.append(renderPNG(page, to: png) ? ["text": "", "image": png.path] : ["text": ""])
            } else {
                pages.append(["text": text])
            }
        }
        emit(["path": path, "pages": pages])
    }
} else if mode == "ocr" {
    for path in args.dropFirst() { emit(ocr(path)) }
} else {
    FileHandle.standardError.write("unknown mode \(mode)\n".data(using: .utf8)!)
    exit(2)
}
