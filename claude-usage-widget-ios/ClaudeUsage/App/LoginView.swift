import SwiftUI
import WebKit
import UIKit

/// In-app WKWebView for capturing the claude.ai `sessionKey` and `lastActiveOrg` cookies.
///
/// Same constraints as Android:
/// - Google OAuth is silently blocked inside embedded WebViews (signal: it never sets the
///   session cookie). The reliable path is email magic-link; the "Paste link" toolbar action
///   loads a URL the user copied from the email.
/// - claude.ai is a SPA — `didFinish` doesn't fire after in-app History API navigation. We
///   poll the cookie store every 2 s and also expose a manual "Done" button as a fallback.
struct LoginView: View {
    var onCaptured: (_ sessionKey: String, _ orgId: String, _ userAgent: String?) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var status: String = "Sign in to claude.ai. We'll capture the session cookie automatically."

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ClaudeWebView(status: $status) { sessionKey, orgId, ua in
                    onCaptured(sessionKey, orgId, ua)
                    dismiss()
                }
                Text(status)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(10)
            }
            .navigationTitle("Log in to Claude")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button {
                            NotificationCenter.default.post(name: .pasteLinkRequested, object: nil)
                        } label: {
                            Label("Paste link", systemImage: "doc.on.clipboard")
                        }
                        Button {
                            NotificationCenter.default.post(name: .manualDoneRequested, object: nil)
                        } label: {
                            Label("Done", systemImage: "checkmark.circle")
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                }
            }
        }
    }
}

extension Notification.Name {
    static let pasteLinkRequested = Notification.Name("ClaudeUsage.pasteLinkRequested")
    static let manualDoneRequested = Notification.Name("ClaudeUsage.manualDoneRequested")
}

private let chromeIOSUserAgent =
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

private struct ClaudeWebView: UIViewRepresentable {
    @Binding var status: String
    var onCaptured: (_ sessionKey: String, _ orgId: String, _ userAgent: String?) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(parent: self) }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = WKWebsiteDataStore.default()
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.customUserAgent = chromeIOSUserAgent
        webView.navigationDelegate = context.coordinator
        context.coordinator.webView = webView

        let req = URLRequest(url: URL(string: "https://claude.ai/login")!)
        webView.load(req)

        context.coordinator.startPolling()
        context.coordinator.observePasteAndDone()
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKNavigationDelegate {
        let parent: ClaudeWebView
        weak var webView: WKWebView?
        private var pollTask: Task<Void, Never>?
        private var captured = false
        private var observers: [NSObjectProtocol] = []

        init(parent: ClaudeWebView) { self.parent = parent }

        deinit {
            pollTask?.cancel()
            observers.forEach { NotificationCenter.default.removeObserver($0) }
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            Task { await tryCapture() }
        }

        func startPolling() {
            pollTask = Task { [weak self] in
                while !(Task.isCancelled) {
                    try? await Task.sleep(nanoseconds: 2_000_000_000)
                    guard let self else { return }
                    if self.captured { return }
                    await self.tryCapture()
                }
            }
        }

        func observePasteAndDone() {
            let center = NotificationCenter.default
            observers.append(center.addObserver(forName: .pasteLinkRequested, object: nil, queue: .main) { [weak self] _ in
                self?.pasteLinkFromClipboard()
            })
            observers.append(center.addObserver(forName: .manualDoneRequested, object: nil, queue: .main) { [weak self] _ in
                Task { await self?.tryCapture(force: true) }
            })
        }

        private func pasteLinkFromClipboard() {
            guard let pasted = UIPasteboard.general.url ?? UIPasteboard.general.string.flatMap({ URL(string: $0) }) else {
                Task { @MainActor in self.parent.status = "No URL in clipboard. Copy the magic link from your email first." }
                return
            }
            webView?.load(URLRequest(url: pasted))
        }

        @MainActor
        private func tryCapture(force: Bool = false) async {
            guard let webView else { return }
            let store = webView.configuration.websiteDataStore.httpCookieStore
            let cookies = await store.allCookies()
            let claudeCookies = cookies.filter { $0.domain.contains("claude.ai") }
            let session = claudeCookies.first(where: { $0.name == "sessionKey" })?.value
            let org = claudeCookies.first(where: { $0.name == "lastActiveOrg" })?.value

            guard let session, !session.isEmpty else {
                if force { parent.status = "Still loading. Sign in fully before tapping Done." }
                return
            }

            // sessionKey is enough — derive orgId from /api/organizations if the lastActiveOrg
            // cookie isn't set yet (claude.ai only sets it after you navigate to an org page).
            let orgId: String?
            if let org, !org.isEmpty {
                orgId = org
            } else {
                orgId = await fetchOrgId(sessionKey: session)
            }

            guard let orgId, !orgId.isEmpty else {
                if force { parent.status = "Got session but no organization. Open https://claude.ai and tap Done again." }
                return
            }

            captured = true
            pollTask?.cancel()
            parent.status = "Captured session. Loading your usage…"
            parent.onCaptured(session, orgId, chromeIOSUserAgent)
        }

        /// Asks claude.ai for the user's organizations using the captured sessionKey, and
        /// returns the first one's uuid. Used when `lastActiveOrg` cookie isn't set yet.
        private func fetchOrgId(sessionKey: String) async -> String? {
            guard let url = URL(string: "https://claude.ai/api/organizations") else { return nil }
            var req = URLRequest(url: url)
            req.setValue("sessionKey=\(sessionKey)", forHTTPHeaderField: "Cookie")
            req.setValue(chromeIOSUserAgent, forHTTPHeaderField: "User-Agent")
            req.setValue("*/*", forHTTPHeaderField: "Accept")
            req.setValue("web_claude_ai", forHTTPHeaderField: "anthropic-client-platform")
            req.setValue("1.0.0", forHTTPHeaderField: "anthropic-client-version")
            req.timeoutInterval = 10
            do {
                let (data, response) = try await URLSession.shared.data(for: req)
                guard let http = response as? HTTPURLResponse, http.statusCode == 200 else { return nil }
                guard let arr = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] else { return nil }
                return arr.first?["uuid"] as? String
            } catch {
                return nil
            }
        }
    }
}
