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
        while Date() < deadline {
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
