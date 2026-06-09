import Foundation

@MainActor
final class NameAutocompleteSource: ObservableObject {
    @Published private(set) var suggestions: [String] = []

    private let service: RenamrService

    init(service: RenamrService) {
        self.service = service
    }

    func refresh() async {
        do {
            suggestions = try await service.loadNameCache()
        } catch {
            suggestions = []
        }
    }

    func updateCache(with names: [String]) async {
        guard !names.isEmpty else { return }
        _ = try? await service.saveNameCache(names: names)
        await refresh()
    }

    func matches(for query: String, excluding original: String) -> [String] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return suggestions.filter { item in
            guard item != original else { return false }
            guard !trimmed.isEmpty else { return true }
            return item.localizedCaseInsensitiveContains(trimmed)
        }
    }
}
