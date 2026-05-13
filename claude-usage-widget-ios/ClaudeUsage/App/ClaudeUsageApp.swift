import SwiftUI
import WidgetKit

@main
struct ClaudeUsageApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .onAppear {
                    // Nudge the widget to re-run getTimeline whenever the user opens the
                    // app. Required after fresh installs where WidgetKit otherwise keeps
                    // serving the previous build's cached timeline. Cheap to call.
                    WidgetCenter.shared.reloadAllTimelines()
                }
        }
    }
}
