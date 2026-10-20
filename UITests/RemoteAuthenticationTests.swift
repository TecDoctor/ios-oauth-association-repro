import XCTest

// Generic OAuth browser probe; no private SDK is imported or built.
final class RemoteAuthenticationTests: XCTestCase {
    private let allowance: TimeInterval = 1000
    private let system = XCUIApplication(bundleIdentifier: "com.apple.springboard")
    private var app: XCUIApplication!

    private func consent() {
        for owner in [system, app!] {
            for label in ["Continue", "続ける", "Allow"] {
                let button = owner.alerts.buttons[label].firstMatch
                if button.exists && button.isHittable { button.tap() }
            }
        }
    }

    private func wait(_ message: String, until condition: () -> Bool) {
        let deadline = Date().addingTimeInterval(allowance)
        while Date() < deadline {
            consent()
            if condition() { return }
            Thread.sleep(forTimeInterval: 1)
        }
        evidence("Failure screen")
        XCTFail(message)
    }

    private func evidence(_ name: String, element: XCUIElement? = nil) {
        let image = element?.screenshot() ?? XCUIScreen.main.screenshot()
        let attachment = XCTAttachment(screenshot: image)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func center(_ element: XCUIElement, in owner: XCUIApplication) {
        let deadline = Date().addingTimeInterval(allowance)
        while Date() < deadline {
            let frame = owner.frame
            if element.exists {
                let middle = element.frame.midY
                if element.isHittable && middle > frame.minY + frame.height * 0.25 && middle < frame.minY + frame.height * 0.75 { return }
                let upward = middle >= frame.midY
                let start = owner.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: upward ? 0.7 : 0.3))
                let end = owner.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: upward ? 0.4 : 0.6))
                start.press(forDuration: 0.1, thenDragTo: end)
            } else {
                owner.swipeUp()
            }
        }
        evidence("Control positioning failed")
        XCTFail("Required control could not be positioned clear of screen overlays.")
    }

    private func field(labels: [String], secure: Bool) -> XCUIElement? {
        for owner in [app!] {
            let query = secure ? owner.secureTextFields : owner.textFields
            let element = query.matching(NSPredicate(format: "label IN %@ OR identifier IN %@", labels, labels)).firstMatch
            if element.exists { return element }
        }
        return nil
    }

    private func replace(_ element: XCUIElement, with value: String) {
        func focused() -> Bool {
            for owner in [app!] {
                let query = owner.descendants(matching: element.elementType)
                if query.matching(NSPredicate(format: "hasKeyboardFocus == true AND label == %@", element.label)).firstMatch.exists { return true }
            }
            return false
        }
        if !focused() {
            // Safari's input accessory toolbar can cover the next field.
            keyboardAction(["Done", "完了"])
            center(element, in: app)
            element.tap()
        }
        wait("The requested input field did not obtain keyboard focus.") { focused() }
        let current = element.value as? String ?? ""
        let count = current == element.placeholderValue ? 0 : current.count
        if count > 0 { element.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: count)) }
        element.typeText(value)
    }

    private func keyboardAction(_ labels: [String]) {
        for owner in [app!] {
            for label in labels {
                // Safari renders Next/Done in an accessory toolbar, outside Keyboard.
                for query in [owner.toolbars.buttons, owner.keyboards.buttons] {
                    let button = query[label].firstMatch
                    if button.exists && button.isHittable { button.tap(); return }
                }
            }
        }
    }

    func testRemoteLoginCallback() throws {
        continueAfterFailure = false
        let environment = ProcessInfo.processInfo.environment
        guard let bundle = environment["PROBE_APP_BUNDLE_ID"],
              let username = environment["PROBE_USERNAME"], !username.isEmpty,
              let password = environment["PROBE_PASSWORD"], !password.isEmpty else {
            XCTFail("Probe configuration has not been supplied.")
            return
        }
        app = XCUIApplication(bundleIdentifier: bundle)
        app.launchEnvironment["PROBE_AUTOSTART"] = "1"
        app.launch()
        let login = app.buttons["Start authentication probe"]

        let emailLabels = ["Email input", "Username or email input", "Eメール入力欄", "Eメール", "メールアドレス入力欄"]
        let passwordLabels = ["Password input", "パスワード入力欄", "パスワード"]
        var failedAttempts = 0
        wait("Authentication form was not presented.") {
            if self.field(labels: emailLabels, secure: false) != nil || self.field(labels: passwordLabels, secure: true) != nil { return true }
            let failure = self.app.staticTexts["probe-status"]
            if failure.exists && ["configuration_failure", "presentation_context_invalid", "start_rejected", "other_session_failure", "callback_rejected"].contains(failure.label) {
                self.evidence("Terminal authentication session failure")
                XCTFail("Authentication session reported an explicit terminal error.")
            }
            if failure.exists && failure.label == "association_failure" {
                failedAttempts += 1
                self.evidence("Pre-form association failure \(failedAttempts)")
                // No credentials have been entered. Preserve the app while its native services initialize.
                Thread.sleep(forTimeInterval: 10)
                self.center(login, in: self.app)
                login.press(forDuration: 3)
            }
            return false
        }
        if let email = field(labels: emailLabels, secure: false) {
            replace(email, with: username)
            keyboardAction(["Next", "次へ"])
        }
        wait("Password field was not presented.") { self.field(labels: passwordLabels, secure: true) != nil }
        guard let passwordField = field(labels: passwordLabels, secure: true) else {
            XCTFail("Password field disappeared before credential entry.")
            return
        }
        replace(passwordField, with: password)
        keyboardAction(["Done", "完了"])
        var submitted = false
        for owner in [app!] {
            let button = owner.webViews.buttons.matching(NSPredicate(format: "label IN %@", ["Log In", "Sign In", "ログイン"])).firstMatch
            if button.exists {
                center(button, in: owner)
                button.tap()
                submitted = true
                break
            }
        }
        XCTAssertTrue(submitted, "No login form submit control was found.")
        evidence("Immediately after credential submission")
        let started = Date()
        var lastEvidence = Date.distantPast
        wait("OAuth callback did not arrive after form submission.") {
            let status = self.app.staticTexts["probe-status"]
            if status.exists && status.label == "callback_received" { return true }
            if status.exists && status.label == "callback_rejected" {
                self.evidence("Rejected OAuth callback")
                XCTFail("OAuth callback lacked a valid authorization code or matching state.")
            }
            if Date().timeIntervalSince(lastEvidence) > 60 {
                lastEvidence = Date()
                self.evidence("Post-submit screen")
                let hierarchy = XCTAttachment(string: self.app.debugDescription)
                hierarchy.name = "Post-submit accessibility hierarchy"
                hierarchy.lifetime = .keepAlways
                self.add(hierarchy)
            }
            // Preserve the unexplained page for observation before interacting with consent.
            if Date().timeIntervalSince(started) < 60 { return false }
            let terms = self.app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "同意して登録する")).firstMatch
            if terms.exists {
                self.app.swipeUp()
                if terms.isEnabled && terms.isHittable { terms.tap() }
            }
            let consent = self.app.buttons["同意する"].firstMatch
            if consent.exists && consent.isEnabled { self.center(consent, in: self.app); consent.tap() }
            return false
        }
        evidence("OAuth callback received")
    }
}
