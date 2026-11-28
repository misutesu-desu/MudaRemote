package com.mudaremote.android

import android.app.ActivityManager
import android.app.AlarmManager
import android.app.ApplicationExitInfo
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.SystemClock
import androidx.annotation.RequiresApi
import androidx.core.app.NotificationCompat
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Keep-running helpers shared by the service, the receivers and the settings card.
 *
 * "Should be running" is the encrypted DESIRED_RUNNING_KEY the service already
 * keeps; it is cleared only when the user stops the runtime (or when the
 * runtime gives up on its own). Everything else here is plain, non-secret
 * bookkeeping: a heartbeat timestamp, the last reported heartbeat and the
 * "start again after reboot" setting.
 */
object KeepAlive {
    private const val PREFS = "mudaremote_keepalive"
    private const val KEY_HEARTBEAT = "heartbeat_ms"
    private const val KEY_REPORTED_HEARTBEAT = "reported_heartbeat_ms"
    private const val KEY_RESUME_AFTER_BOOT = "resume_after_boot"

    const val HEARTBEAT_INTERVAL_SECONDS = 60L
    const val STALE_AFTER_MS = 3L * 60L * 1000L
    const val WATCHDOG_INTERVAL_MS = 15L * 60L * 1000L
    const val RESTART_SOON_MS = 5L * 1000L

    const val ACTION_WATCHDOG = "com.mudaremote.android.WATCHDOG"
    const val ACTION_RESUME_FROM_NOTICE = "com.mudaremote.android.RESUME_FROM_NOTICE"

    const val REASON_STICKY = "sticky"
    const val REASON_WATCHDOG = "watchdog"
    const val REASON_BOOT = "boot"
    const val REASON_UPDATE = "update"
    const val REASON_NOTICE = "notice"

    private const val NOTICE_CHANNEL_ID = "mudaremote_notices"
    private const val RESUME_NOTICE_ID = 42
    private const val REPORT_NOTICE_ID = 43
    private const val WATCHDOG_REQUEST_CODE = 7

    private fun prefs(context: Context) =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun shouldBeRunning(context: Context): Boolean = runCatching {
        SecretVault(context.applicationContext).get(MudaRemoteService.DESIRED_RUNNING_KEY) == "true"
    }.getOrDefault(false)

    fun writeHeartbeat(context: Context) {
        prefs(context).edit().putLong(KEY_HEARTBEAT, System.currentTimeMillis()).apply()
    }

    fun lastHeartbeat(context: Context): Long = prefs(context).getLong(KEY_HEARTBEAT, 0L)

    fun clearHeartbeat(context: Context) {
        prefs(context).edit().putLong(KEY_HEARTBEAT, 0L).apply()
    }

    fun heartbeatIsStale(context: Context): Boolean =
        System.currentTimeMillis() - lastHeartbeat(context) > STALE_AFTER_MS

    fun resumeAfterBoot(context: Context): Boolean = prefs(context).getBoolean(KEY_RESUME_AFTER_BOOT, true)

    fun setResumeAfterBoot(context: Context, enabled: Boolean) {
        prefs(context).edit().putBoolean(KEY_RESUME_AFTER_BOOT, enabled).apply()
    }

    fun log(context: Context, line: String) {
        runCatching { File(context.filesDir, MudaRemoteService.LOG_FILE).appendText(line + "\n") }
    }

    // --- Watchdog alarm (inexact; no exact-alarm permission) ---

    private fun watchdogPendingIntent(context: Context): PendingIntent = PendingIntent.getBroadcast(
        context,
        WATCHDOG_REQUEST_CODE,
        Intent(context, KeepAliveReceiver::class.java).setAction(ACTION_WATCHDOG),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
    )

    /**
     * One alarm, pushed back by every heartbeat while the service is alive.
     * If the service dies, it fires about [delayMs] later (Doze may delay it).
     */
    fun scheduleWatchdog(context: Context, delayMs: Long = WATCHDOG_INTERVAL_MS) {
        runCatching {
            val alarmManager = context.getSystemService(AlarmManager::class.java) ?: return
            alarmManager.setAndAllowWhileIdle(
                AlarmManager.ELAPSED_REALTIME_WAKEUP,
                SystemClock.elapsedRealtime() + delayMs,
                watchdogPendingIntent(context)
            )
        }
    }

    fun cancelWatchdog(context: Context) {
        runCatching {
            context.getSystemService(AlarmManager::class.java)?.cancel(watchdogPendingIntent(context))
        }
    }

