import Foundation
import RenamrShared
import os

final class RenamrServiceHost: NSObject, NSXPCListenerDelegate, RenamrServiceProtocol {
    private let logger = Logger(subsystem: "dev.renamr.app", category: "PythonService")
    private let runtime = PythonRuntime()

    func listener(_ listener: NSXPCListener, shouldAcceptNewConnection newConnection: NSXPCConnection)
        -> Bool
    {
        newConnection.exportedInterface = NSXPCInterface(with: RenamrServiceProtocol.self)
        newConnection.exportedObject = self
        newConnection.resume()
        logger.info("Accepted XPC connection")
        return true
    }

    func loadDocument(payload: Data, reply: @escaping (Data?, NSError?) -> Void) {
        runBridgeDataCall(method: "loadDocument", payload: payload, token: nil, reply: reply)
    }

    func extractNames(payload: Data, token: String, reply: @escaping (Data?, NSError?) -> Void) {
        let progressProxy = NSXPCConnection.current()?
            .remoteObjectProxyWithErrorHandler { [logger] error in
                logger.error("Progress callback failed: \(error.localizedDescription, privacy: .public)")
            } as? RenamrProgressProtocol
        runBridgeDataCall(
            method: "extractNames",
            payload: payload,
            token: token,
            progressProxy: progressProxy,
            reply: reply
        )
    }

    func replaceAndExport(payload: Data, reply: @escaping (Data?, NSError?) -> Void) {
        runBridgeDataCall(method: "replaceAndExport", payload: payload, token: nil, reply: reply)
    }

    func readSettings(reply: @escaping (Data?, NSError?) -> Void) {
        runBridgeDataCall(method: "readSettings", payload: Data("{}".utf8), token: nil, reply: reply)
    }

    func writeSettings(payload: Data, reply: @escaping (NSError?) -> Void) {
        do {
            _ = try callBridge(method: "writeSettings", payload: payload, token: nil)
            reply(nil)
        } catch {
            reply(asNSError(error))
        }
    }

    func normalizeLayout(payload: Data, reply: @escaping (NSError?) -> Void) {
        do {
            _ = try callBridge(method: "normalizeLayout", payload: payload, token: nil)
            reply(nil)
        } catch {
            reply(asNSError(error))
        }
    }

    func loadNameCache(reply: @escaping ([String]?, NSError?) -> Void) {
        do {
            let data = try callBridge(method: "loadNameCache", payload: Data("{}".utf8), token: nil)
            let payload = try JSONDecoder().decode(NameCacheDTO.self, from: data)
            reply(payload.names, nil)
        } catch {
            reply(nil, asNSError(error))
        }
    }

    func saveNameCache(names: [String], reply: @escaping ([String]?, NSError?) -> Void) {
        do {
            let data = try JSONEncoder().encode(SaveNameCacheRequestDTO(names: names))
            let response = try callBridge(method: "saveNameCache", payload: data, token: nil)
            let payload = try JSONDecoder().decode(NameCacheDTO.self, from: response)
            reply(payload.names, nil)
        } catch {
            reply(nil, asNSError(error))
        }
    }

    func commitImportedPairs(payload: Data, reply: @escaping (Data?, NSError?) -> Void) {
        runBridgeDataCall(method: "commitImportedPairs", payload: payload, token: nil, reply: reply)
    }

    func cancel(token: String, reply: @escaping () -> Void) {
        let request = ["token": token]
        let payload = try? JSONSerialization.data(withJSONObject: request)
        _ = try? callBridge(method: "cancel", payload: payload ?? Data("{}".utf8), token: token)
        reply()
    }

    func ping(reply: @escaping (String) -> Void) {
        do {
            let data = try callBridge(method: "ping", payload: Data("{}".utf8), token: nil)
            if let decoded = try? JSONSerialization.jsonObject(with: data) as? [String: String],
               let version = decoded["python_version"]
            {
                reply(version)
            } else {
                reply("unknown")
            }
        } catch {
            reply("error")
        }
    }

