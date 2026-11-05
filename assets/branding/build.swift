import Foundation
import CoreText
import CoreGraphics

// Run from the repository root on macOS. PNG export requires ImageMagick.
let directory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
let charcoal = "#242424"
let orange = "#C94708"
let light = "#FAFAF7"
let font = CTFontCreateWithName("Menlo-Bold" as CFString, 80, nil)
precondition(CTFontCopyPostScriptName(font) as String == "Menlo-Bold")

func number(_ value: CGFloat) -> String { String(format: "%.3f", Double(value)) }

// Store the lettering as paths so exported files do not need a font.
let letters = Array("typokiller".utf16)
var glyphs = [CGGlyph](repeating: 0, count: letters.count)
precondition(CTFontGetGlyphsForCharacters(font, letters, &glyphs, letters.count))
var advances = [CGSize](repeating: .zero, count: glyphs.count)
CTFontGetAdvancesForGlyphs(font, .horizontal, glyphs, &advances, glyphs.count)
let lettering = CGMutablePath()
var offset: CGFloat = 0
for (index, glyph) in glyphs.enumerated() {
    if let path = CTFontCreatePathForGlyph(font, glyph, nil) {
        lettering.addPath(path, transform: CGAffineTransform(a: 1, b: 0, c: 0, d: -1, tx: offset, ty: 0))
    }
    offset += advances[index].width + 1.5
}
let bounds = lettering.boundingBoxOfPath
var outline = ""
lettering.applyWithBlock { pointer in
    let element = pointer.pointee
    func point(_ index: Int) -> String {
        let p = element.points[index]
        return "\(number(p.x)) \(number(p.y))"
    }
    switch element.type {
    case .moveToPoint: outline += "M\(point(0))"
    case .addLineToPoint: outline += "L\(point(0))"
    case .addQuadCurveToPoint: outline += "Q\(point(0)) \(point(1))"
    case .addCurveToPoint: outline += "C\(point(0)) \(point(1)) \(point(2))"
    case .closeSubpath: outline += "Z"
    @unknown default: fatalError("Unknown path element")
    }
}

func mark(_ foreground: String, _ accent: String) -> String {
    """
    <path fill="\(foreground)" d="M84 0H196V90H264V174H196V317H327V407H84V174H0V90H84Z"/>
    <path fill="\(foreground)" d="M322 15L379 27L362 110L311 70ZM303 109L352 150L336 230L280 219Z"/>
    <path fill="\(accent)" d="M282 56L392 146L378 163L268 73Z"/>
    """
}

func svg(_ title: String, _ viewBox: String, _ width: Int, _ height: Int, _ body: String) -> String {
    """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="\(viewBox)" width="\(width)" height="\(height)" role="img" aria-label="\(title)">
    <title>\(title)</title>
    \(body)
    </svg>
    """
}

func write(_ name: String, _ content: String) throws {
    try content.write(to: directory.appendingPathComponent(name), atomically: true, encoding: .utf8)
}

let textScale: CGFloat = 70 / bounds.height
let headerWidth = Int(ceil(bounds.width * textScale + 186))
func header(_ foreground: String, _ accent: String) -> String {
    let transform = "translate(168 37) scale(\(number(textScale))) translate(\(number(-bounds.minX)) \(number(-bounds.minY)))"
    return "<g transform=\"translate(18 24) scale(0.235)\">\(mark(foreground, accent))</g><path fill=\"\(foreground)\" transform=\"\(transform)\" d=\"\(outline)\"/>"
}

let variants = [
    ("colour", charcoal, orange),
    ("dark", light, orange),
    ("black", "#000000", "#000000"),
    ("white", "#FFFFFF", "#FFFFFF")
]
for (name, foreground, accent) in variants {
    try write("symbol-\(name).svg", svg("typokiller symbol", "-32 -24 456 456", 512, 512, mark(foreground, accent)))
    try write("header-\(name).svg", svg("typokiller", "0 0 \(headerWidth) 144", headerWidth, 144, header(foreground, accent)))
}

let icon = "<rect width=\"512\" height=\"512\" rx=\"104\" fill=\"\(charcoal)\"/><g transform=\"translate(76 68) scale(0.91)\">\(mark(light, orange))</g>"
try write("app-icon.svg", svg("typokiller icon", "0 0 512 512", 512, 512, icon))
try write("favicon.svg", svg("typokiller icon", "0 0 512 512", 32, 32, icon))

var preview = "<rect width=\"1100\" height=\"900\" fill=\"\(light)\"/>"
preview += "<text x=\"50\" y=\"58\" font-family=\"sans-serif\" font-size=\"24\" fill=\"\(charcoal)\">typokiller / C / final assets</text>"
preview += "<g transform=\"translate(80 110) scale(0.7)\">\(mark(charcoal, orange))</g>"
preview += "<rect x=\"565\" y=\"90\" width=\"485\" height=\"350\" rx=\"18\" fill=\"\(charcoal)\"/>"
preview += "<g transform=\"translate(660 110) scale(0.7)\">\(mark(light, orange))</g>"
preview += "<g transform=\"translate(45 470)\">\(header(charcoal, orange))</g>"
preview += "<rect x=\"40\" y=\"640\" width=\"1020\" height=\"160\" rx=\"16\" fill=\"\(charcoal)\"/>"
preview += "<g transform=\"translate(45 648)\">\(header(light, orange))</g>"
preview += "<text x=\"50\" y=\"860\" font-family=\"sans-serif\" font-size=\"18\" fill=\"\(charcoal)\">Charcoal \(charcoal) / Orange \(orange) / All lettering stored as outlines</text>"
try write("preview.svg", svg("typokiller branding preview", "0 0 1100 900", 1100, 900, preview))

func run(_ arguments: [String]) throws {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
    process.arguments = arguments
    try process.run()
    process.waitUntilExit()
    precondition(process.terminationStatus == 0, "Export failed: \(arguments)")
}

for (name, _, _) in variants {
    for kind in ["symbol", "header"] {
        let base = directory.appendingPathComponent("\(kind)-\(name)").path
        try run(["magick", "-background", "none", "-density", "192", base + ".svg", base + ".png"])
    }
}
let app = directory.appendingPathComponent("app-icon.svg").path
for size in [180, 192, 512] {
    try run(["magick", "-background", "none", app, "-resize", "\(size)x\(size)", directory.appendingPathComponent("app-icon-\(size).png").path])
}
try run(["magick", "-background", "none", app, "-define", "icon:auto-resize=64,48,32,16", directory.appendingPathComponent("favicon.ico").path])
try run(["magick", "-font", "/System/Library/Fonts/Supplemental/Courier New.ttf", directory.appendingPathComponent("preview.svg").path, directory.appendingPathComponent("preview.png").path])
print("Created branding assets in \(directory.path)")
