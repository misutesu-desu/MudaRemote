package com.mudaremote.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.widget.Toast
import androidx.core.app.NotificationCompat
import com.chaquo.python.Python
import java.io.File

class MudaRemoteService : Service() {
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Satisfy the startForegroundService() contract on every delivery, then act.
        createChannel()
        startForeground(NOTIFICATION_ID, notification(if (isRunning) "Running in the background" else "Starting..."))
        when (intent?.action) {
            ACTION_STOP -> stopRuntime()
            else -> startRuntime()
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        stopPython()
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
        isRunning = false
        super.onDestroy()
    }

    private fun startRuntime() {
        isRunning = true
        updateNotification("Acquiring wake lock...")
        val manager = getSystemService(PowerManager::class.java)
        wakeLock = manager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "MudaRemote:runtime").also {
            it.setReferenceCounted(false)
            it.acquire(WAKE_LOCK_TIMEOUT_MS)
        }
        try {
            PythonRuntime.ensureStarted(applicationContext)
            val vault = SecretVault(this)
            val profiles = launchProfiles.ifBlank { vault.get("profiles").ifBlank { vault.get("profile") } }
            val tokens = launchTokens.ifBlank { vault.get("tokens").ifBlank { vault.get("token") } }
            if (profiles.isBlank() || tokens.isBlank()) throw IllegalStateException("Save a profile and token first.")
            val profileCount = runCatching { org.json.JSONObject(profiles).length() }.getOrDefault(1)
            updateNotification("Running $profileCount profile(s) in the background")
            Python.getInstance().getModule("android_bridge").callAttr("start", profiles, tokens, filesDir.absolutePath)
            appendLocalLog("[INFO] [ANDROID] Foreground service started successfully.")
        } catch (error: Exception) {
            isRunning = false
            appendLocalLog("[ERROR] [ANDROID] Runtime failed to start: ${error.message}")
            Toast.makeText(this, "Start failed: ${error.message}", Toast.LENGTH_LONG).show()
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    private fun stopRuntime() {
        stopPython()
        appendLocalLog("[INFO] [ANDROID] Foreground service stopped by user.")
        isRunning = false
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun stopPython() {
        if (Python.isStarted()) {
            runCatching { Python.getInstance().getModule("android_bridge").callAttr("stop") }
        }
    }

    private fun updateNotification(status: String) {
        val manager = getSystemService(NotificationManager::class.java)
        manager?.notify(NOTIFICATION_ID, notification(status))
    }

    private fun appendLocalLog(line: String) {
        runCatching {
            File(filesDir, LOG_FILE).appendText(line + "\n")
        }
    }

    private fun notification(status: String): Notification {
        val openIntent = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val stopIntent = PendingIntent.getService(
            this, 1, Intent(this, MudaRemoteService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_notify)
            .setContentTitle("MudaRemote is active")
            .setContentText(status)
            .setContentIntent(openIntent)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .addAction(0, "Stop", stopIntent)
            .build()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(CHANNEL_ID, "MudaRemote runtime", NotificationManager.IMPORTANCE_LOW).apply {
                setShowBadge(false)
            }
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    companion object {
        const val ACTION_STOP = "com.mudaremote.android.STOP"
        private const val CHANNEL_ID = "mudaremote_runtime"
        private const val NOTIFICATION_ID = 41
        private const val LOG_FILE = "mudaremote_android.log"
        private const val WAKE_LOCK_TIMEOUT_MS = 24L * 60L * 60L * 1000L

        private var launchProfiles = ""
        private var launchTokens = ""

        /** True while this service holds the foreground runtime. Read by MainActivity to sync status. */
        @Volatile
        var isRunning = false
            private set

        fun start(context: Context, profilesJson: String = "", tokensJson: String = "") {
            launchProfiles = profilesJson
            launchTokens = tokensJson
            val intent = Intent(context, MudaRemoteService::class.java)
            context.startForegroundService(intent)
        }

        fun stop(context: Context) {
            // startForegroundService keeps the stop path legal even if the app is backgrounded;
            // onStartCommand always calls startForeground() before handling ACTION_STOP.
            context.startForegroundService(
                Intent(context, MudaRemoteService::class.java).setAction(ACTION_STOP)
            )
        }
    }
}
