import Foundation
import RenamrShared

@MainActor
final class CSVImportViewModel: ObservableObject {
    @Published var errorMessage: String?

    private let service: RenamrService

    init(service: RenamrService) {
        self.service = service
    }

    func importCSV(data: Data, documentPath: String) async -> [NameRowDTO] {
        do {
            let pairs = try CSVParser.parse(data: data)
            let request = CommitImportedPairsRequestDTO(
                documentPath: documentPath,
                pairs: pairs.map { [$0.original, $0.replacement] }
            )
            let response = try await service.commitImportedPairs(request: request)
            errorMessage = nil
            return response.rows
        } catch {
            errorMessage = error.localizedDescription
            return []
        }
    }
}
