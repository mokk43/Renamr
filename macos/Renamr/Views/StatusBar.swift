import SwiftUI
import RenamrShared

struct StatusBar: View {
    let document: DocumentDescriptorDTO?
    let status: DocumentViewModel.AppStatus
    let progress: ProgressEventDTO?

    var body: some View {
        HStack(spacing: 12) {
            Text(document?.path ?? "No file loaded")
                .lineLimit(1)
                .truncationMode(.middle)
            Divider()
            Text(statusLabel)
            if let progress {
                Divider()
                Text("\(progress.current)/\(max(progress.total, 1))")
                if let detail = progress.detail {
                    Text(detail)
                        .lineLimit(1)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
        }
        .font(.caption)
    }

    private var statusLabel: String {
        switch status {
        case .idle:
            return "Idle"
        case .loading:
            return "Loading…"
        case .extracting:
            return "Extracting…"
        case .replacing:
            return "Replacing…"
        case .normalizing:
            return "Normalizing…"
        case .cancelling:
            return "Cancelling…"
        case let .failed(message):
            return "Error: \(message)"
        }
    }
}
