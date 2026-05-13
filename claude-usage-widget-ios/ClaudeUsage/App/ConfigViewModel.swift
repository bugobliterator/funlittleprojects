import Foundation
import SwiftUI
import WidgetKit

@MainActor
final class ConfigViewModel: ObservableObject {

    @Published var isLoggedIn: Bool = false
    @Published var useMock: Bool = false
    @Published var statusText: String = "Not logged in"
    @Published var previewLoaded: WidgetState.Loaded? = nil
    @Published var previewCaption: String = "Preview will update once the widget fetches data."

    private var credentials = CredentialsStore.shared
    private let stateStore = WidgetStateStore.shared

    init() {
        refreshLocalState()
    }

    var statusColor: Color {
        if useMock && isLoggedIn { return .yellow }
        if useMock { return .yellow }
        if isLoggedIn { return .green }
        return .gray
    }

    var canRefresh: Bool { isLoggedIn || useMock }

    func refreshLocalState() {
        isLoggedIn = credentials.isLoggedIn
        useMock = credentials.useMock
        previewLoaded = stateStore.loadedSnapshot()
        statusText = makeStatusText()
        previewCaption = makePreviewCaption()
    }

    func completeLogin(sessionKey: String, orgId: String, userAgent: String?) {
        credentials.sessionKey = sessionKey
        credentials.orgId = orgId
        credentials.userAgent = userAgent
        credentials.useMock = false
        refreshLocalState()
        Task { await refreshNow() }
    }

    func logout() {
        credentials.clearLogin()
        refreshLocalState()
        stateStore.save(.notConfigured, mock: useMock)
        WidgetCenter.shared.reloadAllTimelines()
    }

    func applyMockToggle(_ enabled: Bool) {
        credentials.useMock = enabled
        refreshLocalState()
        Task { await refreshNow() }
    }

    func refreshIfPossible() async {
        guard canRefresh else { return }
        await refreshNow()
    }

    func refreshNow() async {
        if useMock {
            stateStore.save(.success(MockUsage.envelope(), fetchedAt: Date()), mock: true)
        } else if credentials.isLoggedIn {
            let result = await ClaudeAPIClient(credentials: credentials).fetch()
            stateStore.save(result, mock: false)
        }
        refreshLocalState()
    }

    private func makeStatusText() -> String {
        switch (isLoggedIn, useMock) {
        case (true, true):   return "Logged in · showing mock data"
        case (true, false):  return "Logged in to claude.ai"
        case (false, true):  return "Using mock data"
        case (false, false): return "Not logged in"
        }
    }

    private func makePreviewCaption() -> String {
        guard let loaded = previewLoaded else {
            return "Log in to populate. Until then the widget shows a “Tap to log in” state."
        }
        let f = DateFormatter()
        f.dateFormat = "HH:mm"
        let suffix = loaded.mock ? " · mock" : ""
        return "Last fetched \(f.string(from: loaded.fetchedAt))\(suffix)."
    }
}
