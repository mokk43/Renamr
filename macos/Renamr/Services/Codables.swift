import Foundation

public enum DocumentKindDTO: String, Codable, Sendable {
    case txt
    case epub
}

public struct LoadRequestDTO: Codable, Sendable {
    public var path: String

    public init(path: String) {
        self.path = path
    }
}

public struct DocumentDescriptorDTO: Codable, Sendable {
    public var path: String
    public var kind: DocumentKindDTO
    public var text: String
    public var displayInfo: String
    public var supportsNormalize: Bool
    public var encoding: String?

    public init(
        path: String,
        kind: DocumentKindDTO,
        text: String,
        displayInfo: String,
        supportsNormalize: Bool,
        encoding: String?
    ) {
        self.path = path
        self.kind = kind
        self.text = text
        self.displayInfo = displayInfo
        self.supportsNormalize = supportsNormalize
        self.encoding = encoding
    }

    public enum CodingKeys: String, CodingKey {
        case path
        case kind
        case text
        case displayInfo = "display_info"
        case supportsNormalize = "supports_normalize"
        case encoding
    }
}

public struct NamePairDTO: Codable, Sendable {
    public var original: String
    public var replacement: String

    public init(original: String, replacement: String) {
        self.original = original
        self.replacement = replacement
    }

    public enum CodingKeys: String, CodingKey {
        case original
        case replacement
    }

    private enum LegacyCodingKeys: String, CodingKey {
        case originalName = "original_name"
        case replacementName = "replacement_name"
        case name
        case value
    }

    public init(from decoder: Decoder) throws {
        if var unkeyed = try? decoder.unkeyedContainer() {
            let original = try unkeyed.decode(String.self)
            let replacement = (try? unkeyed.decode(String.self)) ?? ""
            self.init(original: original, replacement: replacement)
            return
        }

        if let single = try? decoder.singleValueContainer(),
           let original = try? single.decode(String.self)
        {
            self.init(original: original, replacement: "")
            return
        }

        if let keyed = try? decoder.container(keyedBy: CodingKeys.self),
           let original = try? keyed.decode(String.self, forKey: .original)
        {
            let replacement = (try? keyed.decode(String.self, forKey: .replacement)) ?? ""
            self.init(original: original, replacement: replacement)
            return
        }

        if let keyed = try? decoder.container(keyedBy: LegacyCodingKeys.self),
           let original = (try? keyed.decode(String.self, forKey: .originalName))
            ?? (try? keyed.decode(String.self, forKey: .name))
        {
            let replacement = (try? keyed.decode(String.self, forKey: .replacementName))
                ?? (try? keyed.decode(String.self, forKey: .value))
                ?? ""
            self.init(original: original, replacement: replacement)
            return
        }

        throw DecodingError.dataCorrupted(
            DecodingError.Context(
                codingPath: decoder.codingPath,
                debugDescription: "Unsupported name pair payload format."
            )
        )
    }

    public func encode(to encoder: Encoder) throws {
        var keyed = encoder.container(keyedBy: CodingKeys.self)
        try keyed.encode(original, forKey: .original)
        try keyed.encode(replacement, forKey: .replacement)
    }
}

public struct NameRowDTO: Codable, Sendable {
    public var originalName: String
    public var replacementName: String
    public var occurrenceCount: Int

    public init(originalName: String, replacementName: String, occurrenceCount: Int) {
        self.originalName = originalName
        self.replacementName = replacementName
        self.occurrenceCount = occurrenceCount
    }

    public enum CodingKeys: String, CodingKey {
        case originalName = "original_name"
        case replacementName = "replacement_name"
        case occurrenceCount = "occurrence_count"
    }
}

public struct ProgressEventDTO: Codable, Sendable {
    public var stage: String
    public var current: Int
    public var total: Int
    public var detail: String?
    public var runningNames: [String]
    public var extractionResult: ExtractionResultDTO?

    public enum CodingKeys: String, CodingKey {
        case stage
        case current
        case total
        case detail
        case runningNames = "running_names"
        case extractionResult = "extraction_result"
    }

    public init(
        stage: String,
        current: Int,
        total: Int,
        detail: String? = nil,
        runningNames: [String] = [],
        extractionResult: ExtractionResultDTO? = nil
    ) {
        self.stage = stage
        self.current = current
        self.total = total
        self.detail = detail
        self.runningNames = runningNames
        self.extractionResult = extractionResult
    }
}

