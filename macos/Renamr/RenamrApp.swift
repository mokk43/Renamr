import Sparkle
import SwiftUI

@main
struct RenamrApp: App {
    @StateObject private var appLog: AppLog
    @StateObject private var nameEditor: NameEditorViewModel
    @StateObject private var documentViewModel: DocumentViewModel
    @StateObject private var settingsViewModel: SettingsViewModel
    @StateObject private var autocompleteSource: NameAutocompleteSource
    @StateObject private var csvImportViewModel: CSVImportViewModel

    private let updaterController: SPUStandardUpdaterController

    init() {
        let service = RenamrService()
        _appLog = StateObject(wrappedValue: AppLog())
        _nameEditor = StateObject(wrappedValue: NameEditorViewModel())
        _documentViewModel = StateObject(wrappedValue: DocumentViewModel(service: service))
        _settingsViewModel = StateObject(wrappedValue: SettingsViewModel(service: service))
        _autocompleteSource = StateObject(wrappedValue: NameAutocompleteSource(service: service))
        _csvImportViewModel = StateObject(wrappedValue: CSVImportViewModel(service: service))
        updaterController = SPUStandardUpdaterController(
            startingUpdater: true,
            updaterDelegate: nil,
            userDriverDelegate: nil
        )
    }

    var body: some Scene {
        WindowGroup {
            MainView(
                documentViewModel: documentViewModel,
                settingsViewModel: settingsViewModel,
                nameEditor: nameEditor,
                appLog: appLog,
                autocompleteSource: autocompleteSource,
                csvImportViewModel: csvImportViewModel
            )
        }
        Settings {
            SettingsView(viewModel: settingsViewModel)
        }
        .commands {
            CommandGroup(after: .appInfo) {
                Button("Check for Updates…") {
                    updaterController.checkForUpdates(nil)
                }
            }
        }
    }
}
