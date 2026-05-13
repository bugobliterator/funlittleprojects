import Foundation

/// What the widget renders. The store persists `Loaded` values across launches via App Group
/// UserDefaults so the widget extension can read the last good state instantly during reload.
enum WidgetState: Equatable {
    case unconfigured
    case loading
    case authError
    case networkError(String)
    case loaded(Loaded)

    struct Loaded: Equatable, Codable {
        var fiveHourPct: Double
        var fiveHourResetsAt: Date?
        /// `nil` means the 7-day bucket wasn't present at all; render an em-dash.
        var sevenDayPct: Double?
        var sevenDayResetsAt: Date?
        /// "7-day Opus" when the Opus-specific bucket exists; "7-day" when falling back.
        var sevenDayLabel: String
        var fetchedAt: Date
        var mock: Bool
    }
}
