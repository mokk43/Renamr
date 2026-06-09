import SwiftUI

struct SettingsView: View {
    @ObservedObject var viewModel: SettingsViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var isSaving = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Form {
                Section("Connection") {
                    TextField("Base URL", text: $viewModel.draft.baseURL)
                    TextField("Model", text: $viewModel.draft.model)
                    SecureField("API key", text: $viewModel.draft.apiKey)
                    Toggle("Remember API key (saved in config file)", isOn: $viewModel.draft.rememberAPIKey)
                }
                Section("Inference") {
                    HStack {
                        Text("Temperature")
                        Slider(value: $viewModel.draft.temperature, in: 0 ... 2, step: 0.05)
                        Text(String(format: "%.2f", viewModel.draft.temperature))
                            .monospacedDigit()
                    }
                    TextField(
                        "Timeout seconds",
                        value: $viewModel.draft.timeoutSeconds,
                        format: .number
                    )
                    TextField("Max tokens", value: $viewModel.draft.maxTokens, format: .number)
                }
                Section("Extraction") {
                    TextField("Chunk max bytes", value: $viewModel.draft.chunkMaxBytes, format: .number)
                    TextField(
                        "Request interval seconds (>=2.0)",
                        value: $viewModel.draft.requestIntervalSeconds,
                        format: .number
                    )
                    TextField(
                        "Begin scan chunks",
                        value: $viewModel.draft.beginScanChunks,
                        format: .number
                    )
                    TextField("Scan interval", value: $viewModel.draft.scanInterval, format: .number)
                }
                Section("Prompt template") {
                    TextEditor(text: $viewModel.draft.promptTemplate)
                        .frame(minHeight: 130)
                        .font(.system(.body, design: .monospaced))
                }
            }
            if let error = viewModel.validationError {
                Text(error)
                    .foregroundStyle(.red)
            }
            HStack {
                Spacer()
                Button("Save") {
                    Task {
                        isSaving = true
                        defer { isSaving = false }
                        do {
                            try await viewModel.save()
                            dismiss()
                        } catch {
                            viewModel.validationError = error.localizedDescription
                        }
                    }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(isSaving)
            }
        }
        .padding()
        .frame(minWidth: 720, minHeight: 560)
        .task {
            await viewModel.load()
        }
    }
}
