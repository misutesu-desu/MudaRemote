package com.mudaremote.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
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
import org.json.JSONArray
import org.json.JSONObject

class MudaRemoteService : Service() {
    enum class RuntimeState { STOPPED, STARTING, RUNNING, STOPPING }

    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null
    private var lowLatencyWifiLock: WifiManager.WifiLock? = null
    private lateinit var commandExecutor: ScheduledExecutorService
    private var runtimeWatch: ScheduledFuture<*>? = null
    private var heartbeatTask: ScheduledFuture<*>? = null
    @Volatile private var workerRestartAttempts = 0
    @Volatile private var lastWorkerRestartAt = 0L
    @Volatile private var latestCommandStartId = 0
    @Volatile private var latestServiceStartId = 0
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
        heartbeatTask = commandExecutor.scheduleWithFixedDelay(
            { heartbeatTick() },
            KeepAlive.HEARTBEAT_INTERVAL_SECONDS,
            KeepAlive.HEARTBEAT_INTERVAL_SECONDS,
            TimeUnit.SECONDS
        )
    }

    /** Every minute while a runtime exists: heartbeat, push the watchdog back, keep the locks held. */
    private fun heartbeatTick() {
        if (destroyed) return
        val state = runtimeState
        if (state == RuntimeState.STOPPED) return
        KeepAlive.writeHeartbeat(this)
        KeepAlive.scheduleWatchdog(this)
        if (state == RuntimeState.RUNNING) {
            ensureLocks()
            if (workerRestartAttempts > 0 &&
                System.currentTimeMillis() - lastWorkerRestartAt > WORKER_BACKOFF_RESET_MS &&
                bridgeIsRunning(defaultOnError = false)
            ) {
                workerRestartAttempts = 0
                appendLocalLog("[INFO] [ANDROID] Account workers have been stable for 15 minutes; restart back-off reset.")
            }
        }
    }

    /** Foreground with the declared type; false when Android refuses (background start limits). */
    private fun enterForeground(status: String): Boolean {
        val shown = notification(status)
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                startForeground(NOTIFICATION_ID, shown, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
            } else {
                startForeground(NOTIFICATION_ID, shown)
            }
            true
        } catch (error: Exception) {
            appendLocalLog("[WARN] [ANDROID] Android refused to put the service in the foreground: ${error.message}")
            false
        }
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        // Swiping the app away must not stop the bot. Some phones kill the
        // process right after this, so ask for a restart check in a few seconds.
        if (runtimeState != RuntimeState.STOPPED && KeepAlive.shouldBeRunning(this)) {
            appendLocalLog("[INFO] [ANDROID] App removed from recents; runtime keeps running (restart check scheduled).")
            KeepAlive.scheduleWatchdog(this, KeepAlive.RESTART_SOON_MS)
        }
        super.onTaskRemoved(rootIntent)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        latestServiceStartId = startId
        // Satisfy the startForegroundService() contract on every delivery, then act.
        createChannel()
        if (intent?.action == ACTION_APPLY) {
            val previousState = runtimeState
            enterForeground(if (previousState == RuntimeState.STOPPING) "Stopping..." else "Running")
            if (previousState == RuntimeState.STOPPED) {
                appendLocalLog("[WARN] [ANDROID] Live apply ignored because the runtime is stopped.")
                showToast("Profile saved. Start the runtime to use the changes.")
                stopSelfResult(startId)
                stopForeground(STOP_FOREGROUND_REMOVE)
                return START_NOT_STICKY
            }
            if (previousState == RuntimeState.RUNNING) {
                val name = intent.getStringExtra(EXTRA_PROFILE_NAME).orEmpty()
                val profileJson = intent.getStringExtra(EXTRA_PROFILE).orEmpty()
                val accountTokensJson = intent.getStringExtra(EXTRA_ACCOUNT_TOKENS).orEmpty()
                commandExecutor.execute { applyRuntimeProfile(name, profileJson, accountTokensJson, startId) }
            } else {
                appendLocalLog("[WARN] [ANDROID] Live apply skipped while runtime is starting or stopping.")
                showToast("Profile saved. Apply again after the runtime finishes starting or stopping.")
            }
            return START_STICKY
        }
        val isStop = intent?.action == ACTION_STOP
        // A null intent is Android's START_STICKY restart; ACTION_RESUME comes from
        // the watchdog, boot/update receivers or the "Tap to resume" notice.
        val isResume = !isStop && (intent == null || intent.action == ACTION_RESUME)
        val resumeReason = if (intent == null) KeepAlive.REASON_STICKY
            else intent.getStringExtra(EXTRA_RESUME_REASON).orEmpty().ifBlank { KeepAlive.REASON_WATCHDOG }
        val wasActive = runtimeState != RuntimeState.STOPPED
        if (isResume && wasActive) {
            // This process still owns a runtime (running, starting or stopping);
            // a watchdog/boot resume must not disturb it.
            enterForeground(if (runtimeState == RuntimeState.RUNNING) "Running" else "Working...")
            appendLocalLog("[INFO] [ANDROID] Resume request ($resumeReason) ignored; the runtime is already active.")
            return START_STICKY
        }
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
            KeepAlive.cancelWatchdog(this)
            KeepAlive.clearHeartbeat(this)
        } else if (!isResume && intent != null) {
            commandVault.put(DESIRED_RUNNING_KEY, "true")
            workerRestartAttempts = 0
            persistPendingSelection(
                commandVault,
                intent.getStringExtra(EXTRA_PROFILES).orEmpty(),
                intent.getStringExtra(EXTRA_TOKENS).orEmpty(),
                appendToSession = wasActive,
            )
        }
        val inForeground = enterForeground(
            if (isStop) "Stopping..." else if (wasActive) "Adding profile(s)..." else "Starting..."
        )
        if (!inForeground && !isStop && !wasActive) {
            // Android 12+ may refuse a foreground start from the background. Keep
            // the user's "should be running" choice and offer a one-tap resume.
            runtimeState = RuntimeState.STOPPED
            if (isResume) {
                KeepAlive.showTapToResume(this)
                KeepAlive.scheduleWatchdog(this)
            } else {
                showToast("Android blocked the start. Open MudaRemote and press Run again.")
            }
            stopSelfResult(startId)
            return START_NOT_STICKY
        }
        if (isResume) KeepAlive.clearTapToResume(this)

        if (isStop) {
            appendLocalLog("[INFO] [ANDROID] Stop-all requested.")
            commandExecutor.execute { stopRuntime(startId) }
        } else {
            val stickyRestart = isResume
            if (intent == null) {
                appendLocalLog("[WARN] [ANDROID] System restarted the service (START_STICKY). Restoring the active selection...")
            } else if (isResume) {
                appendLocalLog("[INFO] [ANDROID] Resume requested ($resumeReason). Restoring the active selection...")
            } else {
                appendLocalLog("[INFO] [ANDROID] Start/add requested.")
            }
            val profilesJson = if (isResume) "" else intent?.getStringExtra(EXTRA_PROFILES).orEmpty()
            val tokensJson = if (isResume) "" else intent?.getStringExtra(EXTRA_TOKENS).orEmpty()
            // A resume always starts a fresh runtime here (active ones return above).
            val reportReason = if (isResume) resumeReason else null
            commandExecutor.execute {
                startRuntime(profilesJson, tokensJson, stickyRestart, wasActive, startId, reportReason)
            }
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        destroyed = true
        appendLocalLog("[INFO] [ANDROID] Service destroyed.")
        if (runtimeState != RuntimeState.STOPPED && KeepAlive.shouldBeRunning(this)) {
            // Destroyed mid-run without a user stop (system or maker cleaner): ask for a restart soon.
            appendLocalLog("[WARN] [ANDROID] Service destroyed while it should be running; restart check scheduled.")
            KeepAlive.scheduleWatchdog(this, KeepAlive.RESTART_SOON_MS)
        }
        stopRuntimeWatch()
        heartbeatTask?.cancel(false)
        heartbeatTask = null
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
        resumeReason: String? = null,
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
                        if (resumeReason != null && status == "started") {
                            KeepAlive.reportResumed(this, resumeReason)
                        }
                        KeepAlive.writeHeartbeat(this)
                        KeepAlive.scheduleWatchdog(this)
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
                KeepAlive.cancelWatchdog(this)
                KeepAlive.clearHeartbeat(this)
            }
            val stopped = stopSelfResult(stopDeliveryId(startId))
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

    private fun applyRuntimeProfile(name: String, profileJson: String, accountTokensJson: String, startId: Int) {
        if (destroyed || startWasCancelled(startId)) return
        try {
            val vault = SecretVault(this)
            val profiles = JSONObject(vault.get(ACTIVE_PROFILES_KEY).ifBlank { "{}" })
            if (!profiles.has(name)) {
                appendLocalLog("[WARN] [ANDROID] Live apply skipped: '$name' is no longer active.")
                showToast("Profile saved. '$name' is not active in the runtime.")
                return
            }
            val currentTokens = JSONArray(activeTokens.optString(name, "[]"))
            val requestedTokens = JSONArray(accountTokensJson)
            val tokensChanged = currentTokens.toString() != requestedTokens.toString()
            val responseText = Python.getInstance().getModule("android_bridge")
                .callAttr("apply_profile", name, profileJson).toString()
            val response = JSONObject(responseText)
            if (startWasCancelled(startId)) return
            when (response.optString("status")) {
                "queued" -> {
                    val cleanProfile = JSONObject(profileJson).apply {
                        remove("token")
                        remove("tokens")
                        remove("additional_tokens")
                    }
                    profiles.put(name, cleanProfile)
                    activeProfiles.put(name, cleanProfile)
                    vault.put(ACTIVE_PROFILES_KEY, profiles.toString())
                    val restartRequired = response.optJSONArray("restart_required")
                    val restartKeys = (0 until (restartRequired?.length() ?: 0)).mapNotNull { index ->
                        restartRequired?.optString(index)?.takeIf { it.isNotBlank() }
                    }.toMutableList()
                    if (tokensChanged) restartKeys.add("account tokens")
                    val restartMessage = if (restartKeys.isEmpty()) "" else
                        " Restart required for: ${restartKeys.distinct().joinToString(", ")}."
                    val count = response.optInt("account_count", 0)
                    appendLocalLog("[INFO] [ANDROID] Live settings QUEUED for '$name' ($count account(s)).$restartMessage")
                    showToast("'$name' settings QUEUED for $count account(s).$restartMessage")
                }
                "inactive" -> {
                    appendLocalLog("[WARN] [ANDROID] Live apply skipped: '$name' is inactive.")
                    showToast("Profile saved. '$name' is no longer active.")
                }
                "invalid" -> {
                    val errors = response.optJSONArray("errors")
                    val reason = (0 until (errors?.length() ?: 0))
                        .mapNotNull { index -> errors?.optString(index)?.takeIf { it.isNotBlank() } }
                        .joinToString("; ").ifBlank { "The active Python runtime rejected the profile." }
                    appendLocalLog("[ERROR] [ANDROID] Live apply failed for '$name': $reason")
                    showToast("Profile saved, but live apply failed: $reason")
                }
                else -> throw IllegalStateException("Unexpected live apply response.")
            }
        } catch (error: Exception) {
            if (destroyed || startWasCancelled(startId)) return
            appendLocalLog("[ERROR] [ANDROID] Live apply failed for '$name': ${error.message}")
            showToast("Profile saved, but live apply failed: ${error.message}")
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
                if (watchedState == RuntimeState.RUNNING && !latestCommandIsStop && KeepAlive.shouldBeRunning(this)) {
                    scheduleWorkerRestart(watchedStartId)
                } else {
                    finishStoppedRuntime(watchedStartId, stoppedByUser = watchedState == RuntimeState.STOPPING)
                }
            }
        }, 1, 1, TimeUnit.SECONDS)
    }

    /**
     * All account workers ended although the user did not stop them: restart
     * with back-off (5 s, 30 s, 2 min, 10 min), then give up honestly.
     */
    private fun scheduleWorkerRestart(startId: Int) {
        val attempt = workerRestartAttempts
        if (attempt >= WORKER_RESTART_BACKOFF_MS.size) {
            appendLocalLog(
                "[ERROR] [ANDROID] Account workers stopped again after $attempt restart attempts; giving up. Press Run to start again."
            )
            workerRestartAttempts = 0
            finishStoppedRuntime(startId, stoppedByUser = false)
            return
        }
        val delayMs = WORKER_RESTART_BACKOFF_MS[attempt]
        workerRestartAttempts = attempt + 1
        runtimeState = RuntimeState.STARTING  // keeps the 1 s watch from firing again meanwhile
        val wait = if (delayMs < 60_000L) "${delayMs / 1000L} s" else "${delayMs / 60_000L} min"
        appendLocalLog(
            "[WARN] [ANDROID] All account workers stopped while the runtime should run. " +
                "Restart ${attempt + 1}/${WORKER_RESTART_BACKOFF_MS.size} in $wait."
        )
        updateNotification("Workers stopped; restarting in $wait...")
        commandExecutor.schedule(Runnable {
            if (destroyed || startWasCancelled(startId) || latestCommandStartId != startId ||
                runtimeState != RuntimeState.STARTING
            ) return@Runnable
            if (!KeepAlive.shouldBeRunning(this)) {
                finishStoppedRuntime(startId, stoppedByUser = true)
                return@Runnable
            }
            lastWorkerRestartAt = System.currentTimeMillis()
            appendLocalLog("[INFO] [ANDROID] Restarting account workers (attempt ${attempt + 1}).")
            startRuntime("", "", stickyRestart = true, appendToSession = false, startId = startId)
        }, delayMs, TimeUnit.MILLISECONDS)
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
            KeepAlive.cancelWatchdog(this)
            KeepAlive.clearHeartbeat(this)
        }
        releaseLocks()
        val stopped = stopSelfResult(stopDeliveryId(startId))
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

    // Apply deliveries do not supersede start/stop ownership, but Android's
    // stopSelfResult must account for those newer deliveries when stopping.
    private fun stopDeliveryId(startId: Int): Int =
        if (latestCommandStartId == startId) latestServiceStartId else startId

    private fun startWasCancelled(startId: Int): Boolean =
        destroyed || lastStopStartId > startId || (latestCommandStartId > startId && latestCommandIsStop)

    // Called on start and by the minute heartbeat, so a lock that timed out
    // (the wake lock has a 24 h safety timeout) is taken again within a minute.
    private fun ensureLocks() {
        if (wakeLock?.isHeld != true) {
            runCatching {
                val powerManager = getSystemService(PowerManager::class.java)
                wakeLock = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "MudaRemote:runtime").also {
                    it.setReferenceCounted(false)
                    it.acquire(WAKE_LOCK_TIMEOUT_MS)
                }
            }.onFailure { error -> appendLocalLog("[WARN] [ANDROID] Wake lock unavailable: ${error.message}") }
        }
        val wifiManager = runCatching {
            applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        }.getOrNull() ?: return
        // High-perf keeps Wi-Fi awake with the screen off (deprecated but still
        // honoured on many builds); low-latency (API 29+) covers newer builds.
        if (wifiLock?.isHeld != true) {
            runCatching {
                @Suppress("DEPRECATION")
                val highPerfMode = WifiManager.WIFI_MODE_FULL_HIGH_PERF
                wifiLock = wifiManager.createWifiLock(highPerfMode, "MudaRemote:wifi").also {
                    it.setReferenceCounted(false)
                    it.acquire()
                }
            }.onFailure { error -> appendLocalLog("[WARN] [ANDROID] Wi-Fi lock unavailable: ${error.message}") }
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && lowLatencyWifiLock?.isHeld != true) {
            runCatching {
                lowLatencyWifiLock = wifiManager.createWifiLock(
                    WifiManager.WIFI_MODE_FULL_LOW_LATENCY, "MudaRemote:wifi-low-latency"
                ).also {
                    it.setReferenceCounted(false)
                    it.acquire()
                }
            }
        }
    }

    private fun releaseLocks() {
        runCatching { wakeLock?.let { if (it.isHeld) it.release() } }
        wakeLock = null
        runCatching { wifiLock?.let { if (it.isHeld) it.release() } }
        wifiLock = null
        runCatching { lowLatencyWifiLock?.let { if (it.isHeld) it.release() } }
        lowLatencyWifiLock = null
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
        private const val ACTION_APPLY = "com.mudaremote.android.APPLY"
        private const val ACTION_RESUME = "com.mudaremote.android.RESUME"
        private const val EXTRA_RESUME_REASON = "com.mudaremote.android.RESUME_REASON"
        private const val EXTRA_PROFILES = "com.mudaremote.android.PROFILES"
        private const val EXTRA_TOKENS = "com.mudaremote.android.TOKENS"
        private const val EXTRA_PROFILE_NAME = "com.mudaremote.android.PROFILE_NAME"
        private const val EXTRA_PROFILE = "com.mudaremote.android.PROFILE"
        private const val EXTRA_ACCOUNT_TOKENS = "com.mudaremote.android.ACCOUNT_TOKENS"
        private const val CHANNEL_ID = "mudaremote_runtime"
        private const val NOTIFICATION_ID = 41
        internal const val LOG_FILE = "mudaremote_android.log"
        private const val WAKE_LOCK_TIMEOUT_MS = 24L * 60L * 60L * 1000L
        private const val ACTIVE_PROFILES_KEY = "active_runtime_profiles"
        private const val ACTIVE_TOKENS_KEY = "active_runtime_tokens"
        internal const val DESIRED_RUNNING_KEY = "active_runtime_desired"
        private const val STOP_POLL_INTERVAL_MS = 200L
        private val WORKER_RESTART_BACKOFF_MS = longArrayOf(5_000L, 30_000L, 120_000L, 600_000L)
        private const val WORKER_BACKOFF_RESET_MS = 15L * 60L * 1000L

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

        /** Restores the last selection; the service ignores it unless the user left it running. */
        fun resume(context: Context, reason: String) {
            context.startForegroundService(
                Intent(context, MudaRemoteService::class.java)
                    .setAction(ACTION_RESUME)
                    .putExtra(EXTRA_RESUME_REASON, reason)
            )
        }

        fun stop(context: Context) {
            // startForegroundService keeps the stop path legal even if the app is backgrounded;
            // onStartCommand always calls startForeground() before handling ACTION_STOP.
            context.startForegroundService(
                Intent(context, MudaRemoteService::class.java).setAction(ACTION_STOP)
            )
        }

        fun applySavedProfile(context: Context, name: String, profile: JSONObject, accountTokens: List<String>): Boolean {
            if (runtimeState != RuntimeState.RUNNING) return false
            val vault = SecretVault(context)
            val profiles = JSONObject(vault.get(ACTIVE_PROFILES_KEY).ifBlank { "{}" })
            if (!profiles.has(name)) return false
            val cleanProfile = JSONObject(profile.toString()).apply {
                remove("token")
                remove("tokens")
                remove("additional_tokens")
            }
            context.startForegroundService(
                Intent(context, MudaRemoteService::class.java).setAction(ACTION_APPLY)
                    .putExtra(EXTRA_PROFILE_NAME, name)
                    .putExtra(EXTRA_PROFILE, cleanProfile.toString())
                    .putExtra(EXTRA_ACCOUNT_TOKENS, JSONArray(accountTokens).toString())
            )
            return true
        }
    }
}
