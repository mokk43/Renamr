import Foundation
import RenamrShared

@MainActor
final class DocumentViewModel: ObservableObject {
    enum AppStatus: Equatable {
        case idle
        case loading
        case extracting
        case replacing
        case normalizing
        case cancelling
        case failed(String)
    }

    @Published var document: DocumentDescriptorDTO?
    @Published var status: AppStatus = .idle
    @Published var progress: ProgressEventDTO?
    @Published var isBusy = false
    @Published var outputPath: String?
    @Published var alternateDirectoryRequired = false

    private let service: RenamrService
    private var extractionTask: Task<Void, Never>?
    private var lastMappings: [String: String] = [:]

    init(service: RenamrService) {
        self.service = service
    }

    func openDocument(url: URL, appLog: AppLog) async {
        status = .loading
        isBusy = true
        defer { isBusy = false }
        do {
            let loaded = try await service.loadDocument(at: url)
            document = loaded
            status = .idle
            outputPath = nil
            appLog.log("Loaded \(loaded.path)")
        } catch {
            status = .failed(error.localizedDescription)
            appLog.log("Load failed: \(error.localizedDescription)", level: "error")
        }
    }

    func extractNames(
        config: ConfigDTO,
        apiKey: String,
        nameEditor: NameEditorViewModel,
        appLog: AppLog
    ) {
        guard let document else { return }
        extractionTask?.cancel()
        status = .extracting
        isBusy = true
        progress = nil

        extractionTask = Task { [weak self] in
            guard let self else { return }
            do {
                let stream = try await service.extractNames(
                    documentPath: document.path,
                    config: config,
                    apiKey: apiKey
                )
                for try await event in stream {
                    progress = event
                    if let detail = event.detail {
                        appLog.log(detail)
                    }
                    if let final = event.extractionResult {
                        nameEditor.setRows(namePairs: final.namePairs, counts: final.counts)
                    }
                }
                status = .idle
            } catch {
                if Task.isCancelled {
                    status = .idle
                } else {
                    status = .failed(error.localizedDescription)
                    appLog.log("Extract failed: \(error.localizedDescription)", level: "error")
                }
            }
            isBusy = false
        }
    }

    func cancelExtraction() async {
        status = .cancelling
        extractionTask?.cancel()
        extractionTask = nil
        isBusy = false
        status = .idle
    }

    func replaceAndExport(
        mappings: [String: String],
        appLog: AppLog,
        outputPath: String? = nil
    ) async {
        guard let document else { return }
        status = .replacing
        isBusy = true
        defer { isBusy = false }
        do {
            let result = try await service.replaceAndExport(
                documentPath: document.path,
                mappings: mappings,
                outputPath: outputPath
            )
            self.outputPath = result.outputPath
            self.lastMappings = mappings
            alternateDirectoryRequired = false
            status = .idle
            appLog.log("Replace complete: \(result.outputPath)")
        } catch let error as RenamrServiceError {
            if error == .permissionDenied {
                alternateDirectoryRequired = true
            }
            status = .failed(error.localizedDescription)
            appLog.log("Replace failed: \(error.localizedDescription)", level: "error")
        } catch {
            status = .failed(error.localizedDescription)
            appLog.log("Replace failed: \(error.localizedDescription)", level: "error")
        }
    }

    func retryReplaceAtSelectedPath(path: String, appLog: AppLog) async {
        alternateDirectoryRequired = false
        await replaceAndExport(mappings: lastMappings, appLog: appLog, outputPath: path)
    }

    func normalizeLayout(appLog: AppLog) async {
        guard let document, document.kind == .txt else { return }
        let sourceURL = URL(fileURLWithPath: document.path)
        let outputURL = sourceURL
            .deletingPathExtension()
            .appendingPathExtension("normalized.txt")
        status = .normalizing
        isBusy = true
        defer { isBusy = false }
        do {
            try await service.normalizeLayout(inputPath: sourceURL.path, outputPath: outputURL.path)
            appLog.log("Normalized layout: \(outputURL.path)")
            status = .idle
        } catch {
            status = .failed(error.localizedDescription)
            appLog.log("Normalize failed: \(error.localizedDescription)", level: "error")
        }
    }
}
