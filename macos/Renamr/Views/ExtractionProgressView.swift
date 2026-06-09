import SwiftUI
import RenamrShared

struct ExtractionProgressView: View {
    let progress: ProgressEventDTO?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let progress {
                ProgressView(
                    value: Double(progress.current),
                    total: max(Double(progress.total), 1)
                )
                Text("\(progress.stage): \(progress.current)/\(max(progress.total, 1))")
                    .font(.caption)
                if let detail = progress.detail {
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else {
                Text("No extraction in progress")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}
