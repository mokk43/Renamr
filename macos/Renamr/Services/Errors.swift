import Foundation

public enum RenamrServiceError: Int, LocalizedError, Sendable {
    case documentNotFound = 1
    case documentEncrypted = 2
    case epubParseFailed = 3
    case llmConfigInvalid = 4
    case cancelled = 5
    case pythonRaised = 6
    case serviceUnavailable = 7
    case timedOut = 8
    case serviceCrashed = 9
    case permissionDenied = 10

    public static let domain = "dev.renamr.service"

    public var errorDescription: String? {
        switch self {
        case .documentNotFound:
            return "Document not found."
        case .documentEncrypted:
            return "This EPUB is DRM-protected or encrypted."
        case .epubParseFailed:
            return "Could not parse EPUB content."
        case .llmConfigInvalid:
            return "LLM configuration is invalid."
        case .cancelled:
            return "Operation cancelled."
        case .pythonRaised:
            return "The Python service raised an unexpected error."
        case .serviceUnavailable:
            return "The extraction service is unavailable."
        case .timedOut:
            return "The request timed out."
        case .serviceCrashed:
            return "The extraction service stopped unexpectedly."
        case .permissionDenied:
            return "Permission denied for the selected output path."
        }
    }

    public var bridgeCode: String {
        switch self {
        case .documentNotFound:
            return "documentNotFound"
        case .documentEncrypted:
            return "documentEncrypted"
        case .epubParseFailed:
            return "epubParseFailed"
        case .llmConfigInvalid:
            return "llmConfigInvalid"
        case .cancelled:
            return "cancelled"
        case .pythonRaised:
            return "pythonRaised"
        case .serviceUnavailable:
            return "serviceUnavailable"
        case .timedOut:
            return "timedOut"
        case .serviceCrashed:
            return "serviceCrashed"
        case .permissionDenied:
            return "permissionDenied"
        }
    }

    public static func fromBridgeCode(_ code: String) -> RenamrServiceError {
        switch code {
        case "documentNotFound":
            return .documentNotFound
        case "documentEncrypted":
            return .documentEncrypted
        case "epubParseFailed":
            return .epubParseFailed
        case "llmConfigInvalid":
            return .llmConfigInvalid
        case "cancelled":
            return .cancelled
        case "serviceUnavailable":
            return .serviceUnavailable
        case "timedOut":
            return .timedOut
        case "serviceCrashed":
            return .serviceCrashed
        case "permissionDenied":
            return .permissionDenied
        default:
            return .pythonRaised
        }
    }

    public func asNSError(message: String? = nil) -> NSError {
        NSError(
            domain: Self.domain,
            code: rawValue,
            userInfo: [
                NSLocalizedDescriptionKey: message ?? errorDescription ?? "Renamr service error",
                "bridgeCode": bridgeCode,
            ]
        )
    }

    public static func fromNSError(_ error: NSError) -> RenamrServiceError {
        if error.domain == domain, let mapped = RenamrServiceError(rawValue: error.code) {
            return mapped
        }
        if let bridgeCode = error.userInfo["bridgeCode"] as? String {
            return fromBridgeCode(bridgeCode)
        }
        return .pythonRaised
    }
}
