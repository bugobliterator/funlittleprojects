package com.sidbh.claudeusage.auth

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

class CredentialsStore(context: Context) {

    private val prefs: SharedPreferences = run {
        val app = context.applicationContext
        val masterKey = MasterKey.Builder(app)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            app,
            FILE_NAME,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    var sessionKey: String?
        get() = prefs.getString(KEY_SESSION, null)
        set(v) = prefs.edit().putString(KEY_SESSION, v).apply()

    var orgId: String?
        get() = prefs.getString(KEY_ORG, null)
        set(v) = prefs.edit().putString(KEY_ORG, v).apply()

    var userAgent: String?
        get() = prefs.getString(KEY_UA, null)
        set(v) = prefs.edit().putString(KEY_UA, v).apply()

    var useMock: Boolean
        get() = prefs.getBoolean(KEY_USE_MOCK, false)
        set(v) = prefs.edit().putBoolean(KEY_USE_MOCK, v).apply()

    fun isConfigured(): Boolean =
        useMock || (!sessionKey.isNullOrBlank() && !orgId.isNullOrBlank())

    fun isLoggedIn(): Boolean =
        !sessionKey.isNullOrBlank() && !orgId.isNullOrBlank()

    fun clearLogin() {
        prefs.edit()
            .remove(KEY_SESSION)
            .remove(KEY_ORG)
            .remove(KEY_UA)
            .apply()
    }

    fun clearAll() {
        prefs.edit().clear().apply()
    }

    companion object {
        private const val FILE_NAME = "claude_usage_secure"
        private const val KEY_SESSION = "session_key"
        private const val KEY_ORG = "org_id"
        private const val KEY_UA = "user_agent"
        private const val KEY_USE_MOCK = "use_mock"
    }
}
