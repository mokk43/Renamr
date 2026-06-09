import Foundation
import RenamrShared

actor RenamrService {
    private let supervisor = ConnectionSupervisor()
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()
    private let defaultTimeout: TimeInterval = 120

    init() {
        supervisor.onInterruption = {}
        supervisor.onInvalidation = {}
    }

    func ping() async throws -> String {
        let proxy = try serviceProxy(progressReceiver: nil)
        return try await withTimeout(seconds: 10) {
            try await withCheckedThrowingContinuation { continuation in
                proxy.ping { value in
                    continuation.resume(returning: value)
                }
            }
        }
    }

    func loadDocument(at url: URL) async throws -> DocumentDescriptorDTO {
        let request = LoadRequestDTO(path: url.path)
        let payload = try encoder.encode(request)
        let data = try await callData(timeout: defaultTimeout, progressReceiver: nil) { proxy, reply in
            proxy.loadDocument(payload: payload, reply: reply)
        }
        return try decoder.decode(DocumentDescriptorDTO.self, from: data)
    }

    func readSettings() async throws -> ConfigDTO {
        let data = try await callData(timeout: defaultTimeout, progressReceiver: nil) { proxy, reply in
            proxy.readSettings(reply: reply)
        }
        return try decoder.decode(ConfigDTO.self, from: data)
    }

    func writeSettings(_ config: ConfigDTO) async throws {
        let payload = try encoder.encode(config)
        let proxy = try serviceProxy(progressReceiver: nil)
        try await withTimeout(seconds: defaultTimeout) {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                proxy.writeSettings(payload: payload) { error in
                    if let error {
                        continuation.resume(throwing: RenamrServiceError.fromNSError(error))
                    } else {
                        continuation.resume(returning: ())
                    }
                }
            }
        }
    }

    func normalizeLayout(inputPath: String, outputPath: String) async throws {
        let request = NormalizeRequestDTO(inputPath: inputPath, outputPath: outputPath)
        let payload = try encoder.encode(request)
        let proxy = try serviceProxy(progressReceiver: nil)
        try await withTimeout(seconds: defaultTimeout) {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                proxy.normalizeLayout(payload: payload) { error in
                    if let error {
                        continuation.resume(throwing: RenamrServiceError.fromNSError(error))
                    } else {
                        continuation.resume(returning: ())
                    }
                }
            }
        }
    }

    func extractNames(
        documentPath: String,
        config: ConfigDTO,
        apiKey: String
    ) async throws -> AsyncThrowingStream<ProgressEventDTO, Error> {
        let token = UUID().uuidString
        let request = ExtractRequestDTO(documentPath: documentPath, config: config, apiKey: apiKey)
        let payload = try encoder.encode(request)
        let receiver = ProgressReceiver()

        return AsyncThrowingStream { continuation in
            receiver.onProgress = { event in
                continuation.yield(event)
            }
            receiver.onChunkNames = { names in
                continuation.yield(
                    ProgressEventDTO(
                        stage: "chunk_names",
                        current: 0,
                        total: 0,
                        detail: names.joined(separator: ", "),
                        runningNames: names
                    )
                )
            }
            receiver.onLogMessage = { message, level in
                continuation.yield(
                    ProgressEventDTO(
                        stage: level,
                        current: 0,
                        total: 0,
                        detail: message,
                        runningNames: []
                    )
                )
            }

            Task {
                do {
                    let data = try await self.callData(
                        timeout: self.defaultTimeout,
                        progressReceiver: receiver
                    ) { proxy, reply in
                        proxy.extractNames(payload: payload, token: token, reply: reply)
                    }
                    let result = try self.decoder.decode(ExtractionResultDTO.self, from: data)
                    continuation.yield(
                        ProgressEventDTO(
                            stage: "done",
                            current: result.namePairs.count,
                            total: result.namePairs.count,
                            detail: "Done",
                            runningNames: result.namePairs.map(\.original),
                            extractionResult: result
                        )
                    )
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in
                Task { await self.cancel(token: token) }
            }
        }
    }

    func replaceAndExport(
        documentPath: String,
        mappings: [String: String],
        outputPath: String?
    ) async throws -> ReplaceResultDTO {
        let request = ReplaceRequestDTO(
            documentPath: documentPath,
            mappings: mappings,
            outputPath: outputPath
        )
        let payload = try encoder.encode(request)
        let data = try await callData(timeout: defaultTimeout, progressReceiver: nil) { proxy, reply in
            proxy.replaceAndExport(payload: payload, reply: reply)
        }
        return try decoder.decode(ReplaceResultDTO.self, from: data)
    }

    func loadNameCache() async throws -> [String] {
        let values = try await callStringArray(timeout: defaultTimeout) { proxy, reply in
            proxy.loadNameCache(reply: reply)
        }
        return values
    }

    func saveNameCache(names: [String]) async throws -> [String] {
        let values = try await callStringArray(timeout: defaultTimeout) { proxy, reply in
            proxy.saveNameCache(names: names, reply: reply)
        }
        return values
    }

    func commitImportedPairs(request: CommitImportedPairsRequestDTO) async throws -> CommitImportedPairsResponseDTO {
        let payload = try encoder.encode(request)
        let data = try await callData(timeout: defaultTimeout, progressReceiver: nil) { proxy, reply in
            proxy.commitImportedPairs(payload: payload, reply: reply)
        }
        return try decoder.decode(CommitImportedPairsResponseDTO.self, from: data)
    }

    func cancel(token: String) async {
        guard let proxy = try? serviceProxy(progressReceiver: nil) else { return }
        await withCheckedContinuation { continuation in
            proxy.cancel(token: token) {
                continuation.resume()
            }
        }
    }

    private func serviceProxy(progressReceiver: RenamrProgressProtocol?) throws -> RenamrServiceProtocol {
        let connection = supervisor.activeConnection(progressReceiver: progressReceiver)
        guard let proxy = connection.remoteObjectProxyWithErrorHandler({ _ in }) as? RenamrServiceProtocol else {
            throw RenamrServiceError.serviceUnavailable
        }
        return proxy
    }

    private func callData(
        timeout: TimeInterval,
        progressReceiver: RenamrProgressProtocol?,
        _ call: @escaping (RenamrServiceProtocol, @escaping (Data?, NSError?) -> Void) -> Void
    ) async throws -> Data {
        let proxy = try serviceProxy(progressReceiver: progressReceiver)
        return try await withTimeout(seconds: timeout) {
            try await withCheckedThrowingContinuation { continuation in
                call(proxy) { data, error in
                    if let error {
                        continuation.resume(throwing: RenamrServiceError.fromNSError(error))
                        return
                    }
                    guard let data else {
                        continuation.resume(throwing: RenamrServiceError.pythonRaised)
                        return
                    }
                    continuation.resume(returning: data)
                }
            }
        }
    }

    private func callStringArray(
        timeout: TimeInterval,
        _ call: @escaping (RenamrServiceProtocol, @escaping ([String]?, NSError?) -> Void) -> Void
    ) async throws -> [String] {
        let proxy = try serviceProxy(progressReceiver: nil)
        return try await withTimeout(seconds: timeout) {
            try await withCheckedThrowingContinuation { continuation in
                call(proxy) { values, error in
                    if let error {
                        continuation.resume(throwing: RenamrServiceError.fromNSError(error))
                        return
                    }
                    continuation.resume(returning: values ?? [])
                }
            }
        }
    }

    private func withTimeout<T>(
        seconds: TimeInterval,
        operation: @escaping () async throws -> T
    ) async throws -> T {
        _ = seconds
        return try await operation()
    }
}