public struct ExtractionResultDTO: Codable, Sendable {
    public var namePairs: [NamePairDTO]
    public var counts: [String: Int]
    public var errors: [String]

    public init(namePairs: [NamePairDTO], counts: [String: Int], errors: [String]) {
        self.namePairs = namePairs
        self.counts = counts
        self.errors = errors
    }

    public enum CodingKeys: String, CodingKey {
        case namePairs = "name_pairs"
        case counts
        case errors
    }

    public init(from decoder: Decoder) throws {
        if let single = try? decoder.singleValueContainer(),
           let names = try? single.decode([String].self)
        {
            self.init(
                namePairs: names.map { NamePairDTO(original: $0, replacement: "") },
                counts: [:],
                errors: []
            )
            return
        }

        let keyed = try decoder.container(keyedBy: CodingKeys.self)
        let namePairs = Self.decodeNamePairs(from: keyed)
        let counts = Self.decodeCounts(from: keyed)
        let errors = Self.decodeErrors(from: keyed)
        self.init(namePairs: namePairs, counts: counts, errors: errors)
    }

    public func encode(to encoder: Encoder) throws {
        var keyed = encoder.container(keyedBy: CodingKeys.self)
        try keyed.encode(namePairs, forKey: .namePairs)
        try keyed.encode(counts, forKey: .counts)
        try keyed.encode(errors, forKey: .errors)
    }

    private static func decodeNamePairs(
        from keyed: KeyedDecodingContainer<CodingKeys>
    ) -> [NamePairDTO] {
        if let value = try? keyed.decode([NamePairDTO].self, forKey: .namePairs) {
            return value
        }

        if let value = try? keyed.decode([[String]].self, forKey: .namePairs) {
            return value.compactMap { item in
                guard let original = item.first, !original.isEmpty else { return nil }
                let replacement = item.count > 1 ? item[1] : ""
                return NamePairDTO(original: original, replacement: replacement)
            }
        }

        if let value = try? keyed.decode([String].self, forKey: .namePairs) {
            return value.map { NamePairDTO(original: $0, replacement: "") }
        }

        if let value = try? keyed.decode([[String: String]].self, forKey: .namePairs) {
            return value.compactMap { item in
                let original = item["original"] ?? item["original_name"] ?? item["name"]
                guard let original, !original.isEmpty else { return nil }
                let replacement = item["replacement"] ?? item["replacement_name"] ?? item["value"] ?? ""
                return NamePairDTO(original: original, replacement: replacement)
            }
        }

        return []
    }

    private static func decodeCounts(
        from keyed: KeyedDecodingContainer<CodingKeys>
    ) -> [String: Int] {
        if let value = try? keyed.decode([String: Int].self, forKey: .counts) {
            return value
        }

        if let value = try? keyed.decode([String: String].self, forKey: .counts) {
            return value.reduce(into: [String: Int]()) { partial, item in
                if let count = Int(item.value) {
                    partial[item.key] = count
                }
            }
        }

        if let value = try? keyed.decode([String: Double].self, forKey: .counts) {
            return value.reduce(into: [String: Int]()) { partial, item in
                partial[item.key] = Int(item.value)
            }
        }

        return [:]
    }

    private static func decodeErrors(
        from keyed: KeyedDecodingContainer<CodingKeys>
    ) -> [String] {
        if let value = try? keyed.decode([String].self, forKey: .errors) {
            return value
        }

        if let value = try? keyed.decode(String.self, forKey: .errors) {
            return [value]
        }

        if let value = try? keyed.decode([[String: String]].self, forKey: .errors) {
            return value.compactMap { $0["message"] ?? $0["error"] }
        }

        return []
    }
}

public struct ReplaceResultDTO: Codable, Sendable {
    public var outputPath: String
    public var totals: [String: Int]
    public var perItem: [String: Int]

    public init(outputPath: String, totals: [String: Int], perItem: [String: Int]) {
        self.outputPath = outputPath
        self.totals = totals
        self.perItem = perItem
    }

    public enum CodingKeys: String, CodingKey {
        case outputPath = "output_path"
        case totals
        case perItem = "per_item"
    }
}

public struct ConfigDTO: Codable, Sendable {
    public var baseURL: String
    public var model: String
    public var temperature: Double
    public var timeoutSeconds: Double
    public var maxTokens: Int?
    public var promptTemplate: String
    public var chunkMaxBytes: Int
    public var requestIntervalSeconds: Double
    public var beginScanChunks: Int
    public var scanInterval: Int
    public var rememberAPIKey: Bool
    public var apiKey: String

