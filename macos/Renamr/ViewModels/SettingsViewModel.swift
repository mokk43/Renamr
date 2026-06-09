import Foundation
import RenamrShared

@MainActor
final class SettingsViewModel: ObservableObject {
    @Published var draft: ConfigDTO = .default
    @Published var validationError: String?

    private let service: RenamrService
    private var sessionAPIKey: String = ""

    init(service: RenamrService) {
        self.service = service
    }

    func load() async {
        do {
            let loaded = try await service.readSettings()
            draft = loaded
            if !sessionAPIKey.isEmpty {
                draft.apiKey = sessionAPIKey
            }
        } catch {
            validationError = "Failed to load settings: \(error.localizedDescription)"
        }
    }

    func save() async throws {
        guard validate() else {
            throw RenamrServiceError.llmConfigInvalid
        }
        sessionAPIKey = draft.apiKey
        try await service.writeSettings(draft)
    }

    private func validate() -> Bool {
        validationError = nil
        if draft.promptTemplate.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            validationError = "Prompt template cannot be empty."
            return false
        }
        if draft.chunkMaxBytes > 16384 || draft.chunkMaxBytes <= 0 {
            validationError = "Chunk max bytes must be between 1 and 16384."
            return false
        }
        if draft.requestIntervalSeconds < 2.0 {
            validationError = "Request interval must be at least 2.0 seconds."
            return false
        }
        if draft.beginScanChunks < 1 || draft.scanInterval < 1 {
            validationError = "Scan values must be positive integers."
            return false
        }
        if draft.temperature < 0 || draft.temperature > 2 {
            validationError = "Temperature must be between 0.0 and 2.0."
            return false
        }
        return true
    }
}
