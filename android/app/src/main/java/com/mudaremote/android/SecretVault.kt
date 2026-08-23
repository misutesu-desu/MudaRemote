package com.mudaremote.android

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.nio.ByteBuffer
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Encrypts values before they enter app preferences. Android backup is disabled. */
class SecretVault(context: Context) {
    private val preferences = context.getSharedPreferences("mudaremote_private", Context.MODE_PRIVATE)

    fun put(name: String, value: String) {
        preferences.edit().putString(name, encrypt(value)).apply()
    }

    fun get(name: String): String = read(name).getOrNull().orEmpty()

    /** Distinguishes a missing value from an unreadable encrypted value. */
    fun read(name: String): Result<String?> = runCatching {
        preferences.getString(name, null)?.let(::decrypt)
    }

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build()
        )
        return generator.generateKey()
    }

    private fun encrypt(value: String): String {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        val iv = cipher.iv
        val encrypted = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        return Base64.encodeToString(ByteBuffer.allocate(1 + iv.size + encrypted.size)
            .put(iv.size.toByte()).put(iv).put(encrypted).array(), Base64.NO_WRAP)
    }

    private fun decrypt(encoded: String): String {
        val all = Base64.decode(encoded, Base64.NO_WRAP)
        require(all.isNotEmpty()) { "Encrypted value is empty" }
        val ivLength = all[0].toInt() and 0xff
        require(ivLength > 0 && 1 + ivLength < all.size) { "Encrypted value is malformed" }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, all.copyOfRange(1, 1 + ivLength)))
        }
        return String(cipher.doFinal(all.copyOfRange(1 + ivLength, all.size)), Charsets.UTF_8)
    }

    private companion object { const val KEY_ALIAS = "mudaremote.profile.v1" }
}
