import Foundation

// Generic transport readiness for a disposable simulator; no application SDK.
@main
struct Readiness {
    static func main() async {
        do {
            let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
            let settings = try JSONSerialization.jsonObject(with: data) as! [String: Any]
            let urls = settings["urls"] as! [String]
            let identity = settings["identity"] as! String
            let configuration = URLSessionConfiguration.ephemeral
            configuration.timeoutIntervalForRequest = 20
            configuration.timeoutIntervalForResource = 30
            let session = URLSession(configuration: configuration)
            defer { session.invalidateAndCancel() }
            for (index, address) in urls.enumerated() {
                let (body, response) = try await session.data(from: URL(string: address)!)
                guard (response as? HTTPURLResponse)?.statusCode == 200,
                      let document = try JSONSerialization.jsonObject(with: body) as? [String: Any] else {
                    print("{\"ready\":false,\"reason\":\"response\"}")
                    exit(1)
                }
                if index == urls.count - 1 {
                    let credentials = document["webcredentials"] as? [String: Any]
                    guard (credentials?["apps"] as? [String])?.contains(identity) == true else {
                        print("{\"ready\":false,\"reason\":\"association_identity\"}")
                        exit(1)
                    }
                }
            }
            print("{\"ready\":true}")
        } catch {
            print("{\"ready\":false,\"code\":\((error as NSError).code)}")
            exit(1)
        }
    }
}
