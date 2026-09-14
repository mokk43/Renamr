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

    func testExtractionResultDecodesPairArrays() throws {
        let payload = """
        {
          "name_pairs": [["Alice", ""], ["Bob", "Robert"]],
          "counts": {"Alice": 3, "Bob": 1},
          "errors": []
        }
        """
        let decoded = try JSONDecoder().decode(
            ExtractionResultDTO.self,
            from: Data(payload.utf8)
        )
        XCTAssertEqual(decoded.namePairs.count, 2)
        XCTAssertEqual(decoded.namePairs[0].original, "Alice")
        XCTAssertEqual(decoded.namePairs[0].replacement, "")
        XCTAssertEqual(decoded.namePairs[1].original, "Bob")
        XCTAssertEqual(decoded.namePairs[1].replacement, "Robert")
        XCTAssertEqual(decoded.counts["Alice"], 3)
    }

    func testExtractionResultDecodesStringNamePairsAndStringCounts() throws {
        let payload = """
        {
          "name_pairs": ["Alice", "Bob"],
          "counts": {"Alice": "3", "Bob": "1"},
          "errors": "partial failure"
        }
        """
        let decoded = try JSONDecoder().decode(
            ExtractionResultDTO.self,
            from: Data(payload.utf8)
        )
        XCTAssertEqual(decoded.namePairs.map(\.original), ["Alice", "Bob"])
        XCTAssertEqual(decoded.namePairs.map(\.replacement), ["", ""])
        XCTAssertEqual(decoded.counts["Alice"], 3)
        XCTAssertEqual(decoded.errors, ["partial failure"])
    }

    func testExtractionResultDecodesLegacyPairObjects() throws {
        let payload = """
        {
          "name_pairs": [
            {"original_name": "Alice", "replacement_name": ""},
            {"name": "Bob", "value": "Robert"}
          ],
          "counts": {"Alice": 2, "Bob": 1},
          "errors": []
        }
        """
        let decoded = try JSONDecoder().decode(
            ExtractionResultDTO.self,
            from: Data(payload.utf8)
        )
        XCTAssertEqual(decoded.namePairs.count, 2)
        XCTAssertEqual(decoded.namePairs[0].original, "Alice")
        XCTAssertEqual(decoded.namePairs[0].replacement, "")
        XCTAssertEqual(decoded.namePairs[1].original, "Bob")
        XCTAssertEqual(decoded.namePairs[1].replacement, "Robert")
    }
}
