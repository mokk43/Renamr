import Foundation
import RenamrShared

final class ProgressReceiver: NSObject, RenamrProgressProtocol {
    var onProgress: ((ProgressEventDTO) -> Void)?
    var onChunkNames: (([String]) -> Void)?
    var onLogMessage: ((String, String) -> Void)?

    private let decoder = JSONDecoder()

    func progress(payload: Data) {
        guard let event = try? decoder.decode(ProgressEventDTO.self, from: payload) else { return }
        onProgress?(event)
    }

    func chunkNames(names: [String]) {
        onChunkNames?(names)
    }

    func logMessage(message: String, level: String) {
        onLogMessage?(message, level)
    }
}