    /** Starts the service again; on Android 12+ a background start may be refused. */
    fun tryResume(context: Context, reason: String): Boolean {
        return try {
            MudaRemoteService.resume(context, reason)
            true
        } catch (error: Exception) {
            log(context, "[WARN] [ANDROID] Android blocked a background restart ($reason): ${error.message}. Showing 'Tap to resume'.")
            showTapToResume(context)
            false
        }
    }

    // --- Notices ---

    private fun ensureNoticeChannel(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(NOTICE_CHANNEL_ID, "MudaFork notices", NotificationManager.IMPORTANCE_DEFAULT)
            context.getSystemService(NotificationManager::class.java)?.createNotificationChannel(channel)
        }
    }

    private fun showNotice(context: Context, id: Int, title: String, text: String, resumeOnTap: Boolean) {
        runCatching {
            ensureNoticeChannel(context)
            val open = Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            if (resumeOnTap) open.action = ACTION_RESUME_FROM_NOTICE
            val contentIntent = PendingIntent.getActivity(
                context, id, open,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            val notice = NotificationCompat.Builder(context, NOTICE_CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_stat_notify)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(NotificationCompat.BigTextStyle().bigText(text))
                .setContentIntent(contentIntent)
                .setAutoCancel(true)
                .build()
            context.getSystemService(NotificationManager::class.java)?.notify(id, notice)
        }
    }

    fun showTapToResume(context: Context) {
        showNotice(
            context, RESUME_NOTICE_ID,
            "MudaFork stopped",
            "Android stopped the bot and did not allow it to restart in the background. Tap to resume.",
            resumeOnTap = true
        )
    }

    fun clearTapToResume(context: Context) {
        runCatching { context.getSystemService(NotificationManager::class.java)?.cancel(RESUME_NOTICE_ID) }
    }

    // --- Honest reporting ---

    private fun clock(millis: Long): String = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date(millis))

    /** Last process exit recorded by Android (API 30+): time and a short reason. */
    private fun lastExit(context: Context): Pair<Long, String>? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return null
        return runCatching {
            val activityManager = context.getSystemService(ActivityManager::class.java) ?: return null
            val info = activityManager.getHistoricalProcessExitReasons(context.packageName, 0, 1).firstOrNull()
                ?: return null
            info.timestamp to exitReasonName(info.reason)
        }.getOrNull()
    }

    @RequiresApi(Build.VERSION_CODES.R)
    private fun exitReasonName(reason: Int): String = when (reason) {
        ApplicationExitInfo.REASON_LOW_MEMORY -> "low memory"
        ApplicationExitInfo.REASON_SIGNALED -> "killed by the system"
        ApplicationExitInfo.REASON_EXCESSIVE_RESOURCE_USAGE -> "too much battery/CPU use"
        ApplicationExitInfo.REASON_USER_REQUESTED -> "force-stopped or cleaned"
        ApplicationExitInfo.REASON_USER_STOPPED -> "stopped by the user"
        ApplicationExitInfo.REASON_CRASH -> "app crash"
        ApplicationExitInfo.REASON_CRASH_NATIVE -> "native crash"
        ApplicationExitInfo.REASON_ANR -> "app not responding"
        ApplicationExitInfo.REASON_PERMISSION_CHANGE -> "permission changed"
        ApplicationExitInfo.REASON_DEPENDENCY_DIED -> "dependency died"
        ApplicationExitInfo.REASON_EXIT_SELF -> "exited by itself"
        ApplicationExitInfo.REASON_OTHER -> "other system reason"
        else -> "unknown"
    }

    /** Exit reasons caused by a phone restriction, a cleaner or resource pressure: the "Keep running" card helps. */
    private val RESTRICTION_REASONS = setOf("low memory", "killed by the system", "too much battery/CPU use", "force-stopped or cleaned")

    /** «Android closed MudaFork at HH:MM. It started again at HH:MM.» plus the reason and, for restriction kinds, a hint. */
    internal fun restartedText(stoppedAt: String, resumedAt: String, reason: String?): String {
        val sb = StringBuilder("Android closed MudaFork at $stoppedAt. It started again at $resumedAt.")
        if (!reason.isNullOrBlank()) {
            sb.append(" Reason: ").append(reason).append('.')
            if (reason in RESTRICTION_REASONS) sb.append(" Open \"Keep running\" to stop this.")
        }
        return sb.toString()
    }

    /**
     * Called once the runtime is running again after a resume. Logs, and for
     * a system kill also shows one notice, at most once per lost heartbeat.
     */
    fun reportResumed(context: Context, reason: String) {
        val store = prefs(context)
        val beat = store.getLong(KEY_HEARTBEAT, 0L)
        if (beat <= 0L || store.getLong(KEY_REPORTED_HEARTBEAT, 0L) == beat) return
        store.edit().putLong(KEY_REPORTED_HEARTBEAT, beat).apply()
        val now = System.currentTimeMillis()
        when (reason) {
            REASON_BOOT -> log(context, "[INFO] [ANDROID] Phone restarted; runtime resumed at ${clock(now)}.")
            REASON_UPDATE -> log(context, "[INFO] [ANDROID] App updated; runtime resumed at ${clock(now)}.")
            else -> {
                val exit = lastExit(context)?.takeIf { it.first >= beat }
                val stoppedAt = exit?.first ?: beat
                val reasonText = exit?.second
                val text = restartedText(clock(stoppedAt), clock(now), reasonText)
                log(context, "[WARN] [ANDROID] $text")
                showNotice(context, REPORT_NOTICE_ID, "MudaFork was restarted", text, resumeOnTap = false)
            }
        }
    }

    // --- Phone maker guidance ---

    enum class Maker { TRANSSION, XIAOMI, OPPO, VIVO, HUAWEI, SAMSUNG, OTHER }

    fun maker(): Maker {
        val name = (Build.MANUFACTURER.orEmpty() + " " + Build.BRAND.orEmpty()).lowercase(Locale.ROOT)
        return when {
            listOf("tecno", "infinix", "itel", "transsion").any { name.contains(it) } -> Maker.TRANSSION
            listOf("xiaomi", "redmi", "poco").any { name.contains(it) } -> Maker.XIAOMI
            listOf("oppo", "realme", "oneplus").any { name.contains(it) } -> Maker.OPPO
            listOf("vivo", "iqoo").any { name.contains(it) } -> Maker.VIVO
            listOf("huawei", "honor").any { name.contains(it) } -> Maker.HUAWEI
            name.contains("samsung") -> Maker.SAMSUNG
            else -> Maker.OTHER
        }
    }

    fun makerTitle(maker: Maker): String = when (maker) {
        Maker.TRANSSION -> "Tecno / Infinix / itel"
        Maker.XIAOMI -> "Xiaomi / Redmi / Poco"
        Maker.OPPO -> "Oppo / Realme / OnePlus"
        Maker.VIVO -> "Vivo"
        Maker.HUAWEI -> "Huawei / Honor"
        Maker.SAMSUNG -> "Samsung"
        Maker.OTHER -> "Your phone"
    }

    fun makerSteps(maker: Maker): List<String> = when (maker) {
        Maker.TRANSSION -> listOf(
            "Phone Master (or Settings > Apps) > Auto-start: turn MudaFork on.",
            "Settings > Battery > App battery management (or Power saving): set MudaFork to Unrestricted / No restrictions.",
            "Open recents, pull down (or long-press) the MudaFork card and lock it.",
            "Phone Master > Accelerate / cleaner: add MudaFork to the whitelist so cleaning does not close it.",
        )
        Maker.XIAOMI -> listOf(
            "Settings > Apps > MudaFork > Autostart: on.",
            "Settings > Apps > MudaFork > Battery saver: No restrictions.",
            "Open recents, long-press the MudaFork card and tap the lock.",
            "Security app > Cleaner: do not let it clean MudaFork.",
        )
        Maker.OPPO -> listOf(
            "Settings > Apps > MudaFork: allow Auto launch / Auto-start.",
            "Settings > Apps > MudaFork > Battery: Allow background activity (Unrestricted).",
            "Open recents, tap the menu on the MudaFork card and choose Lock.",
            "Phone Manager / cleaner: exclude MudaFork.",
        )
        Maker.VIVO -> listOf(
            "i Manager > App manager > Autostart manager: turn MudaFork on.",
            "Settings > Battery > Background power consumption: allow MudaFork (High background power use).",
            "Open recents, pull the MudaFork card down to lock it.",
            "i Manager cleaner: exclude MudaFork.",
        )
        Maker.HUAWEI -> listOf(
            "Settings > Battery > App launch: turn off Manage automatically for MudaFork and allow all three options.",
            "Settings > Apps > MudaFork > Battery: no restrictions.",
            "Open recents, pull the MudaFork card down to lock it.",
            "Phone Manager cleaner: exclude MudaFork.",
        )
        Maker.SAMSUNG -> listOf(
            "Settings > Apps > MudaFork > Battery: Unrestricted.",
            "Settings > Battery > Background usage limits: make sure MudaFork is not in Sleeping or Deep sleeping apps; add it to Never sleeping apps.",
            "Open recents, tap the MudaFork icon and choose Keep open.",
            "Device care: do not let it optimise MudaFork.",
        )
        Maker.OTHER -> listOf(
            "Allow MudaFork to auto-start, if your phone has that option.",
            "Set MudaFork's battery use to Unrestricted.",
            "Lock MudaFork in the recent apps screen, if your phone allows it.",
            "Exclude MudaFork from any cleaner or booster app.",
        )
    }

    /** Known auto-start / background pages, tried in order; may not exist on every build. */
    fun autoStartComponents(maker: Maker): List<ComponentName> = when (maker) {
        Maker.TRANSSION -> listOf(
            ComponentName("com.transsion.phonemaster", "com.cyin.himgr.autostart.AutoStartActivity"),
            ComponentName("com.transsion.phonemaster", "com.cyin.himgr.widget.activity.MainSettingGpActivity"),
        )
        Maker.XIAOMI -> listOf(
            ComponentName("com.miui.securitycenter", "com.miui.permcenter.autostart.AutoStartManagementActivity"),
            ComponentName("com.miui.powerkeeper", "com.miui.powerkeeper.ui.HiddenAppsConfigActivity"),
        )
        Maker.OPPO -> listOf(
            ComponentName("com.coloros.safecenter", "com.coloros.safecenter.permission.startup.StartupAppListActivity"),
            ComponentName("com.coloros.safecenter", "com.coloros.safecenter.startupapp.StartupAppListActivity"),
            ComponentName("com.oppo.safe", "com.oppo.safe.permission.startup.StartupAppListActivity"),
            ComponentName("com.oneplus.security", "com.oneplus.security.chainlaunch.view.ChainLaunchAppListActivity"),
        )
        Maker.VIVO -> listOf(
            ComponentName("com.vivo.permissionmanager", "com.vivo.permissionmanager.activity.BgStartUpManagerActivity"),
            ComponentName("com.iqoo.secure", "com.iqoo.secure.ui.phoneoptimize.BgStartUpManager"),
            ComponentName("com.iqoo.secure", "com.iqoo.secure.ui.phoneoptimize.AddWhiteListActivity"),
        )
        Maker.HUAWEI -> listOf(
            ComponentName("com.huawei.systemmanager", "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity"),
            ComponentName("com.huawei.systemmanager", "com.huawei.systemmanager.optimize.process.ProtectActivity"),
            ComponentName("com.hihonor.systemmanager", "com.hihonor.systemmanager.startupmgr.ui.StartupNormalAppListActivity"),
        )
        Maker.SAMSUNG -> listOf(
            ComponentName("com.samsung.android.lool", "com.samsung.android.sm.battery.ui.BatteryActivity"),
            ComponentName("com.samsung.android.sm", "com.samsung.android.sm.battery.ui.BatteryActivity"),
        )
        Maker.OTHER -> emptyList()
    }
}

