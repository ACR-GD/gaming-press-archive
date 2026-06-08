import Foundation
import Vision
import CoreGraphics
import ImageIO

// MARK: - Output Structures

struct BoundingBox: Codable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

struct TextBlock: Codable {
    let text: String
    let confidence: Float
    let bbox: BoundingBox
    let orientation: String  // "horizontal" | "vertical" | "unknown"
}

struct PageOCRResult: Codable {
    let source: String
    let imageWidth: Int
    let imageHeight: Int
    let ocrBlocks: [TextBlock]
    let fullText: String
    let blockCount: Int
    let averageConfidence: Double
    let processedAt: String
    let error: String?
}

// MARK: - Helpers

func isoNow() -> String {
    let fmt = ISO8601DateFormatter()
    fmt.formatOptions = [.withInternetDateTime]
    return fmt.string(from: Date())
}

func inferOrientation(from observation: VNRecognizedTextObservation) -> String {
    let box = observation.boundingBox
    // Aspect ratio heuristic: tall and narrow = vertical Japanese text
    let aspect = box.width / box.height
    if aspect < 0.4 { return "vertical" }
    if aspect > 2.0 { return "horizontal" }
    return "horizontal"
}

// MARK: - Core OCR

func runOCR(imagePath: String) -> PageOCRResult {
    let url = URL(fileURLWithPath: imagePath)
    let filename = url.lastPathComponent

    // Load image
    guard let imageSource = CGImageSourceCreateWithURL(url as CFURL, nil),
          let cgImage = CGImageSourceCreateImageAtIndex(imageSource, 0, nil) else {
        return PageOCRResult(
            source: filename, imageWidth: 0, imageHeight: 0,
            ocrBlocks: [], fullText: "", blockCount: 0,
            averageConfidence: 0, processedAt: isoNow(),
            error: "Failed to load image: \(imagePath)"
        )
    }

    let imageWidth = cgImage.width
    let imageHeight = cgImage.height

    // Configure Vision request
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    // Japanese + English — covers all Famitsu, Dengeki, Beep! content
    // Also handles romanized Japanese game titles perfectly
    request.recognitionLanguages = ["ja", "en"]
    request.minimumTextHeight = 0.01  // catch small text like scores and captions

    // Run synchronously
    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    var blocks: [TextBlock] = []
    var allLines: [String] = []

    do {
        try handler.perform([request])
    } catch {
        return PageOCRResult(
            source: filename, imageWidth: imageWidth, imageHeight: imageHeight,
            ocrBlocks: [], fullText: "", blockCount: 0,
            averageConfidence: 0, processedAt: isoNow(),
            error: "Vision error: \(error.localizedDescription)"
        )
    }

    guard let observations = request.results else {
        return PageOCRResult(
            source: filename, imageWidth: imageWidth, imageHeight: imageHeight,
            ocrBlocks: [], fullText: "", blockCount: 0,
            averageConfidence: 0, processedAt: isoNow(),
            error: nil
        )
    }

    for obs in observations {
        guard let candidate = obs.topCandidates(1).first else { continue }
        let text = candidate.string
        let confidence = candidate.confidence

        // Vision bounding boxes are normalized (0–1), origin at bottom-left
        // Convert to top-left origin for consistency
        let vBox = obs.boundingBox
        let bbox = BoundingBox(
            x: vBox.origin.x,
            y: 1.0 - vBox.origin.y - vBox.height,  // flip Y
            width: vBox.width,
            height: vBox.height
        )

        let orientation = inferOrientation(from: obs)
        blocks.append(TextBlock(text: text, confidence: confidence, bbox: bbox, orientation: orientation))
        allLines.append(text)
    }

    // Sort blocks top-to-bottom, left-to-right (reading order approximation)
    // For vertical Japanese, this is top-to-bottom, right-to-left — we keep it simple
    // and let the Phase 1 AI reassemble reading order from bounding boxes
    let sorted = blocks.sorted {
        if abs($0.bbox.y - $1.bbox.y) > 0.02 {
            return $0.bbox.y < $1.bbox.y
        }
        return $0.bbox.x < $1.bbox.x
    }

    let fullText = sorted.map { $0.text }.joined(separator: "\n")
    let avgConf = sorted.isEmpty ? 0.0 : Double(sorted.map { $0.confidence }.reduce(0, +)) / Double(sorted.count)

    return PageOCRResult(
        source: filename,
        imageWidth: imageWidth,
        imageHeight: imageHeight,
        ocrBlocks: sorted,
        fullText: fullText,
        blockCount: sorted.count,
        averageConfidence: avgConf,
        processedAt: isoNow(),
        error: nil
    )
}

// MARK: - Main Entry Point

func main() {
    let args = CommandLine.arguments

    guard args.count >= 2 else {
        fputs("Usage: ocr_tool <image_path> [<image_path> ...]\n", stderr)
        fputs("       Outputs JSON array to stdout.\n", stderr)
        exit(1)
    }

    let imagePaths = Array(args.dropFirst())

    if imagePaths.count == 1 {
        // Single page → output single JSON object
        let result = runOCR(imagePath: imagePaths[0])
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .withoutEscapingSlashes]
        encoder.keyEncodingStrategy = .convertToSnakeCase
        if let data = try? encoder.encode(result),
           let json = String(data: data, encoding: .utf8) {
            print(json)
        }
    } else {
        // Multiple pages → output JSON array
        var results: [PageOCRResult] = []
        for path in imagePaths {
            fputs("OCR: \(URL(fileURLWithPath: path).lastPathComponent)\n", stderr)
            results.append(runOCR(imagePath: path))
        }
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .withoutEscapingSlashes]
        encoder.keyEncodingStrategy = .convertToSnakeCase
        if let data = try? encoder.encode(results),
           let json = String(data: data, encoding: .utf8) {
            print(json)
        }
    }
}

main()
