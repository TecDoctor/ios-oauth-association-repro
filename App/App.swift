import AuthenticationServices
import UIKit

// Standalone diagnostic. No SDK code, credential entry, or token exchange.
@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
    func application(_ application: UIApplication, didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        let window = UIWindow(frame: UIScreen.main.bounds)
        window.rootViewController = ProbeController()
        window.makeKeyAndVisible()
        self.window = window
        return true
    }
}

final class ProbeController: UIViewController, ASWebAuthenticationPresentationContextProviding {
    private var session: ASWebAuthenticationSession?
    private var events: [String] = []
    private var started = false

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        let button = UIButton(type: .system)
        button.setTitle("Start authentication probe", for: .normal)
        button.addTarget(self, action: #selector(startProbe), for: .touchUpInside)
        button.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(button)
        NSLayoutConstraint.activate([
            button.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            button.centerYAnchor.constraint(equalTo: view.centerYAnchor)
        ])
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        if ProcessInfo.processInfo.environment["PROBE_AUTOSTART"] == "1" {
            startProbe()
        }
    }

    private func record(_ event: String) {
        events.append(event)
        let file = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("probe-events.json")
        if let data = try? JSONSerialization.data(withJSONObject: events) {
            try? data.write(to: file, options: .atomic)
        }
    }

    @objc private func startProbe() {
        guard !started else { return }
        started = true
        record("handler")
        guard let file = Bundle.main.url(forResource: "Runtime", withExtension: "plist"),
              let data = try? Data(contentsOf: file),
              let config = (try? PropertyListSerialization.propertyList(from: data, format: nil)) as? [String: String],
              let rawURL = config["authorizationURL"], let url = URL(string: rawURL),
              let host = config["callbackHost"], let path = config["callbackPath"] else {
            record("configuration_failure")
            return
        }
        let session = ASWebAuthenticationSession(url: url, callback: .https(host: host, path: path)) { [weak self] callback, error in
            DispatchQueue.main.async {
                guard let self else { return }
                if callback != nil {
                    self.record("callback_received")
                } else if let error = error as NSError? {
                    // Classify locally; never persist raw error text or callback URLs.
                    let description = [error.localizedDescription,
                        error.userInfo[NSLocalizedFailureReasonErrorKey] as? String ?? "",
                        error.userInfo[NSDebugDescriptionErrorKey] as? String ?? ""].joined(separator: " ").lowercased()
                    if description.contains("not associated") || description.contains("associated domain") {
                        self.record("association_failure")
                    } else {
                        self.record("other_session_failure")
                    }
                } else {
                    self.record("empty_completion")
                }
                self.session = nil
            }
        }
        session.presentationContextProvider = self
        self.session = session
        record(session.start() ? "start_accepted" : "start_rejected")
    }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        record(view.window?.isKeyWindow == true ? "key_window_present" : "key_window_missing")
        return view.window!
    }
}
