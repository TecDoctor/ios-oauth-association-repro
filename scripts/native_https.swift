import Foundation

let endpoint = URL(string: "https://probe.test/health")!
var finished = false
var exitCode: Int32 = 1
var request = URLRequest(url: endpoint)
request.timeoutInterval = 180
let task = URLSession.shared.dataTask(with: request) { data, response, error in
    let status = (response as? HTTPURLResponse)?.statusCode ?? 0
    let body = String(data: data ?? Data(), encoding: .utf8) ?? ""
    let result: [String: Any] = ["status": status, "body": body,
        "error": error?.localizedDescription ?? ""]
    if let json = try? JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]),
       let text = String(data: json, encoding: .utf8) { print(text) }
    exitCode = status == 200 && body.trimmingCharacters(in: .whitespacesAndNewlines) == "healthy" && error == nil ? 0 : 1
    finished = true
}
task.resume()
let deadline = Date().addingTimeInterval(190)
while !finished && Date() < deadline {
    RunLoop.current.run(until: Date().addingTimeInterval(0.1))
}
if !finished { print("Native HTTPS request deadline exceeded") }
exit(exitCode)
