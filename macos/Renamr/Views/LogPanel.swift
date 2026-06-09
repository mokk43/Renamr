import SwiftUI

struct LogPanel: View {
    @ObservedObject var appLog: AppLog
    @State private var expanded = false

    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 6) {
                    ForEach(appLog.entries) { entry in
                        HStack(alignment: .top, spacing: 8) {
                            Text(entry.timestamp.formatted(date: .omitted, time: .standard))
                                .foregroundStyle(.secondary)
                            Text("[\(entry.level.uppercased())]")
                                .foregroundStyle(color(for: entry.level))
                            Text(entry.message)
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .font(.caption)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(minHeight: 100, maxHeight: 240)
        } label: {
            Text("Log")
                .font(.headline)
        }
    }

    private func color(for level: String) -> Color {
        switch level.lowercased() {
        case "error":
            return .red
        case "warning":
            return .orange
        default:
            return .secondary
        }
    }
}
