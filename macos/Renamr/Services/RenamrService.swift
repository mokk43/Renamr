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
        do {
            return try await withTimedResult(seconds: 10) { resolve in
                do {
                    let proxy = try self.serviceProxy(progressReceiver: nil) { error in
                        resolve(.failure(Self.mapConnectionError(error)))
                    }
                    proxy.ping { value in
                        resolve(.success(value))
                    }
                } catch {
                    resolve(.failure(error))
                }
            }
        } catch {
            if let serviceError = error as? RenamrServiceError,
               serviceError == .timedOut || serviceError == .serviceCrashed
            {
                supervisor.reset()
            }
            throw error
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
        try await callVoid(timeout: defaultTimeout) { proxy, reply in
            proxy.writeSettings(payload: payload, reply: reply)
        }
    }

    func normalizeLayout(inputPath: String, outputPath: String) async throws {
        let request = NormalizeRequestDTO(inputPath: inputPath, outputPath: outputPath)
        let payload = try encoder.encode(request)
        try await callVoid(timeout: defaultTimeout) { proxy, reply in
            proxy.normalizeLayout(payload: payload, reply: reply)
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
                    if let serviceError = error as? RenamrServiceError, serviceError == .timedOut {
                        await self.cancel(token: token)
                    }
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
        do {
            _ = try await withTimedResult(seconds: 5) { resolve in
                do {
                    let proxy = try self.serviceProxy(progressReceiver: nil) { _ in
                        resolve(.success(()))
                    }
                    proxy.cancel(token: token) {
                        resolve(.success(()))
                    }
                } catch {
                    resolve(.failure(error))
                }
            }
        } catch {
            supervisor.reset()
        }
    }

    private func serviceProxy(
        progressReceiver: RenamrProgressProtocol?,
        errorHandler: @escaping (NSError) -> Void
    ) throws -> RenamrServiceProtocol {
        let connection = supervisor.activeConnection(progressReceiver: progressReceiver)
        guard
            let proxy = connection.remoteObjectProxyWithErrorHandler({ error in
                errorHandler(error as NSError)
            }) as? RenamrServiceProtocol
        else {
            throw RenamrServiceError.serviceUnavailable
        }
        return proxy
    }

    private func callData(
        timeout: TimeInterval,
        progressReceiver: RenamrProgressProtocol?,
        _ call: @escaping (RenamrServiceProtocol, @escaping (Data?, NSError?) -> Void) -> Void
    ) async throws -> Data {
        if let progressReceiver {
            let proxy = try serviceProxy(progressReceiver: progressReceiver) { _ in }
            return try await withCheckedThrowingContinuation { continuation in
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

        do {
            return try await withTimedResult(seconds: timeout) { resolve in
                do {
                    let proxy = try self.serviceProxy(progressReceiver: nil) { error in
                        resolve(.failure(Self.mapConnectionError(error)))
                    }
                    call(proxy) { data, error in
                        if let error {
                            resolve(.failure(RenamrServiceError.fromNSError(error)))
                            return
                        }
                        guard let data else {
                            resolve(.failure(RenamrServiceError.pythonRaised))
                            return
                        }
                        resolve(.success(data))
                    }
                } catch {
                    resolve(.failure(error))
                }
            }
        } catch {
            if let serviceError = error as? RenamrServiceError,
               serviceError == .timedOut || serviceError == .serviceCrashed
            {
                supervisor.reset()
            }
            throw error
        }
    }

    private func callStringArray(
        timeout: TimeInterval,
        _ call: @escaping (RenamrServiceProtocol, @escaping ([String]?, NSError?) -> Void) -> Void
    ) async throws -> [String] {
        do {
            return try await withTimedResult(seconds: timeout) { resolve in
                do {
                    let proxy = try self.serviceProxy(progressReceiver: nil) { error in
                        resolve(.failure(Self.mapConnectionError(error)))
                    }
                    call(proxy) { values, error in
                        if let error {
                            resolve(.failure(RenamrServiceError.fromNSError(error)))
                            return
                        }
                        resolve(.success(values ?? []))
                    }
                } catch {
                    resolve(.failure(error))
                }
            }
        } catch {
            if let serviceError = error as? RenamrServiceError,
               serviceError == .timedOut || serviceError == .serviceCrashed
            {
                supervisor.reset()
            }
            throw error
        }
    }

    private func callVoid(
        timeout: TimeInterval,
        _ call: @escaping (RenamrServiceProtocol, @escaping (NSError?) -> Void) -> Void
    ) async throws {
        do {
            try await withTimedResult(seconds: timeout) { (resolve: @escaping (Result<Void, Error>) -> Void) in
                do {
                    let proxy = try self.serviceProxy(progressReceiver: nil) { error in
                        resolve(.failure(Self.mapConnectionError(error)))
                    }
                    call(proxy) { error in
                        if let error {
                            resolve(.failure(RenamrServiceError.fromNSError(error)))
                            return
                        }
                        resolve(.success(()))
                    }
                } catch {
                    resolve(.failure(error))
                }
            }
        } catch {
            if let serviceError = error as? RenamrServiceError,
               serviceError == .timedOut || serviceError == .serviceCrashed
            {
                supervisor.reset()
            }
            throw error
        }
    }

    private func withTimedResult<T: Sendable>(
        seconds: TimeInterval,
        operation: @escaping (@escaping (Result<T, Error>) -> Void) -> Void
    ) async throws -> T {
        try await withCheckedThrowingContinuation { continuation in
            let resolution = TimedResolutionBox(continuation: continuation)

            let nanoseconds = UInt64(max(seconds, 0) * 1_000_000_000)
            DispatchQueue.global(qos: .userInitiated).asyncAfter(
                deadline: .now() + .nanoseconds(Int(nanoseconds))
            ) {
                resolution.resolve(.failure(RenamrServiceError.timedOut))
            }

            operation { result in
                resolution.resolve(result)
            }
        }
    }

    private static func mapConnectionError(_ error: NSError) -> RenamrServiceError {
        let mapped = RenamrServiceError.fromNSError(error)
        if mapped == .pythonRaised {
            return .serviceCrashed
        }
        return mapped
    }
}

private final class TimedResolutionBox<T: Sendable>: @unchecked Sendable {
    private let lock = NSLock()
    private var resolved = false
    private let continuation: CheckedContinuation<T, Error>

    init(continuation: CheckedContinuation<T, Error>) {
        self.continuation = continuation
    }

    func resolve(_ result: Result<T, Error>) {
        lock.lock()
        defer { lock.unlock() }
        guard !resolved else { return }
        resolved = true
        switch result {
        case let .success(value):
            continuation.resume(returning: value)
        case let .failure(error):
            continuation.resume(throwing: error)
        }
    }
}
