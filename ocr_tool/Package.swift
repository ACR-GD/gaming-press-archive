// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "ocr_tool",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "ocr_tool",
            path: "Sources/ocr_tool",
            swiftSettings: [
                .unsafeFlags(["-strict-concurrency=minimal"])
            ]
        )
    ]
)
