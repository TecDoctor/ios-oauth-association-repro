import XCTest

final class BrowserPresentationTests: XCTestCase {
    func testAuthenticationBrowserOpens() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment["PROBE_AUTOSTART"] = "1"
        app.launch()
        let system = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let browser = XCUIApplication(bundleIdentifier: "com.apple.SafariViewService")
        let deadline = Date().addingTimeInterval(1000)
        var attempt = 1
        while Date() < deadline {
            let status = app.staticTexts["probe-status"]
            if status.exists && status.label == "association_failure" {
                let screenshot = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
                screenshot.name = "Association rejection on attempt \(attempt)"
                screenshot.lifetime = .keepAlways
                add(screenshot)
                // Retry only this terminal native error, preserving the installed app and process.
                Thread.sleep(forTimeInterval: 10)
                if Date() >= deadline { break }
                let start = app.buttons["Start authentication probe"]
                XCTAssertTrue(start.waitForExistence(timeout: 30))
                start.tap()
                attempt += 1
                continue
            }
            let terminalErrors = ["other_session_failure", "start_rejected",
                                  "presentation_context_invalid", "configuration_failure", "empty_completion"]
            if status.exists && terminalErrors.contains(status.label) {
                let screenshot = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
                screenshot.name = "Terminal native session error"
                screenshot.lifetime = .keepAlways
                add(screenshot)
                XCTFail("The native authentication session reported a terminal error.")
                return
            }
            for owner in [system, app, browser] {
                for label in ["Continue", "Allow"] {
                    let button = owner.alerts.buttons[label].firstMatch
                    if button.exists && button.isHittable { button.tap() }
                }
            }
            if app.webViews.firstMatch.exists || browser.webViews.firstMatch.exists {
                let screenshot = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
                screenshot.name = "Authentication browser presented"
                screenshot.lifetime = .keepAlways
                add(screenshot)
                return
            }
            Thread.sleep(forTimeInterval: 1)
        }
        let screenshot = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        screenshot.name = "Browser presentation not observed"
        screenshot.lifetime = .keepAlways
        add(screenshot)
        XCTFail("Authentication browser was not observed within the session allowance.")
    }
}
