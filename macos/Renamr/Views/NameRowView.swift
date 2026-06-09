import SwiftUI

struct NameRowView: View {
    @Binding var row: NameEditorViewModel.NameRowModel
    let suggestions: [String]
    let onReset: () -> Void
    let onRemove: (() -> Void)?

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                if row.userAdded {
                    TextField("Original", text: $row.original)
                        .textFieldStyle(.roundedBorder)
                } else {
                    Text(row.original.isEmpty ? "—" : row.original)
                        .fontWeight(.medium)
                }
                Text("Count: \(row.occurrenceCount)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            TextField("Replacement", text: $row.replacement)
                .textFieldStyle(.roundedBorder)
            if !suggestions.isEmpty {
                Menu("Suggestions") {
                    ForEach(suggestions, id: \.self) { value in
                        Button(value) {
                            row.replacement = value
                        }
                    }
                }
                .menuStyle(.borderlessButton)
            }
        }
        .contextMenu {
            Button("Reset row") {
                onReset()
            }
            if let onRemove {
                Button("Remove row", role: .destructive) {
                    onRemove()
                }
            }
        }
    }
}
