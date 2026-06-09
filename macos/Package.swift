// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "RenamrMac",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "Renamr", targets: ["Renamr"]),
        .executable(name: "RenamrPythonService", targets: ["RenamrPythonService"]),
        .library(name: "RenamrShared", targets: ["RenamrShared"]),
    ],
    dependencies: [
        .package(url: "https://github.com/sparkle-project/Sparkle.git", from: "2.7.0"),
    ],
    targets: [
        .target(
            name: "RenamrShared",
            path: "Renamr/Services",
            exclude: [
                "ConnectionSupervisor.swift",
                "CSVParser.swift",
                "NameAutocompleteSource.swift",
                "ProgressReceiver.swift",
                "RenamrService.swift",
            ],
            sources: ["Codables.swift", "Errors.swift", "RenamrProtocols.swift"]
        ),
        .executableTarget(
            name: "Renamr",
            dependencies: [
                "RenamrShared",
                .product(name: "Sparkle", package: "Sparkle"),
            ],
            path: "Renamr",
            exclude: [
                "Resources/Info.plist",
                "Services/Codables.swift",
                "Services/Errors.swift",
                "Services/RenamrProtocols.swift",
            ],
            sources: [
                "RenamrApp.swift",
                "Services/ConnectionSupervisor.swift",
                "Services/CSVParser.swift",
                "Services/NameAutocompleteSource.swift",
                "Services/ProgressReceiver.swift",
                "Services/RenamrService.swift",
                "ViewModels/AppLog.swift",
                "ViewModels/CSVImportViewModel.swift",
                "ViewModels/DocumentViewModel.swift",
                "ViewModels/NameEditorViewModel.swift",
                "ViewModels/SettingsViewModel.swift",
                "Views/AlternateDirectoryPicker.swift",
                "Views/CSVImportSheet.swift",
                "Views/ExtractionProgressView.swift",
                "Views/LogPanel.swift",
                "Views/MainView.swift",
                "Views/NameEditorView.swift",
                "Views/NameRowView.swift",
                "Views/SettingsView.swift",
                "Views/StatusBar.swift",
            ],
            resources: [
                .copy("Renamr.entitlements"),
            ]
        ),
        .executableTarget(
            name: "RenamrPythonService",
            dependencies: ["RenamrShared"],
            path: "RenamrPythonService",
            exclude: [
                "Info.plist",
                "Bridging-Header.h",
            ],
            resources: [
                .copy("RenamrPythonService.entitlements"),
            ]
        ),
        .testTarget(
            name: "RenamrTests",
            dependencies: ["RenamrShared"],
            path: "Tests"
        ),
    ]
)
