import Foundation
import WidgetKit

/// Persists the latest `UsageResult` into App Group UserDefaults under a single JSON blob,
/// then nudges WidgetKit so the timeline reloads with the new value.
struct WidgetStateStore {
    static let shared = WidgetStateStore()

    private let defaults = AppGroup.sharedDefaults
    private let stateKey = "widget_state_v1"
    private let statusKey = "widget_status_v1"
    private let errorKey  = "widget_error_v1"

    private enum Status: String {
        case ok, auth, network, unconfigured
    }

    func save(_ result: UsageResult, mock: Bool) {
        switch result {
        case .success(let env, let fetchedAt):
            let pct5 = env.fiveHour?.utilization ?? -1
            let resets5 = env.fiveHour?.resetsAt
            let opus = env.sevenDayOpus
            let overall = env.sevenDay
            let useOverall = opus == nil && overall != nil
            let bucket = opus ?? overall
            let pct7 = bucket?.utilization
            let resets7 = bucket?.resetsAt

            let loaded = WidgetState.Loaded(
                fiveHourPct: pct5,
                fiveHourResetsAt: resets5,
                sevenDayPct: pct7,
                sevenDayResetsAt: resets7,
                sevenDayLabel: useOverall ? "7-day" : "7-day Opus",
                fetchedAt: fetchedAt,
                mock: mock,
            )
            if let data = try? JSONEncoder.iso.encode(loaded) {
                defaults.set(data, forKey: stateKey)
            }
            defaults.set(Status.ok.rawValue, forKey: statusKey)

        case .authError:
            defaults.set(Status.auth.rawValue, forKey: statusKey)

        case .networkError(let msg):
            defaults.set(Status.network.rawValue, forKey: statusKey)
            defaults.set(msg, forKey: errorKey)

        case .notConfigured:
            defaults.set(Status.unconfigured.rawValue, forKey: statusKey)
        }

        WidgetCenter.shared.reloadAllTimelines()
    }

    func load(isConfigured: Bool) -> WidgetState {
        guard isConfigured else { return .unconfigured }
        let raw = defaults.string(forKey: statusKey) ?? ""
        switch Status(rawValue: raw) {
        case .auth: return .authError
        case .network:
            if let cached = loadCached() { return .loaded(cached) }
            return .networkError(defaults.string(forKey: errorKey) ?? "network")
        case .ok:
            return loadCached().map(WidgetState.loaded) ?? .loading
        case .unconfigured, .none, .some:
            return loadCached().map(WidgetState.loaded) ?? .loading
        }
    }

    func loadedSnapshot() -> WidgetState.Loaded? { loadCached() }

    private func loadCached() -> WidgetState.Loaded? {
        guard let data = defaults.data(forKey: stateKey) else { return nil }
        return try? JSONDecoder.iso.decode(WidgetState.Loaded.self, from: data)
    }
}

extension JSONEncoder {
    static let iso: JSONEncoder = {
        let e = JSONEncoder()
        e.dateEncodingStrategy = .iso8601
        return e
    }()
}

extension JSONDecoder {
    static let iso: JSONDecoder = {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .iso8601
        return d
    }()
}
