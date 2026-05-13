import Foundation
import Security

/// Stores the claude.ai sessionKey in the Keychain (shared via access group with the widget),
/// and the orgId/userAgent/useMock flags in shared UserDefaults so the widget can read them.
///
/// Keychain access group requires the `keychain-access-groups` entitlement on both targets,
/// with a shared prefix like `$(AppIdentifierPrefix)com.sidbh.claudeusage.shared`. The same
/// access group string must be passed to all Keychain calls below.
struct CredentialsStore {
    static let shared = CredentialsStore()

    private let defaults = AppGroup.sharedDefaults
    private let keychainService = "com.sidbh.claudeusage.session"
    private let keychainAccount = "claudeAi"
    private let keychainAccessGroup =
        Bundle.main.object(forInfoDictionaryKey: "KeychainAccessGroup") as? String

    enum Key {
        static let orgId = "org_id"
        static let userAgent = "user_agent"
        static let useMock = "use_mock"
    }

    var sessionKey: String? {
        get { readSession() }
        set {
            if let v = newValue, !v.isEmpty { writeSession(v) } else { deleteSession() }
        }
    }

    var orgId: String? {
        get { defaults.string(forKey: Key.orgId) }
        set { defaults.set(newValue, forKey: Key.orgId) }
    }

    var userAgent: String? {
        get { defaults.string(forKey: Key.userAgent) }
        set { defaults.set(newValue, forKey: Key.userAgent) }
    }

    var useMock: Bool {
        get { defaults.bool(forKey: Key.useMock) }
        set { defaults.set(newValue, forKey: Key.useMock) }
    }

    var isLoggedIn: Bool {
        guard let s = sessionKey, !s.isEmpty,
              let o = orgId, !o.isEmpty else { return false }
        return true
    }

    var isConfigured: Bool { useMock || isLoggedIn }

    func clearLogin() {
        deleteSession()
        defaults.removeObject(forKey: Key.orgId)
        defaults.removeObject(forKey: Key.userAgent)
    }

    func clearAll() {
        clearLogin()
        defaults.removeObject(forKey: Key.useMock)
    }

    // MARK: - Keychain

    private func keychainQuery() -> [String: Any] {
        var q: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keychainAccount,
        ]
        if let group = keychainAccessGroup, !group.isEmpty {
            q[kSecAttrAccessGroup as String] = group
        }
        return q
    }

    private func writeSession(_ value: String) {
        let data = Data(value.utf8)
        let q = keychainQuery()
        let attrs: [String: Any] = [
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock,
        ]
        let updateStatus = SecItemUpdate(q as CFDictionary, attrs as CFDictionary)
        if updateStatus == errSecItemNotFound {
            var add = q
            add[kSecValueData as String] = data
            add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
            SecItemAdd(add as CFDictionary, nil)
        }
    }

    private func readSession() -> String? {
        var q = keychainQuery()
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        let status = SecItemCopyMatching(q as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private func deleteSession() {
        SecItemDelete(keychainQuery() as CFDictionary)
    }
}
