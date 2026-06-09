import Foundation
import RenamrShared

final class ConnectionSupervisor {
    private let serviceName: String
    private let lock = NSLock()
    private var connection: NSXPCConnection?

    var onInterruption: (() -> Void)?
    var onInvalidation: (() -> Void)?

    init(serviceName: String = "dev.renamr.app.PythonService") {
        self.serviceName = serviceName
    }

    func activeConnection(progressReceiver: RenamrProgressProtocol?) -> NSXPCConnection {
        lock.lock()
        defer { lock.unlock() }
        if let connection {
            if let progressReceiver {
                connection.exportedInterface = NSXPCInterface(with: RenamrProgressProtocol.self)
                connection.exportedObject = progressReceiver
            } else {
                connection.exportedInterface = nil
                connection.exportedObject = nil
            }
            return connection
        }
        let created = NSXPCConnection(serviceName: serviceName)
        created.remoteObjectInterface = NSXPCInterface(with: RenamrServiceProtocol.self)
        if let progressReceiver {
            created.exportedInterface = NSXPCInterface(with: RenamrProgressProtocol.self)
            created.exportedObject = progressReceiver
        }
        created.interruptionHandler = { [weak self] in
            self?.onInterruption?()
            self?.reset()
        }
        created.invalidationHandler = { [weak self] in
            self?.onInvalidation?()
            self?.reset()
        }
        created.resume()
        connection = created
        return created
    }

    func reset() {
        lock.lock()
        defer { lock.unlock() }
        connection?.invalidate()
        connection = nil
    }
}
