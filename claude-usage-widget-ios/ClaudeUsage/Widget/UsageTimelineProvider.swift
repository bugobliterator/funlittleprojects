import WidgetKit
import Foundation

struct UsageEntry: TimelineEntry {
    let date: Date
    let state: WidgetState
}

/// Drives the widget timeline. iOS controls how often we actually run — the `after()` policy
/// is advisory. We refresh in the background up to roughly every 15 minutes, but the system
/// applies its own budget; expect fewer reloads on a quiet device.
struct UsageTimelineProvider: TimelineProvider {

    func placeholder(in context: Context) -> UsageEntry {
        UsageEntry(date: Date(), state: .loaded(.placeholder))
    }

    func getSnapshot(in context: Context, completion: @escaping (UsageEntry) -> Void) {
        let state = currentState()
        completion(UsageEntry(date: Date(), state: state))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<UsageEntry>) -> Void) {
        Task {
            let creds = CredentialsStore.shared
            if creds.useMock {
                WidgetStateStore.shared.save(.success(MockUsage.envelope(), fetchedAt: Date()), mock: true)
            } else if creds.isLoggedIn {
                let result = await ClaudeAPIClient(credentials: creds).fetch()
                WidgetStateStore.shared.save(result, mock: false)
            }

            let state = currentState()
            let now = Date()
            let next = now.addingTimeInterval(15 * 60)
            let entry = UsageEntry(date: now, state: state)
            completion(Timeline(entries: [entry], policy: .after(next)))
        }
    }

    private func currentState() -> WidgetState {
        let creds = CredentialsStore.shared
        return WidgetStateStore.shared.load(isConfigured: creds.isConfigured)
    }
}

extension WidgetState.Loaded {
    /// Used for placeholder/preview rendering before the timeline has any real data.
    static let placeholder = WidgetState.Loaded(
        fiveHourPct: 38,
        fiveHourResetsAt: Date().addingTimeInterval(60 * 60 * 2),
        sevenDayPct: 64,
        sevenDayResetsAt: Date().addingTimeInterval(60 * 60 * 24 * 3),
        sevenDayLabel: "7-day Opus",
        fetchedAt: Date(),
        mock: true,
    )
}
