import AppKit
import Foundation

enum AlternateDirectoryPicker {
    @MainActor
    static func pickOutputPath(defaultFilename: String) -> String? {
        let panel = NSSavePanel()
        panel.canCreateDirectories = true
        panel.nameFieldStringValue = defaultFilename
        panel.title = "Choose export destination"
        let response = panel.runModal()
        guard response == .OK else { return nil }
        return panel.url?.path
    }
}
