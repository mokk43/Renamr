import XCTest
import RenamrShared

final class RenamrServiceTests: XCTestCase {
    func testConfigRoundTrip() throws {
        let config = ConfigDTO.default
        let data = try JSONEncoder().encode(config)
        let decoded = try JSONDecoder().decode(ConfigDTO.self, from: data)
        XCTAssertEqual(decoded.baseURL, config.baseURL)
        XCTAssertEqual(decoded.model, config.model)
        XCTAssertEqual(decoded.requestIntervalSeconds, config.requestIntervalSeconds)
    }

    func testProgressEventRoundTrip() throws {
        let event = ProgressEventDTO(
            stage: "parsing",
            current: 2,
            total: 10,
            detail: nil,
            runningNames: ["Alice", "Bob"]
        )
        let data = try JSONEncoder().encode(event)
        let decoded = try JSONDecoder().decode(ProgressEventDTO.self, from: data)
        XCTAssertEqual(decoded.stage, "parsing")
        XCTAssertEqual(decoded.runningNames, ["Alice", "Bob"])
        XCTAssertNil(decoded.detail)
    }
}
