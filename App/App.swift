import AuthenticationServices
import UIKit

// Standalone diagnostic. No SDK code, credential entry, or token exchange.
@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    func application(_ application: UIApplication, configurationForConnecting session: UISceneSession, options: UIScene.ConnectionOptions) -> UISceneConfiguration {
        let configuration = UISceneConfiguration(name: "Probe", sessionRole: session.role)
        configuration.delegateClass = SceneDelegate.self
        return configuration
    }
}

final class SceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?
    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options: UIScene.ConnectionOptions) {
        guard let scene = scene as? UIWindowScene else { return }
        let window = UIWindow(windowScene: scene)
        window.rootViewController = ProbeController()
        self.window = window
        window.makeKeyAndVisible()
    }
    func sceneDidBecomeActive(_ scene: UIScene) {
        (window?.rootViewController as? ProbeController)?.startWhenReady()
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
        startWhenReady()
    }

    func startWhenReady() {
        if ProcessInfo.processInfo.environment["PROBE_AUTOSTART"] == "1",
           viewIfLoaded?.window?.windowScene?.activationState == .foregroundActive {
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
                    // Raw error details stay private and are only exported inside encrypted evidence.
                    let file = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
                        .appendingPathComponent("private-error.json")
                    let details: [String: Any] = ["domain": error.domain, "code": error.code,
                        "description": error.localizedDescription,
                        "failureReason": error.userInfo[NSLocalizedFailureReasonErrorKey] as? String ?? "",
                        "debugDescription": error.userInfo[NSDebugDescriptionErrorKey] as? String ?? ""]
                    if let data = try? JSONSerialization.data(withJSONObject: details) {
                        try? data.write(to: file, options: .atomic)
                    }
                    let description = [error.localizedDescription,
                        error.userInfo[NSLocalizedFailureReasonErrorKey] as? String ?? "",
                        error.userInfo[NSDebugDescriptionErrorKey] as? String ?? ""].joined(separator: " ").lowercased()
                    if description.contains("not associated") || description.contains("associated domain") {
                        self.record("association_failure")
                    } else if error.domain == ASWebAuthenticationSessionErrorDomain,
                              error.code == ASWebAuthenticationSessionError.Code.presentationContextInvalid.rawValue {
                        self.record("presentation_context_invalid")
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
        record(view.window?.windowScene?.activationState == .foregroundActive ? "scene_active" : "scene_inactive")
        return view.window!
    }
}
