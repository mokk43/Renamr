import XCTest

final class PreparePythonRuntimeScriptTests: XCTestCase {
    func testRejectsFrameworkRuntimeWhenLauncherIsMissing() throws {
        let fixture = try RuntimeScriptFixture(testCase: self)
        try fixture.createRequiredInputs()
        try fixture.createFrameworkRuntime()

        let result = try runPrepareScript(fixture: fixture)

        XCTAssertNotEqual(result.status, 0)
        XCTAssertTrue(result.stderr.contains("No executable Python launcher found"))
    }

    func testCreatesLauncherSymlinkWhenFrameworkProvidesPython3() throws {
        let fixture = try RuntimeScriptFixture(testCase: self)
        try fixture.createRequiredInputs()
        try fixture.createFrameworkRuntime()
        try fixture.createFrameworkLauncher()

        let result = try runPrepareScript(fixture: fixture)

        XCTAssertEqual(result.status, 0, result.stderr)
        let symlink = fixture.serviceBundle
            .appendingPathComponent("Contents/Resources/python/bin/python3")
        let destination = try FileManager.default.destinationOfSymbolicLink(atPath: symlink.path)
        XCTAssertEqual(destination, "../../../Frameworks/Python.framework/Versions/Current/bin/python3")
    }

    private func runPrepareScript(fixture: RuntimeScriptFixture) throws -> ScriptResult {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let scriptURL = packageRoot.appendingPathComponent("Scripts/prepare_python_runtime.sh")

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = [
            scriptURL.path,
            "--bundle",
            fixture.bundle.path,
            "--repo-root",
            fixture.repoRoot.path,
        ]

        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr

        try process.run()
        process.waitUntilExit()

        return ScriptResult(
            status: process.terminationStatus,
            stdout: String(data: stdout.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? "",
            stderr: String(data: stderr.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        )
    }
}

private struct ScriptResult {
    let status: Int32
    let stdout: String
    let stderr: String
}

private final class RuntimeScriptFixture {
    let root: URL
    let repoRoot: URL
    let bundle: URL
    let serviceBundle: URL
    private let frameworkCurrent: URL

    init(testCase: XCTestCase) throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("renamr-runtime-\(UUID().uuidString)", isDirectory: true)
        repoRoot = root.appendingPathComponent("repo", isDirectory: true)
        bundle = root.appendingPathComponent("Renamr.app", isDirectory: true)
        serviceBundle = bundle
            .appendingPathComponent("Contents/XPCServices/RenamrPythonService.xpc", isDirectory: true)
        frameworkCurrent = repoRoot
            .appendingPathComponent("macos/Vendored/Python.xcframework/macos-arm64_x86_64/Python.framework/Versions/Current", isDirectory: true)

        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        testCase.addTeardownBlock { [root] in
            try? FileManager.default.removeItem(at: root)
        }
    }

    func createRequiredInputs() throws {
        let directories = [
            serviceBundle,
            repoRoot.appendingPathComponent("macos/Vendored/python-stdlib", isDirectory: true),
            repoRoot.appendingPathComponent("macos/Vendored/app_packages", isDirectory: true),
            repoRoot.appendingPathComponent("txt_process", isDirectory: true),
        ]
        for directory in directories {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        }
    }

    func createFrameworkRuntime() throws {
        try FileManager.default.createDirectory(at: frameworkCurrent, withIntermediateDirectories: true)
        try createExecutable(at: frameworkCurrent.appendingPathComponent("Python"))
    }

    func createFrameworkLauncher() throws {
        let bin = frameworkCurrent.appendingPathComponent("bin", isDirectory: true)
        try FileManager.default.createDirectory(at: bin, withIntermediateDirectories: true)
        try createExecutable(at: bin.appendingPathComponent("python3"))
    }

    private func createExecutable(at url: URL) throws {
        try Data("#!/bin/sh\n".utf8).write(to: url)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: url.path)
    }
}
