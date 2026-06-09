import SwiftUI
import UniformTypeIdentifiers
import RenamrShared

struct CSVImportSheet: View {
    @ObservedObject var viewModel: CSVImportViewModel
    let documentPath: String
    let onImported: ([NameRowDTO]) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var showingImporter = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Import name mappings from CSV")
                .font(.headline)
            Text("CSV format: source,target")
                .font(.caption)
                .foregroundStyle(.secondary)
            if let message = viewModel.errorMessage {
                Text(message)
                    .foregroundStyle(.red)
                    .font(.caption)
            }
            HStack {
                Spacer()
                Button("Choose CSV…") {
                    showingImporter = true
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding()
        .frame(minWidth: 360)
        .fileImporter(
            isPresented: $showingImporter,
            allowedContentTypes: [.commaSeparatedText, .plainText]
        ) { result in
            Task {
                switch result {
                case let .success(url):
                    do {
                        let data = try Data(contentsOf: url)
                        let rows = await viewModel.importCSV(data: data, documentPath: documentPath)
                        onImported(rows)
                        dismiss()
                    } catch {
                        viewModel.errorMessage = error.localizedDescription
                    }
                case let .failure(error):
                    viewModel.errorMessage = error.localizedDescription
                }
            }
        }
    }
}
