import Foundation

struct UsageEnvelope: Decodable {
    let fiveHour: UsageBucket?
    let sevenDay: UsageBucket?
    let sevenDayOpus: UsageBucket?
    let sevenDaySonnet: UsageBucket?

    enum CodingKeys: String, CodingKey {
        case fiveHour = "five_hour"
        case sevenDay = "seven_day"
        case sevenDayOpus = "seven_day_opus"
        case sevenDaySonnet = "seven_day_sonnet"
    }
}

struct UsageBucket: Decodable {
    let utilization: Double?
    let resetsAt: Date?

    enum CodingKeys: String, CodingKey {
        case utilization
        case resetsAt = "resets_at"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        utilization = try c.decodeIfPresent(Double.self, forKey: .utilization)
        if let s = try c.decodeIfPresent(String.self, forKey: .resetsAt) {
            resetsAt = ISO8601DateFormatter.claudeAi.date(from: s)
                ?? ISO8601DateFormatter.claudeAiFractional.date(from: s)
        } else {
            resetsAt = nil
        }
    }
}

extension ISO8601DateFormatter {
    static let claudeAi: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()
    static let claudeAiFractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
}

enum UsageResult {
    case success(UsageEnvelope, fetchedAt: Date)
    case authError(Int)
    case networkError(String)
    case notConfigured
}
