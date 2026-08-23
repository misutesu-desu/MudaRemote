package com.mudaremote.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.widget.Toast
import androidx.core.app.NotificationCompat
import com.chaquo.python.Python
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit
import org.json.JSONObject

class MudaRemoteService : Service() {
    enum class RuntimeState { STOPPED, STARTING, RUNNING, STOPPING }

    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null
    private lateinit var commandExecutor: ScheduledExecutorService
    private var runtimeWatch: ScheduledFuture<*>? = null
    @Volatile private var latestCommandStartId = 0
    @Volatile private var latestCommandIsStop = false
    @Volatile private var lastStopStartId = 0
    @Volatile private var destroyed = false
    private val mainHandler = Handler(Looper.getMainLooper())
    private var activeProfiles = JSONObject()
    private var activeTokens = JSONObject()

    override fun onCreate() {
        super.onCreate()
        commandExecutor = Executors.newSingleThreadScheduledExecutor { runnable ->
            Thread(runnable, "MudaRemote-ServiceCommands")
        }
        appendLocalLog("[INFO] [ANDROID] Service created (pid ${android.os.Process.myPid()}).")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Satisfy the startForegroundService() contract on every delivery, then act.
        createChannel()
        val isStop = intent?.action == ACTION_STOP
        val wasActive = runtimeState != RuntimeState.STOPPED
        runtimeState = if (isStop) RuntimeState.STOPPING else RuntimeState.STARTING
        latestCommandIsStop = isStop
        latestCommandStartId = startId
        if (isStop) lastStopStartId = startId

        val commandVault = SecretVault(this)
        if (isStop) {
            // Persist user intent before asynchronous teardown so START_STICKY
            // can never resurrect a runtime which the user already stopped.
            commandVault.put(DESIRED_RUNNING_KEY, "false")
            commandVault.put(ACTIVE_PROFILES_KEY, "{}")
            commandVault.put(ACTIVE_TOKENS_KEY, "{}")
        } else if (intent != null) {
            commandVault.put(DESIRED_RUNNING_KEY, "true")
            persistPendingSelection(
                commandVault,
                intent.getStringExtra(EXTRA_PROFILES).orEmpty(),
                intent.getStringExtra(EXTRA_TOKENS).orEmpty(),
                appendToSession = wasActive,
            )
        }
        startForeground(
            NOTIFICATION_ID,
            notification(if (isStop) "Stopping..." else if (wasActive) "Adding profile(s)..." else "Starting...")
        )

        if (isStop) {
            appendLocalLog("[INFO] [ANDROID] Stop-all requested.")
            commandExecutor.execute { stopRuntime(startId) }
        } else {
            val stickyRestart = intent == null
            if (stickyRestart) {
                appendLocalLog("[WARN] [ANDROID] System restarted the service (START_STICKY). Restoring the active selection...")
            } else {
                appendLocalLog("[INFO] [ANDROID] Start/add requested.")
            }
            val profilesJson = intent?.getStringExtra(EXTRA_PROFILES).orEmpty()
            val tokensJson = intent?.getStringExtra(EXTRA_TOKENS).orEmpty()
            commandExecutor.execute {
                startRuntime(profilesJson, tokensJson, stickyRestart, wasActive, startId)
            }
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        destroyed = true
        appendLocalLog("[INFO] [ANDROID] Service destroyed.")
        stopRuntimeWatch()
        commandExecutor.shutdownNow()
        if (runtimeState != RuntimeState.STOPPED) {
            runCatching { stopPython(timeoutSeconds = 2.0) }
        }
        releaseLocks()
        runtimeState = RuntimeState.STOPPED
        super.onDestroy()
    }

    private fun startRuntime(
        profilesJson: String,
        tokensJson: String,
        stickyRestart: Boolean,
        appendToSession: Boolean,
        startId: Int,
    ) {
        var hadActiveRuntime = false
        try {
            PythonRuntime.ensureStarted(applicationContext)
            val vault = SecretVault(this)
            if (stickyRestart && vault.get(DESIRED_RUNNING_KEY) != "true") {
                appendLocalLog("[INFO] [ANDROID] Sticky restart ignored because the last requested state is stopped.")
                finishStoppedRuntime(startId, stoppedByUser = true)
                return
            }
            val requestProfilesText = profilesJson.ifBlank {
                if (stickyRestart) vault.get(ACTIVE_PROFILES_KEY) else ""
            }
            val requestTokensText = tokensJson.ifBlank {
                if (stickyRestart) vault.get(ACTIVE_TOKENS_KEY) else "{}"
            }
            if (requestProfilesText.isBlank()) {
                throw IllegalStateException("No active profile selection is available to restore.")
            }
            val requestProfiles = JSONObject(requestProfilesText)
            val requestTokens = JSONObject(requestTokensText.ifBlank { "{}" })
            if (requestProfiles.length() == 0) {
                throw IllegalStateException("Select at least one runnable profile.")
            }
            if (!appendToSession) {
                activeProfiles = JSONObject()
                activeTokens = JSONObject()
            }
            hadActiveRuntime = appendToSession && activeProfiles.length() > 0

            ensureLocks()
            var response: JSONObject
            var status: String
            var loggedWait = false
            while (true) {
                if (startWasCancelled(startId)) {
                    appendLocalLog("[INFO] [ANDROID] Skipped a start request superseded by Stop-all.")
                    return
                }
                val responseText = Python.getInstance().getModule("android_bridge")
                    .callAttr("start", requestProfiles.toString(), requestTokens.toString(), filesDir.absolutePath)
                    .toString()
                response = runCatching { JSONObject(responseText) }
                    .getOrElse { JSONObject().put("status", responseText) }
                status = response.optString("status", "error")
                if (status != "stopping") break

                if (!loggedWait) {
                    appendLocalLog("[WARN] [ANDROID] New selection queued until the previous account workers exit.")
                    loggedWait = true
                }
                if (latestCommandStartId == startId) {
                    runtimeState = RuntimeState.STOPPING
                    updateNotification("Waiting for previous account workers to stop...")
                }
                Thread.sleep(STOP_POLL_INTERVAL_MS)
            }

            if (startWasCancelled(startId)) return
            when (status) {
                "started", "added", "already-active" -> {
                    mergeInto(activeProfiles, requestProfiles)
                    mergeInto(activeTokens, requestTokens)
                    pruneToActiveResponse(activeProfiles, activeTokens, response)
                    if (!startWasCancelled(startId)) {
                        vault.put(ACTIVE_PROFILES_KEY, activeProfiles.toString())
                        vault.put(ACTIVE_TOKENS_KEY, activeTokens.toString())
                        vault.put(DESIRED_RUNNING_KEY, "true")
                    }

                    val profileCount = response.optJSONArray("active_profiles")?.length()
                        ?: activeProfiles.length()
                    val accountCount = response.optInt("account_count", profileCount)
                    if (!latestCommandIsStop) {
                        runtimeState = RuntimeState.RUNNING
                        updateNotification("Running $profileCount profile(s), $accountCount account(s)")
                        ensureRuntimeWatch()
                    }
                    val message = when (status) {
                        "added" -> "Added profile(s) to the existing runtime"
                        "already-active" -> "Requested profile(s) already active; no duplicate workers started"
                        else -> "Foreground runtime started"
                    }
                    appendLocalLog("[INFO] [ANDROID] $message ($profileCount profile(s), $accountCount account(s)).")
                }
                "no-runnable-profiles" -> throw IllegalStateException("Selected profile(s) have no usable account token.")
                else -> throw IllegalStateException("Runtime rejected the request ($status).")
            }
        } catch (_: InterruptedException) {
            Thread.currentThread().interrupt()
        } catch (error: Exception) {
            if (destroyed || startWasCancelled(startId)) return
            appendLocalLog("[ERROR] [ANDROID] Runtime failed to start: ${error.message}")
            showToast("Start failed: ${error.message}")
            if (hadActiveRuntime && bridgeIsRunning(defaultOnError = true)) {
                runtimeState = RuntimeState.RUNNING
                updateNotification("Existing profiles continue running")
                ensureRuntimeWatch()
                return
            }
            if (latestCommandStartId == startId) {
                SecretVault(this).put(DESIRED_RUNNING_KEY, "false")
            }
            val stopped = stopSelfResult(startId)
            if (stopped) {
                runtimeState = RuntimeState.STOPPED
                releaseLocks()
                stopForeground(STOP_FOREGROUND_REMOVE)
            } else {
                runtimeState = RuntimeState.STARTING
                updateNotification("Waiting for the next start request...")
            }
        }
    }

    private fun stopRuntime(startId: Int) {
        val response = runCatching { stopPython() }
            .getOrElse { error ->
                appendLocalLog("[ERROR] [ANDROID] Runtime stop failed: ${error.message}")
                JSONObject().put("status", "stopping")
            }
        val status = response.optString("status", "stopping")
        if (status == "stopped") {
            finishStoppedRuntime(startId, stoppedByUser = true)
        } else if (latestCommandStartId == startId) {
            runtimeState = RuntimeState.STOPPING
            updateNotification("Stopping account workers...")
            appendLocalLog("[WARN] [ANDROID] Stop timed out; the service is retaining ownership until workers exit.")
            showToast("Still stopping account workers. A queued Run will start automatically afterward.")
            ensureRuntimeWatch()
        }
    }

    private fun stopPython(timeoutSeconds: Double = 12.0): JSONObject {
        if (!Python.isStarted()) return JSONObject().put("status", "stopped")
        val raw = Python.getInstance().getModule("android_bridge")
            .callAttr("stop", timeoutSeconds)
            .toString()
        return runCatching { JSONObject(raw) }.getOrElse { JSONObject().put("status", raw) }
    }

    private fun bridgeIsRunning(defaultOnError: Boolean = false): Boolean {
        if (!Python.isStarted()) return false
        return runCatching {
            Python.getInstance().getModule("android_bridge").callAttr("is_running").toString().toBoolean()
        }.getOrDefault(defaultOnError)
    }

    private fun ensureRuntimeWatch() {
        if (runtimeWatch?.isDone == false && runtimeWatch?.isCancelled == false) return
        runtimeWatch = commandExecutor.scheduleWithFixedDelay({
            val watchedState = runtimeState
            val watchedStartId = latestCommandStartId
            if ((watchedState == RuntimeState.RUNNING || watchedState == RuntimeState.STOPPING) &&
                !bridgeIsRunning(defaultOnError = true) &&
                runtimeState == watchedState &&
                latestCommandStartId == watchedStartId
            ) {
                finishStoppedRuntime(watchedStartId, stoppedByUser = watchedState == RuntimeState.STOPPING)
            }
        }, 1, 1, TimeUnit.SECONDS)
    }

    private fun stopRuntimeWatch() {
        runtimeWatch?.cancel(false)
        runtimeWatch = null
    }

    private fun finishStoppedRuntime(startId: Int, stoppedByUser: Boolean) {
        activeProfiles = JSONObject()
        activeTokens = JSONObject()
        val isLatestCommand = latestCommandStartId == startId
        if (isLatestCommand) {
            val vault = SecretVault(this)
            vault.put(ACTIVE_PROFILES_KEY, "{}")
            vault.put(ACTIVE_TOKENS_KEY, "{}")
            vault.put(DESIRED_RUNNING_KEY, "false")
        }
        releaseLocks()
        val stopped = stopSelfResult(startId)
        if (stopped) {
            runtimeState = RuntimeState.STOPPED
            stopRuntimeWatch()
            stopForeground(STOP_FOREGROUND_REMOVE)
            appendLocalLog(
                if (stoppedByUser) {
                    "[INFO] [ANDROID] Foreground service stopped by user; all workers exited."
                } else {
                    "[WARN] [ANDROID] All account workers exited; foreground service stopped automatically."
                }
            )
        } else {
            runtimeState = RuntimeState.STARTING
            updateNotification("Starting next selection...")
            appendLocalLog("[INFO] [ANDROID] Previous workers stopped; processing the queued start request.")
        }
    }

    private fun startWasCancelled(startId: Int): Boolean =
        destroyed || lastStopStartId > startId || (latestCommandStartId > startId && latestCommandIsStop)

    private fun ensureLocks() {
        if (wakeLock?.isHeld != true) {
            val powerManager = getSystemService(PowerManager::class.java)
            wakeLock = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "MudaRemote:runtime").also {
                it.setReferenceCounted(false)
                it.acquire(WAKE_LOCK_TIMEOUT_MS)
            }
        }
        if (wifiLock?.isHeld != true) {
            val wifiManager = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            val mode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q)
                WifiManager.WIFI_MODE_FULL_LOW_LATENCY else
                @Suppress("DEPRECATION") WifiManager.WIFI_MODE_FULL_HIGH_PERF
            wifiLock = wifiManager.createWifiLock(mode, "MudaRemote:wifi").also {
                it.setReferenceCounted(false)
                it.acquire()
            }
        }
    }

    private fun releaseLocks() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
        wifiLock?.let { if (it.isHeld) it.release() }
        wifiLock = null
    }

    private fun mergeInto(target: JSONObject, source: JSONObject) {
        source.keys().forEach { key -> target.put(key, source.get(key)) }
    }

    private fun persistPendingSelection(
        vault: SecretVault,
        profilesJson: String,
        tokensJson: String,
        appendToSession: Boolean,
    ) {
        if (profilesJson.isBlank()) return
        runCatching {
            val profiles = if (appendToSession) {
                JSONObject(vault.get(ACTIVE_PROFILES_KEY).ifBlank { "{}" })
            } else {
                JSONObject()
            }
            val tokens = if (appendToSession) {
                JSONObject(vault.get(ACTIVE_TOKENS_KEY).ifBlank { "{}" })
            } else {
                JSONObject()
            }
            mergeInto(profiles, JSONObject(profilesJson))
            mergeInto(tokens, JSONObject(tokensJson.ifBlank { "{}" }))
            vault.put(ACTIVE_PROFILES_KEY, profiles.toString())
            vault.put(ACTIVE_TOKENS_KEY, tokens.toString())
        }.onFailure { error ->
            appendLocalLog("[WARN] [ANDROID] Could not persist the pending selection: ${error.message}")
        }
    }

    private fun pruneToActiveResponse(profiles: JSONObject, tokens: JSONObject, response: JSONObject) {
        val active = response.optJSONArray("active_profiles") ?: return
        val names = (0 until active.length()).mapNotNull { index ->
            active.optString(index).takeIf { it.isNotBlank() }
        }.toSet()
        profiles.keys().asSequence().toList().filterNot(names::contains).forEach(profiles::remove)
        tokens.keys().asSequence().toList().filterNot(names::contains).forEach(tokens::remove)
    }

    private fun showToast(message: String) {
        mainHandler.post { Toast.makeText(this, message, Toast.LENGTH_LONG).show() }
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
        private const val EXTRA_PROFILES = "com.mudaremote.android.PROFILES"
        private const val EXTRA_TOKENS = "com.mudaremote.android.TOKENS"
        private const val CHANNEL_ID = "mudaremote_runtime"
        private const val NOTIFICATION_ID = 41
        private const val LOG_FILE = "mudaremote_android.log"
        private const val WAKE_LOCK_TIMEOUT_MS = 24L * 60L * 60L * 1000L
        private const val ACTIVE_PROFILES_KEY = "active_runtime_profiles"
        private const val ACTIVE_TOKENS_KEY = "active_runtime_tokens"
        private const val DESIRED_RUNNING_KEY = "active_runtime_desired"
        private const val STOP_POLL_INTERVAL_MS = 200L

        /** Process-local state for Activity status; the encrypted snapshot handles sticky restarts. */
        @Volatile
        var runtimeState = RuntimeState.STOPPED
            private set

        val isRunning: Boolean
            get() = runtimeState != RuntimeState.STOPPED

        fun start(context: Context, profilesJson: String = "", tokensJson: String = "") {
            val intent = Intent(context, MudaRemoteService::class.java)
                .putExtra(EXTRA_PROFILES, profilesJson)
                .putExtra(EXTRA_TOKENS, tokensJson)
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
