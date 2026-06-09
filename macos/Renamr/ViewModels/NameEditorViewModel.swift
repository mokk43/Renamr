import Foundation
import RenamrShared

@MainActor
final class NameEditorViewModel: ObservableObject {
    struct NameRowModel: Identifiable, Sendable {
        let id = UUID()
        var original: String
        var replacement: String
        var occurrenceCount: Int
        var userAdded: Bool

        var isEdited: Bool {
            let source = original.trimmingCharacters(in: .whitespacesAndNewlines)
            let target = replacement.trimmingCharacters(in: .whitespacesAndNewlines)
            return !source.isEmpty && !target.isEmpty && source != target
        }
    }

    @Published var rows: [NameRowModel] = []
    @Published var filterEditedOnly = false
    @Published var searchText = ""

    var visibleRows: [NameRowModel] {
        rows.filter { row in
            let matchesEdited = !filterEditedOnly || row.isEdited
            guard matchesEdited else { return false }
            let needle = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !needle.isEmpty else { return true }
            return row.original.localizedCaseInsensitiveContains(needle)
                || row.replacement.localizedCaseInsensitiveContains(needle)
        }
    }

    func setRows(namePairs: [NamePairDTO], counts: [String: Int]) {
        rows = namePairs
            .map {
                NameRowModel(
                    original: $0.original,
                    replacement: $0.replacement,
                    occurrenceCount: counts[$0.original, default: 0],
                    userAdded: false
                )
            }
            .filter { $0.occurrenceCount > 0 }
            .sorted {
                if $0.occurrenceCount == $1.occurrenceCount {
                    return $0.original < $1.original
                }
                return $0.occurrenceCount > $1.occurrenceCount
            }
    }

    func setRows(importedRows: [NameRowDTO]) {
        rows = importedRows
            .map {
                NameRowModel(
                    original: $0.originalName,
                    replacement: $0.replacementName,
                    occurrenceCount: $0.occurrenceCount,
                    userAdded: false
                )
            }
            .filter { $0.occurrenceCount > 0 }
            .sorted {
                if $0.occurrenceCount == $1.occurrenceCount {
                    return $0.original < $1.original
                }
                return $0.occurrenceCount > $1.occurrenceCount
            }
    }

    func updateReplacement(for rowID: UUID, replacement: String) {
        guard let index = rows.firstIndex(where: { $0.id == rowID }) else { return }
        rows[index].replacement = replacement
    }

    func resetAll() {
        for index in rows.indices {
            rows[index].replacement = ""
        }
    }

    func resetRow(_ rowID: UUID) {
        guard let index = rows.firstIndex(where: { $0.id == rowID }) else { return }
        rows[index].replacement = ""
    }

    func removeRow(_ rowID: UUID) {
        rows.removeAll { $0.id == rowID }
    }

    func appendCustomRow() {
        rows.append(
            NameRowModel(
                original: "",
                replacement: "",
                occurrenceCount: 0,
                userAdded: true
            )
        )
    }

    func removeEmptyCustomRows() {
        rows.removeAll { $0.userAdded && $0.original.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    }

    func editedMappings() -> [String: String] {
        Dictionary(
            uniqueKeysWithValues: rows.compactMap { row in
                guard row.isEdited else { return nil }
                guard row.occurrenceCount > 0 || row.userAdded else { return nil }
                return (row.original, row.replacement.trimmingCharacters(in: .whitespacesAndNewlines))
            }
        )
    }

    func nonEmptyReplacements() -> [String] {
        var seen = Set<String>()
        var values: [String] = []
        for row in rows {
            let value = row.replacement.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !value.isEmpty else { continue }
            if seen.insert(value).inserted {
                values.append(value)
            }
        }
        return values
    }
}
