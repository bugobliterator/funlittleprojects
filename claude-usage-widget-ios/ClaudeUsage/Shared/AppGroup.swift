import Foundation

/// Identifier of the App Group shared between the host app and the widget extension.
/// Must match the App Group capability on both targets in Xcode.
enum AppGroup {
    static let identifier = "group.com.sidbh.claudeusage"

    static var sharedDefaults: UserDefaults {
        guard let defaults = UserDefaults(suiteName: identifier) else {
            preconditionFailure("App Group \(identifier) is missing. Enable it in both target Signing & Capabilities.")
        }
        return defaults
    }
}
