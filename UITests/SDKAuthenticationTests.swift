import XCTest

// UI-only verification: the SDK implementation is fetched privately by CI.
final class SDKAuthenticationTests: XCTestCase {
    private let allowance: TimeInterval = 1000
    private let system = XCUIApplication(bundleIdentifier: "com.apple.springboard")
    private let browser = XCUIApplication(bundleIdentifier: "com.apple.SafariViewService")
    private var app: XCUIApplication!

    private func consent() {
        for owner in [system, app!, browser] {
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
        for owner in [app!, browser] {
            let query = secure ? owner.secureTextFields : owner.textFields
            let element = query.matching(NSPredicate(format: "label IN %@ OR identifier IN %@", labels, labels)).firstMatch
            if element.exists { return element }
        }
        return nil
    }

    private func replace(_ element: XCUIElement, with value: String) {
        func focused() -> Bool {
            for owner in [app!, browser] {
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
        for owner in [app!, browser] {
            for label in labels {
                // Safari renders Next/Done in an accessory toolbar, outside Keyboard.
                for query in [owner.toolbars.buttons, owner.keyboards.buttons] {
                    let button = query[label].firstMatch
                    if button.exists && button.isHittable { button.tap(); return }
                }
            }
        }
    }

    func testSandboxLoginLogout() throws {
        continueAfterFailure = false
        let environment = ProcessInfo.processInfo.environment
        guard let bundle = environment["SDK_APP_BUNDLE_ID"],
              let username = environment["SDK_USERNAME"], !username.isEmpty,
              let password = environment["SDK_PASSWORD"], !password.isEmpty else {
            XCTFail("Private SDK test configuration has not been supplied.")
            return
        }
        app = XCUIApplication(bundleIdentifier: bundle)
        app.launch()
        let login = app.buttons["sample.oauth.login"]
        center(login, in: app)
        login.press(forDuration: 3)

        let emailLabels = ["Email input", "Username or email input", "Eメール入力欄", "Eメール", "メールアドレス入力欄"]
        let passwordLabels = ["Password input", "パスワード入力欄", "パスワード"]
        var failedAttempts = 0
        wait("Authentication form was not presented.") {
            if self.field(labels: emailLabels, secure: false) != nil || self.field(labels: passwordLabels, secure: true) != nil { return true }
            let failure = self.app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "ログインに失敗しました")).firstMatch
            if failure.exists {
                failedAttempts += 1
                self.evidence("Pre-form SDK login failure \(failedAttempts)")
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
        for owner in [app!, browser] {
            let button = owner.buttons.matching(NSPredicate(format: "label IN %@", ["Log In", "Sign In", "ログイン"])).firstMatch
            if button.exists {
                center(button, in: owner)
                button.tap()
                submitted = true
                break
            }
        }
        XCTAssertTrue(submitted, "No login form submit control was found.")
        let authenticated = app.staticTexts["ログイン済み"]
        wait("SDK did not enter its authenticated state.") {
            if authenticated.exists { return true }
            for owner in [self.app!, self.browser] {
                let terms = owner.buttons.matching(NSPredicate(format: "label CONTAINS %@", "同意して登録する")).firstMatch
                if terms.exists {
                    if terms.isEnabled { self.center(terms, in: owner); terms.tap() }
                    else { owner.swipeUp() }
                }
                let consent = owner.buttons["同意する"].firstMatch
                if consent.exists && consent.isEnabled { self.center(consent, in: owner); consent.tap() }
            }
            return false
        }
        for _ in 0..<10 {
            if authenticated.isHittable { break }
            app.swipeDown()
        }
        XCTAssertTrue(authenticated.isHittable, "Authenticated status is not visible for screenshot verification.")
        evidence("Authenticated SDK status", element: authenticated)

        let logout = app.buttons["sample.oauth.logout"]
        center(logout, in: app)
        logout.press(forDuration: 3)
        let unauthenticated = app.staticTexts["未ログイン"]
        wait("SDK did not clear its authenticated state.") { unauthenticated.exists && !authenticated.exists }
        app.terminate()
        app.launch()
        wait("Logout did not persist after app relaunch.") { unauthenticated.exists && !authenticated.exists }
        evidence("Unauthenticated SDK status after relaunch", element: unauthenticated)
    }
}
