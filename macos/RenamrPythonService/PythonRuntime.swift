import Foundation
import os

enum PythonRuntimeError: LocalizedError {
    case processFailed(String)
    case invalidUTF8

    var errorDescription: String? {
        switch self {
        case let .processFailed(message):
            return message
        case .invalidUTF8:
            return "Python runtime returned non UTF-8 output."
        }
    }
}

final class PythonRuntime {
    private let logger = Logger(subsystem: "dev.renamr.app", category: "PythonRuntime")
    private let queue = DispatchQueue(label: "dev.renamr.python")
    private static let progressPrefix = "__RENAMR_PROGRESS__"
    private static let resultPrefix = "__RENAMR_RESULT__"

    func dispatch(
        method: String,
        payloadJSON: String,
        token: String?,
        progressHandler: ((String) -> Void)? = nil
    ) throws -> String {
        logger.debug("Dispatching Python method \(method, privacy: .public)")
        return try queue.sync {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
            process.arguments = ["-c", Self.bootstrapScript]

            var environment = ProcessInfo.processInfo.environment
            environment["RENAMR_METHOD"] = method
            environment["RENAMR_PAYLOAD"] = payloadJSON
            if let token {
                environment["RENAMR_TOKEN"] = token
            }
            if let resourceURL = Bundle.main.resourceURL {
                let bridgeRoot = resourceURL.path
                let existing = environment["PYTHONPATH"] ?? ""
                environment["PYTHONPATH"] = existing.isEmpty ? bridgeRoot : "\(bridgeRoot):\(existing)"
            }
            process.environment = environment

            let outputPipe = Pipe()
            let errorPipe = Pipe()
            process.standardOutput = outputPipe
            process.standardError = errorPipe

            var outputBuffer = Data()
            var resultPayload: String?
            let outputHandle = outputPipe.fileHandleForReading

            try process.run()
            while true {
                let chunk = outputHandle.availableData
                if chunk.isEmpty {
                    break
                }
                outputBuffer.append(chunk)
                Self.consumeLines(from: &outputBuffer) { line in
                    if line.hasPrefix(Self.progressPrefix) {
                        let event = String(line.dropFirst(Self.progressPrefix.count))
                        progressHandler?(event)
                    } else if line.hasPrefix(Self.resultPrefix) {
                        resultPayload = String(line.dropFirst(Self.resultPrefix.count))
                    }
                }
            }
            process.waitUntilExit()

            if !outputBuffer.isEmpty, let tail = String(data: outputBuffer, encoding: .utf8) {
                if tail.hasPrefix(Self.progressPrefix) {
                    let event = String(tail.dropFirst(Self.progressPrefix.count))
                    progressHandler?(event)
                } else if tail.hasPrefix(Self.resultPrefix) {
                    resultPayload = String(tail.dropFirst(Self.resultPrefix.count))
                }
            }

            let stderrData = errorPipe.fileHandleForReading.readDataToEndOfFile()
            guard process.terminationStatus == 0 else {
                let stderr = String(data: stderrData, encoding: .utf8) ?? "Unknown Python error"
                throw PythonRuntimeError.processFailed(stderr)
            }

            if let resultPayload {
                return resultPayload
            }
            guard let output = String(data: outputBuffer, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines), !output.isEmpty
            else {
                throw PythonRuntimeError.invalidUTF8
            }
            return output
        }
    }

    private static func consumeLines(from buffer: inout Data, handler: (String) -> Void) {
        while let newlineRange = buffer.range(of: Data([0x0A])) {
            let lineData = buffer.subdata(in: 0 ..< newlineRange.lowerBound)
            buffer.removeSubrange(0 ..< newlineRange.upperBound)
            guard let line = String(data: lineData, encoding: .utf8) else { continue }
            handler(line)
        }
    }

    private static let bootstrapScript = """
    import os
    from txt_process.macos_bridge.service import dispatch

    method = os.environ.get("RENAMR_METHOD", "")
    payload = os.environ.get("RENAMR_PAYLOAD", "{}")
    token = os.environ.get("RENAMR_TOKEN") or None
    def _progress(message):
        print("__RENAMR_PROGRESS__" + message, flush=True)

    callback = _progress if method == "extractNames" else None
    result = dispatch(method, payload, callback, token)
    print("__RENAMR_RESULT__" + result, flush=True)
    """
}