/** Watchdog alarm target (not exported): resumes the runtime when it should run but is gone. */
class KeepAliveReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != KeepAlive.ACTION_WATCHDOG) return
        if (!KeepAlive.shouldBeRunning(context)) return  // user stopped it: the alarm chain ends here
        KeepAlive.scheduleWatchdog(context)  // keep checking until the service takes over again
        val alive = MudaRemoteService.runtimeState != MudaRemoteService.RuntimeState.STOPPED
        if (alive && !KeepAlive.heartbeatIsStale(context)) return
        KeepAlive.log(context, "[WARN] [ANDROID] Watchdog: the runtime should be running but is not; restarting it.")
        KeepAlive.tryResume(context, KeepAlive.REASON_WATCHDOG)
    }
}

/** Boot and app-update receiver: resumes only when the user had it running. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return
        val isUpdate = action == Intent.ACTION_MY_PACKAGE_REPLACED
        val isBoot = action == Intent.ACTION_BOOT_COMPLETED ||
            action == "android.intent.action.QUICKBOOT_POWERON" ||
            action == "com.htc.intent.action.QUICKBOOT_POWERON"
        if (!isUpdate && !isBoot) return
        if (!KeepAlive.shouldBeRunning(context)) return
        if (isBoot && !KeepAlive.resumeAfterBoot(context)) {
            KeepAlive.log(context, "[INFO] [ANDROID] Phone restarted; not resuming because 'Start again after reboot' is off.")
            return
        }
        KeepAlive.scheduleWatchdog(context)
        KeepAlive.tryResume(context, if (isUpdate) KeepAlive.REASON_UPDATE else KeepAlive.REASON_BOOT)
    }
}
