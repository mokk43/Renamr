import Foundation
import RenamrShared

enum CSVParserError: Error, LocalizedError {
    case malformedQuotes

    var errorDescription: String? {
        switch self {
        case .malformedQuotes:
            return "Malformed CSV: unclosed quoted value."
        }
    }
}

enum CSVParser {
    static func parse(data: Data) throws -> [NamePairDTO] {
        guard let text = String(data: data, encoding: .utf8) else {
            return []
        }
        var rows: [NamePairDTO] = []
        for line in text.split(whereSeparator: \.isNewline) {
            let fields = try splitCSVLine(String(line))
            guard fields.count >= 2 else { continue }
            let source = fields[0].trimmingCharacters(in: .whitespacesAndNewlines)
            let target = fields[1].trimmingCharacters(in: .whitespacesAndNewlines)
            guard !source.isEmpty else { continue }
            rows.append(NamePairDTO(original: source, replacement: target))
        }
        return rows
    }

    private static func splitCSVLine(_ line: String) throws -> [String] {
        var fields: [String] = []
        var current = ""
        var inQuotes = false
        var iterator = line.makeIterator()
        while let char = iterator.next() {
            if char == "\"" {
                if inQuotes {
                    if let next = iterator.next() {
                        if next == "\"" {
                            current.append("\"")
                        } else {
                            inQuotes = false
                            if next == "," {
                                fields.append(current)
                                current = ""
                            } else {
                                current.append(next)
                            }
                        }
                    } else {
                        inQuotes = false
                    }
                } else {
                    inQuotes = true
                }
                continue
            }
            if char == "," && !inQuotes {
                fields.append(current)
                current = ""
                continue
            }
            current.append(char)
        }
        if inQuotes {
            throw CSVParserError.malformedQuotes
        }
        fields.append(current)
        return fields
    }
}
