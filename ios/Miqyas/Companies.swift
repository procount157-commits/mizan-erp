import Foundation

/// The companies this phone has signed in to, newest first — like the
/// accounts list in Odoo's app. Only addresses are kept; the password stays
/// in the web session for that address, never in the app.
enum Companies {
    private static let listKey = "companies.hosts"
    private static let currentKey = "companies.current"
    private static var defaults: UserDefaults { .standard }

    /// The domain a bare company code belongs to: "alamana" → alamana.<domain>.
    static var domain: String {
        (Bundle.main.object(forInfoDictionaryKey: "MiqyasDomain") as? String) ?? "miqyas.example.com"
    }

    static var all: [String] { defaults.stringArray(forKey: listKey) ?? [] }
    static var current: String? { defaults.string(forKey: currentKey) }

    static func use(_ host: String) {
        var hosts = all.filter { $0 != host }
        hosts.insert(host, at: 0)
        defaults.set(hosts, forKey: listKey)
        defaults.set(host, forKey: currentKey)
    }

    static func forget(_ host: String) {
        defaults.set(all.filter { $0 != host }, forKey: listKey)
        if current == host { defaults.removeObject(forKey: currentKey) }
    }

    /// "alamana" → alamana.miqyas.ae; anything with a dot is taken as the
    /// server's own address, the way Odoo's app accepts any server.
    static func host(for typed: String) -> String? {
        var text = typed.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        for prefix in ["https://", "http://"] where text.hasPrefix(prefix) {
            text.removeFirst(prefix.count)
        }
        if let slash = text.firstIndex(of: "/") { text = String(text[..<slash]) }
        guard !text.isEmpty else { return nil }
        if !text.contains(".") {
            return text.range(of: "^[a-z0-9][a-z0-9-]*$", options: .regularExpression) != nil
                ? "\(text).\(domain)" : nil
        }
        return text.range(of: "^[a-z0-9.-]+(:[0-9]+)?$", options: .regularExpression) != nil ? text : nil
    }

    /// Asks the server before saving it, so a typo says so on this screen
    /// rather than as a blank page later.
    static func check(_ host: String, completion: @escaping (Bool) -> Void) {
        guard let url = URL(string: "https://\(host)/web/login") else { return completion(false) }
        var request = URLRequest(url: url, timeoutInterval: 12)
        request.httpMethod = "GET"
        URLSession.shared.dataTask(with: request) { _, response, _ in
            let ok = (response as? HTTPURLResponse)?.statusCode == 200
            DispatchQueue.main.async { completion(ok) }
        }.resume()
    }
}
