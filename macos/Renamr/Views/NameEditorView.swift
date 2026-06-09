import SwiftUI

struct NameEditorView: View {
    @ObservedObject var viewModel: NameEditorViewModel
    @ObservedObject var autocomplete: NameAutocompleteSource

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Toggle("Edited only", isOn: $viewModel.filterEditedOnly)
                TextField("Search", text: $viewModel.searchText)
                    .textFieldStyle(.roundedBorder)
                Button("Add row") {
                    viewModel.appendCustomRow()
                }
                Button("Reset all") {
                    viewModel.resetAll()
                }
            }
            .font(.subheadline)

            List {
                ForEach(viewModel.visibleRows) { row in
                    if let binding = binding(for: row.id) {
                        NameRowView(
                            row: binding,
                            suggestions: autocomplete.matches(
                                for: binding.wrappedValue.replacement,
                                excluding: binding.wrappedValue.original
                            ),
                            onReset: { viewModel.resetRow(row.id) },
                            onRemove: binding.wrappedValue.userAdded ? { viewModel.removeRow(row.id) } : nil
                        )
                    }
                }
            }
            .listStyle(.inset)
        }
        .task {
            await autocomplete.refresh()
        }
    }

    private func binding(for id: UUID) -> Binding<NameEditorViewModel.NameRowModel>? {
        guard let index = viewModel.rows.firstIndex(where: { $0.id == id }) else { return nil }
        return $viewModel.rows[index]
    }
}
