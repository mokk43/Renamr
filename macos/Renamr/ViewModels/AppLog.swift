import Foundation

@MainActor
final class AppLog: ObservableObject {
    struct Entry: Identifiable, Sendable {
        let id = UUID()
        let timestamp: Date
        let level: String
        let message: String
    }

    @Published private(set) var entries: [Entry] = []

    private let maxEntries: Int
    private let sensitivePatterns: [NSRegularExpression]

    init(maxEntries: Int = 400) {
        self.maxEntries = maxEntries
        self.sensitivePatterns = [
            try! NSRegularExpression(pattern: #"Authorization:\s*\S+"#, options: [.caseInsensitive]),
            try! NSRegularExpression(pattern: #"\bsk-[A-Za-z0-9_\-]+\b"#),
        ]
    }

    func log(_ message: String, level: String = "info") {
        let redacted = redact(message)
        entries.append(Entry(timestamp: Date(), level: level, message: redacted))
        if entries.count > maxEntries {
            entries.removeFirst(entries.count - maxEntries)
        }
    }

    private func redact(_ input: String) -> String {
        var redacted = input
        for pattern in sensitivePatterns {
            let range = NSRange(redacted.startIndex..<redacted.endIndex, in: redacted)
            redacted = pattern.stringByReplacingMatches(
                in: redacted,
                options: [],
                range: range,
                withTemplate: "[REDACTED]"
            )
        }
        return redacted
    }
}
