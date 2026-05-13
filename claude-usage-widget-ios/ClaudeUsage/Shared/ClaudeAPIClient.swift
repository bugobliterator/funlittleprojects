import Foundation

/// Talks to claude.ai's consumer usage endpoint. Auth is the `sessionKey` cookie captured
/// from an in-app WKWebView login. Mirrors the Android `ClaudeAiUsageRepository`.
struct ClaudeAPIClient {
    static let fallbackUserAgent =
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

    let credentials: CredentialsStore
    let session: URLSession

    init(credentials: CredentialsStore = .shared, session: URLSession = .shared) {
        self.credentials = credentials
        self.session = session
    }

    func fetch() async -> UsageResult {
        guard let sessionKey = credentials.sessionKey, !sessionKey.isEmpty,
              let orgId = credentials.orgId, !orgId.isEmpty else {
            return .notConfigured
        }
        let ua = credentials.userAgent ?? Self.fallbackUserAgent

        guard let url = URL(string: "https://claude.ai/api/organizations/\(orgId)/usage") else {
            return .networkError("bad url")
        }
        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        req.setValue("sessionKey=\(sessionKey)", forHTTPHeaderField: "Cookie")
        req.setValue(ua, forHTTPHeaderField: "User-Agent")
        req.setValue("*/*", forHTTPHeaderField: "Accept")
        req.setValue("en-US,en;q=0.9", forHTTPHeaderField: "Accept-Language")
        req.setValue("web_claude_ai", forHTTPHeaderField: "anthropic-client-platform")
        req.setValue("1.0.0", forHTTPHeaderField: "anthropic-client-version")
        req.setValue("https://claude.ai/settings/usage", forHTTPHeaderField: "Referer")
        req.timeoutInterval = 20

        do {
            let (data, response) = try await session.data(for: req)
            guard let http = response as? HTTPURLResponse else {
                return .networkError("no http response")
            }
            switch http.statusCode {
            case 401, 403:
                return .authError(http.statusCode)
            case 200..<300:
                let envelope = try JSONDecoder().decode(UsageEnvelope.self, from: data)
                return .success(envelope, fetchedAt: Date())
            default:
                return .networkError("HTTP \(http.statusCode)")
            }
        } catch let DecodingError.dataCorrupted(ctx) {
            return .networkError("parse: \(ctx.debugDescription)")
        } catch {
            return .networkError(error.localizedDescription)
        }
    }
}

/// Returns a synthetic usage envelope for the "Use mock data" toggle, so the widget design
/// is visible without a live session.
enum MockUsage {
    static func envelope() -> UsageEnvelope {
        let json = """
        {
          "five_hour":   { "utilization": 38, "resets_at": "\(iso(plus: 60 * 60 * 2))" },
          "seven_day_opus": { "utilization": 64, "resets_at": "\(iso(plus: 60 * 60 * 24 * 3))" }
        }
        """
        return try! JSONDecoder().decode(UsageEnvelope.self, from: Data(json.utf8))
    }

    private static func iso(plus seconds: TimeInterval) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f.string(from: Date().addingTimeInterval(seconds))
    }
}