    private func runBridgeDataCall(
        method: String,
        payload: Data,
        token: String?,
        progressProxy: RenamrProgressProtocol? = nil,
        reply: @escaping (Data?, NSError?) -> Void
    ) {
        do {
            let data = try callBridge(
                method: method,
                payload: payload,
                token: token,
                progressHandler: { [self] eventJSON in
                    emitProgressEvent(eventJSON, to: progressProxy)
                }
            )
            reply(data, nil)
        } catch {
            reply(nil, asNSError(error))
        }
    }

    private func callBridge(
        method: String,
        payload: Data,
        token: String?,
        progressHandler: ((String) -> Void)? = nil
    ) throws -> Data {
        guard let payloadString = String(data: payload, encoding: .utf8) else {
            throw RenamrServiceError.pythonRaised.asNSError(
                message: "Invalid Python bridge payload encoding."
            )
        }
        let response = try runtime.dispatch(
            method: method,
            payloadJSON: payloadString,
            token: token,
            progressHandler: progressHandler
        )
        let envelopeObject = try decodeEnvelopeObject(from: response)
        guard let ok = envelopeObject["ok"] as? Bool else {
            throw RenamrServiceError.pythonRaised.asNSError(
                message: "The Python bridge response is missing an `ok` field."
            )
        }
        if ok {
            let resultObject = envelopeObject["result"] ?? NSNull()
            return try JSONSerialization.data(withJSONObject: resultObject)
        }

        let code = envelopeObject["error"] as? String ?? "pythonRaised"
        let message = (envelopeObject["message"] as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedMessage = (message?.isEmpty == false)
            ? message!
            : RenamrServiceError.fromBridgeCode(code).localizedDescription
        throw RenamrServiceError.fromBridgeCode(code).asNSError(message: resolvedMessage)
    }

    private func decodeEnvelopeObject(from response: String) throws -> [String: Any] {
        if let object = jsonObject(from: response), object["ok"] as? Bool != nil {
            return object
        }

        if let candidate = extractJSONObjectCandidate(from: response),
           let object = jsonObject(from: candidate), object["ok"] as? Bool != nil
        {
            logger.warning("Recovered Python bridge response envelope from surrounding output")
            return object
        }

        throw RenamrServiceError.pythonRaised.asNSError(
            message: "The Python bridge returned an invalid response envelope."
        )
    }

    private func jsonObject(from text: String) -> [String: Any]? {
        guard
            let data = text.data(using: .utf8),
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return nil
        }
        return object
    }

    private func extractJSONObjectCandidate(from text: String) -> String? {
        guard
            let start = text.firstIndex(of: "{"),
            let end = text.lastIndex(of: "}"),
            start <= end
        else {
            return nil
        }
        return String(text[start ... end])
    }

    private func emitProgressEvent(_ eventJSON: String, to proxy: RenamrProgressProtocol?) {
        guard
            let data = eventJSON.data(using: .utf8),
            let envelope = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let type = envelope["type"] as? String,
            let payload = envelope["payload"] as? [String: Any]
        else {
            return
        }
        switch type {
        case "progress":
            if let payloadData = try? JSONSerialization.data(withJSONObject: payload) {
                proxy?.progress(payload: payloadData)
            }
        case "chunk_names":
            let names = payload["names"] as? [String] ?? []
            proxy?.chunkNames(names: names)
        case "chunk_error":
            let message = payload["message"] as? String ?? "Chunk error"
            proxy?.logMessage(message: message, level: "error")
        case "log":
            let message = payload["message"] as? String ?? ""
            let level = payload["level"] as? String ?? "info"
            proxy?.logMessage(message: message, level: level)
        default:
            break
        }
    }

    private func asNSError(_ error: Error) -> NSError {
        if let mapped = error as? RenamrServiceError {
            return mapped.asNSError()
        }
        let nsError = error as NSError
        if nsError.domain == RenamrServiceError.domain {
            return nsError
        }
        return RenamrServiceError.pythonRaised.asNSError(message: nsError.localizedDescription)
    }
}

let service = RenamrServiceHost()
let listener = NSXPCListener.service()
listener.delegate = service
listener.resume()
RunLoop.main.run()
