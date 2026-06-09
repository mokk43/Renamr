import SwiftUI
import UniformTypeIdentifiers

struct MainView: View {
    @ObservedObject var documentViewModel: DocumentViewModel
    @ObservedObject var settingsViewModel: SettingsViewModel
    @ObservedObject var nameEditor: NameEditorViewModel
    @ObservedObject var appLog: AppLog
    @ObservedObject var autocompleteSource: NameAutocompleteSource
    @ObservedObject var csvImportViewModel: CSVImportViewModel

    @State private var showingFileImporter = false
    @State private var showingSettings = false
    @State private var showingCSVImport = false

    private var epubType: UTType {
        UTType(filenameExtension: "epub") ?? .data
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            toolbar
            ExtractionProgressView(progress: documentViewModel.progress)
            NameEditorView(viewModel: nameEditor, autocomplete: autocompleteSource)
            LogPanel(appLog: appLog)
            StatusBar(
                document: documentViewModel.document,
                status: documentViewModel.status,
                progress: documentViewModel.progress
            )
        }
        .padding()
        .frame(minWidth: 980, minHeight: 700)
        .fileImporter(
            isPresented: $showingFileImporter,
            allowedContentTypes: [.plainText, epubType]
        ) { result in
            Task {
                if case let .success(url) = result {
                    await documentViewModel.openDocument(url: url, appLog: appLog)
                } else if case let .failure(error) = result {
                    appLog.log("Open failed: \(error.localizedDescription)", level: "error")
                }
            }
        }
        .sheet(isPresented: $showingSettings) {
            SettingsView(viewModel: settingsViewModel)
        }
        .sheet(isPresented: $showingCSVImport) {
            if let path = documentViewModel.document?.path {
                CSVImportSheet(
                    viewModel: csvImportViewModel,
                    documentPath: path
                ) { rows in
                    nameEditor.setRows(importedRows: rows)
                }
            }
        }
    }

    private var toolbar: some View {
        HStack {
            Button("Open") {
                showingFileImporter = true
            }
            .keyboardShortcut("o", modifiers: .command)

            Button("Extract names") {
                documentViewModel.extractNames(
                    config: settingsViewModel.draft,
                    apiKey: settingsViewModel.draft.apiKey,
                    nameEditor: nameEditor,
                    appLog: appLog
                )
            }
            .disabled(documentViewModel.document == nil || documentViewModel.isBusy)

            Button("Import Names") {
                showingCSVImport = true
            }
            .disabled(documentViewModel.document == nil || documentViewModel.isBusy)
            .keyboardShortcut("i", modifiers: .command)

            Button("Replace / Export") {
                Task {
                    let mappings = nameEditor.editedMappings()
                    guard !mappings.isEmpty else {
                        appLog.log("No edited mappings to apply.", level: "warning")
                        return
                    }
                    await documentViewModel.replaceAndExport(mappings: mappings, appLog: appLog)
                    if documentViewModel.alternateDirectoryRequired,
                       let fallback = AlternateDirectoryPicker.pickOutputPath(
                           defaultFilename: defaultExportFilename()
                       )
                    {
                        await documentViewModel.retryReplaceAtSelectedPath(path: fallback, appLog: appLog)
                    }
                    await autocompleteSource.updateCache(with: nameEditor.nonEmptyReplacements())
                }
            }
            .disabled(documentViewModel.document == nil || documentViewModel.isBusy)
            .keyboardShortcut(.return, modifiers: [.command])

            if documentViewModel.document?.kind == .txt {
                Button("Normalize Layout") {
                    Task {
                        await documentViewModel.normalizeLayout(appLog: appLog)
                    }
                }
                .disabled(documentViewModel.document == nil || documentViewModel.isBusy)
            }

            if documentViewModel.isBusy {
                Button("Cancel") {
                    Task { await documentViewModel.cancelExtraction() }
                }
                .keyboardShortcut(.cancelAction)
            }

            Spacer()

            Button("Settings…") {
                showingSettings = true
            }
            .keyboardShortcut(",", modifiers: .command)
        }
    }

    private func defaultExportFilename() -> String {
        guard let path = documentViewModel.document?.path else { return "renamr_processed.txt" }
        let url = URL(fileURLWithPath: path)
        let stem = url.deletingPathExtension().lastPathComponent
        let ext = url.pathExtension
        return ext.isEmpty ? "\(stem)_processed" : "\(stem)_processed.\(ext)"
    }
}
