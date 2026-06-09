import Foundation
import os

enum PythonRuntimeError: LocalizedError {
    case executableNotFound
    case processFailed(String)
    case invalidUTF8

    var errorDescription: String? {
        switch self {
        case .executableNotFound:
            return "No usable Python executable was found for Renamr."
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
    private let runtime: Result<RuntimeLayout, PythonRuntimeError>

    init() {
        runtime = RuntimeLayout.discover()
        switch runtime {
        case let .success(layout):
            logger.info("Using Python executable at \(layout.executableURL.path, privacy: .public)")
        case let .failure(error):
            logger.error("Python runtime discovery failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func dispatch(
        method: String,
        payloadJSON: String,
        token: String?,
        progressHandler: ((String) -> Void)? = nil
    ) throws -> String {
        logger.debug("Dispatching Python method \(method, privacy: .public)")
        return try queue.sync {
            let runtimeLayout = try runtime.get()
            let process = Process()
            process.executableURL = runtimeLayout.executableURL
            process.arguments = ["-c", Self.bootstrapScript]

            var environment = runtimeLayout.configuredEnvironment(from: ProcessInfo.processInfo.environment)
            environment["RENAMR_METHOD"] = method
            environment["RENAMR_PAYLOAD"] = payloadJSON
            if let token {
                environment["RENAMR_TOKEN"] = token
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

private struct RuntimeLayout {
    let executableURL: URL
    let pythonHome: String?
    let pythonPathEntries: [String]

    func configuredEnvironment(from base: [String: String]) -> [String: String] {
        var environment = base
        if let pythonHome {
            environment["PYTHONHOME"] = pythonHome
        }
        var entries = pythonPathEntries
        if let existing = environment["PYTHONPATH"], !existing.isEmpty {
            entries.append(contentsOf: existing.split(separator: ":").map(String.init))
        }
        let deduped = RuntimeLayout.uniqueEntries(entries)
        if !deduped.isEmpty {
            environment["PYTHONPATH"] = deduped.joined(separator: ":")
        }
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONUTF8"] = "1"
        return environment
    }

    static func discover() -> Result<RuntimeLayout, PythonRuntimeError> {
        let environment = ProcessInfo.processInfo.environment
        if let override = environment["RENAMR_PYTHON_EXECUTABLE"], isExecutable(override) {
            let overrideHome = environment["RENAMR_PYTHON_HOME"]
            let overridePath = environment["RENAMR_PYTHONPATH"]?
                .split(separator: ":")
                .map(String.init) ?? []
            return .success(RuntimeLayout(
                executableURL: URL(fileURLWithPath: override),
                pythonHome: overrideHome,
                pythonPathEntries: uniqueEntries(overridePath)
            ))
        }

        let runtimeRoot = bundledRuntimeRoot()
        let frameworkRoot = bundledFrameworkRoot()
        let devRoot = developmentRoot()

        if let runtimeRoot {
            let packagedExecutable = runtimeRoot.appendingPathComponent("bin/python3", isDirectory: false)
            guard isExecutable(packagedExecutable.path) else {
                return .failure(.executableNotFound)
            }

            return .success(layout(
                executableURL: packagedExecutable,
                runtimeRoot: runtimeRoot,
                devRoot: devRoot
            ))
        }

        let executableCandidates = [
            frameworkRoot?.appendingPathComponent("bin/python3", isDirectory: false),
            URL(fileURLWithPath: "/usr/bin/python3"),
            URL(fileURLWithPath: "/opt/homebrew/bin/python3"),
        ].compactMap { $0 }

        guard let executable = executableCandidates.first(where: { isExecutable($0.path) }) else {
            return .failure(.executableNotFound)
        }

        return .success(layout(
            executableURL: executable,
            runtimeRoot: nil,
            devRoot: devRoot
        ))
    }

    private static func layout(
        executableURL: URL,
        runtimeRoot: URL?,
        devRoot: URL?
    ) -> RuntimeLayout {
        let pythonHome: String?
        if let runtimeRoot {
            let stdlibPath = runtimeRoot.appendingPathComponent("python-stdlib", isDirectory: true).path
            pythonHome = FileManager.default.fileExists(atPath: stdlibPath) ? stdlibPath : nil
        } else {
            pythonHome = nil
        }

        var pythonPathEntries: [String] = []
        if let runtimeRoot {
            if FileManager.default.fileExists(atPath: runtimeRoot.path) {
                pythonPathEntries.append(runtimeRoot.path)
            }
            let appPackages = runtimeRoot.appendingPathComponent("app_packages", isDirectory: true).path
            if FileManager.default.fileExists(atPath: appPackages) {
                pythonPathEntries.append(appPackages)
            }
        }
        if let devRoot {
            pythonPathEntries.append(devRoot.path)
        }

        return RuntimeLayout(
            executableURL: executableURL,
            pythonHome: pythonHome,
            pythonPathEntries: uniqueEntries(pythonPathEntries)
        )
    }

    private static func bundledRuntimeRoot() -> URL? {
        guard let resourceURL = Bundle.main.resourceURL else {
            return nil
        }
        let candidate = resourceURL.appendingPathComponent("python", isDirectory: true)
        return FileManager.default.fileExists(atPath: candidate.path) ? candidate : nil
    }

    private static func bundledFrameworkRoot() -> URL? {
        guard let privateFrameworksURL = Bundle.main.privateFrameworksURL else {
            return nil
        }
        let frameworkRoot = privateFrameworksURL
            .appendingPathComponent("Python.framework", isDirectory: true)
            .appendingPathComponent("Versions/Current", isDirectory: true)
        return FileManager.default.fileExists(atPath: frameworkRoot.path) ? frameworkRoot : nil
    }

    private static func developmentRoot() -> URL? {
        var startingPoints: [URL] = [
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath, isDirectory: true),
        ]
        if let resourceURL = Bundle.main.resourceURL {
            startingPoints.append(resourceURL)
        }

        for start in startingPoints {
            var candidate = start
            for _ in 0 ..< 12 {
                let pyproject = candidate.appendingPathComponent("pyproject.toml", isDirectory: false)
                let txtProcess = candidate.appendingPathComponent("txt_process", isDirectory: true)
                if FileManager.default.fileExists(atPath: pyproject.path),
                   FileManager.default.fileExists(atPath: txtProcess.path)
                {
                    return candidate
                }
                let parent = candidate.deletingLastPathComponent()
                if parent.path == candidate.path {
                    break
                }
                candidate = parent
            }
        }

        return nil
    }

    private static func isExecutable(_ path: String) -> Bool {
        FileManager.default.isExecutableFile(atPath: path)
    }

    private static func uniqueEntries(_ values: [String]) -> [String] {
        var seen = Set<String>()
        var result: [String] = []
        for value in values where !value.isEmpty {
            if seen.insert(value).inserted {
                result.append(value)
            }
        }
        return result
    }
}
