import Foundation

@objc public protocol RenamrServiceProtocol: NSObjectProtocol {
    func loadDocument(payload: Data, reply: @escaping (Data?, NSError?) -> Void)
    func extractNames(payload: Data, token: String, reply: @escaping (Data?, NSError?) -> Void)
    func replaceAndExport(payload: Data, reply: @escaping (Data?, NSError?) -> Void)
    func readSettings(reply: @escaping (Data?, NSError?) -> Void)
    func writeSettings(payload: Data, reply: @escaping (NSError?) -> Void)
    func normalizeLayout(payload: Data, reply: @escaping (NSError?) -> Void)
    func loadNameCache(reply: @escaping ([String]?, NSError?) -> Void)
    func saveNameCache(names: [String], reply: @escaping ([String]?, NSError?) -> Void)
    func commitImportedPairs(payload: Data, reply: @escaping (Data?, NSError?) -> Void)
    func cancel(token: String, reply: @escaping () -> Void)
    func ping(reply: @escaping (String) -> Void)
}

@objc public protocol RenamrProgressProtocol: NSObjectProtocol {
    func progress(payload: Data)
    func chunkNames(names: [String])
    func logMessage(message: String, level: String)
}