    public init(
        baseURL: String,
        model: String,
        temperature: Double,
        timeoutSeconds: Double,
        maxTokens: Int?,
        promptTemplate: String,
        chunkMaxBytes: Int,
        requestIntervalSeconds: Double,
        beginScanChunks: Int,
        scanInterval: Int,
        rememberAPIKey: Bool,
        apiKey: String
    ) {
        self.baseURL = baseURL
        self.model = model
        self.temperature = temperature
        self.timeoutSeconds = timeoutSeconds
        self.maxTokens = maxTokens
        self.promptTemplate = promptTemplate
        self.chunkMaxBytes = chunkMaxBytes
        self.requestIntervalSeconds = requestIntervalSeconds
        self.beginScanChunks = beginScanChunks
        self.scanInterval = scanInterval
        self.rememberAPIKey = rememberAPIKey
        self.apiKey = apiKey
    }

    public enum CodingKeys: String, CodingKey {
        case baseURL = "base_url"
        case model
        case temperature
        case timeoutSeconds = "timeout_seconds"
        case maxTokens = "max_tokens"
        case promptTemplate = "prompt_template"
        case chunkMaxBytes = "chunk_max_bytes"
        case requestIntervalSeconds = "request_interval_seconds"
        case beginScanChunks = "begin_scan_chunks"
        case scanInterval = "scan_interval"
        case rememberAPIKey = "remember_api_key"
        case apiKey = "api_key"
    }

    public static let `default` = ConfigDTO(
        baseURL: "https://api.openai.com/v1",
        model: "gpt-4o-mini",
        temperature: 0.1,
        timeoutSeconds: 60.0,
        maxTokens: nil,
        promptTemplate: "{chunk_text}",
        chunkMaxBytes: 16384,
        requestIntervalSeconds: 2.0,
        beginScanChunks: 20,
        scanInterval: 3,
        rememberAPIKey: false,
        apiKey: ""
    )
}

public struct ExtractRequestDTO: Codable, Sendable {
    public var documentPath: String
    public var config: ConfigDTO
    public var apiKey: String?

    public init(documentPath: String, config: ConfigDTO, apiKey: String?) {
        self.documentPath = documentPath
        self.config = config
        self.apiKey = apiKey
    }

    public enum CodingKeys: String, CodingKey {
        case documentPath = "documentPath"
        case config
        case apiKey = "api_key"
    }
}

public struct ReplaceRequestDTO: Codable, Sendable {
    public var documentPath: String
    public var mappings: [String: String]
    public var outputPath: String?

    public init(documentPath: String, mappings: [String: String], outputPath: String?) {
        self.documentPath = documentPath
        self.mappings = mappings
        self.outputPath = outputPath
    }

    public enum CodingKeys: String, CodingKey {
        case documentPath = "documentPath"
        case mappings
        case outputPath = "outputPath"
    }
}

public struct NormalizeRequestDTO: Codable, Sendable {
    public var inputPath: String
    public var outputPath: String

    public init(inputPath: String, outputPath: String) {
        self.inputPath = inputPath
        self.outputPath = outputPath
    }

    public enum CodingKeys: String, CodingKey {
        case inputPath = "inputPath"
        case outputPath = "outputPath"
    }
}

public struct SaveNameCacheRequestDTO: Codable, Sendable {
    public var names: [String]

    public init(names: [String]) {
        self.names = names
    }
}

public struct NameCacheDTO: Codable, Sendable {
    public var names: [String]

    public init(names: [String]) {
        self.names = names
    }
}

public struct CommitImportedPairsRequestDTO: Codable, Sendable {
    public var documentPath: String
    public var pairs: [[String]]

    public init(documentPath: String, pairs: [[String]]) {
        self.documentPath = documentPath
        self.pairs = pairs
    }

    public enum CodingKeys: String, CodingKey {
        case documentPath = "documentPath"
        case pairs
    }
}

public struct CommitImportedPairsResponseDTO: Codable, Sendable {
    public var rows: [NameRowDTO]
    public var counts: [String: Int]

    public init(rows: [NameRowDTO], counts: [String: Int]) {
        self.rows = rows
        self.counts = counts
    }
}

public struct BridgeEnvelopeDTO: Codable, Sendable {
    public var ok: Bool
    public var result: Data?
    public var error: String?
    public var message: String?
}
