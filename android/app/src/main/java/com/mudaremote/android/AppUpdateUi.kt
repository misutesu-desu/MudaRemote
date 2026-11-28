package com.mudaremote.android

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.content.res.ColorStateList
import android.graphics.Typeface
import android.net.Uri
import android.provider.Settings
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.View
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * The screen side of the app updater: the «App updates» block of the Releases card and the
 * update dialog. It draws whatever [AppUpdater.snapshot] says, so a rotated or re-opened
 * screen shows the same dialog again.
 */
class AppUpdateUi(private val activity: Activity) {
    private var dialog: AlertDialog? = null
    private var titleView: TextView? = null
    private var metaView: TextView? = null
    private var botView: TextView? = null
    private var notesView: TextView? = null
    private var notesScroll: ScrollView? = null
    private var bar: ProgressBar? = null
    private var statusView: TextView? = null
    private var shownVersion = ""
    private var statusLine: TextView? = null

    private fun dp(v: Int): Int = UiTheme.dp(activity, v)

    private fun toast(msg: String) {
        activity.runOnUiThread { Toast.makeText(activity, msg, Toast.LENGTH_SHORT).show() }
    }

    // ---------------------------------------------------------------- lifecycle

    fun onResume() {
        AppUpdater.listener = { snap -> render(snap) }
        val snap = AppUpdater.snapshot
        if (snap.phase == AppUpdater.Phase.NEEDS_PERMISSION && AppUpdater.canInstall(activity)) {
            // Back from the «allow installs» page: carry on with the install.
            AppUpdater.launchInstall(activity)
            return
        }
        render(snap)
        refreshStatusLine()
    }

    fun onPause() {
        AppUpdater.listener = null
        closeDialog()
    }

    /** At app start: one automatic check, at most every 12 hours, when the setting is on. */
    fun autoCheck() {
        if (!AppUpdater.autoCheckEnabled(activity)) return
        if (!AppUpdateCore.isCheckDue(AppUpdater.lastCheckMs(activity), System.currentTimeMillis())) return
        AppUpdater.check(activity, false) { result ->
            // An offer shows itself through the dialog; every failure stays in the log only.
            if (result is AppUpdater.CheckResult.Available || result is AppUpdater.CheckResult.UpToDate) refreshStatusLine()
        }
    }

    /** «Check now»: always asks, ignores a skipped version, and says what happened. */
    fun checkNow() {
        statusLine?.text = "Checking for an app update..."
        AppUpdater.check(activity, true) { result ->
            when (result) {
                is AppUpdater.CheckResult.UpToDate ->
                    toast("MudaFork is up to date (v${AppUpdater.installedVersion(activity)}).")
                is AppUpdater.CheckResult.Failed -> toast(
                    when (result.kind) {
                        AppUpdater.FailKind.OFFLINE -> "No connection. Could not check for updates."
                        AppUpdater.FailKind.RATE_LIMITED -> "GitHub is limiting requests right now. Try again later."
                        AppUpdater.FailKind.ERROR -> "Could not check for updates."
                    }
                )
                is AppUpdater.CheckResult.Busy -> toast("An update is already in progress.")
                else -> Unit
            }
            refreshStatusLine()
        }
    }

    // ---------------------------------------------------------------- the card block

    private fun refreshStatusLine() {
        val v = statusLine ?: return
        val last = AppUpdater.lastCheckMs(activity)
        val whenText = if (last > 0L) SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.US).format(Date(last)) else "never"
        v.text = "Installed v${AppUpdater.installedVersion(activity)} · last checked: $whenText"
    }

    private fun switchRow(title: String, hint: String, initial: Boolean, onChange: (Boolean) -> Unit): View {
        val row = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            minimumHeight = dp(48)
            background = UiTheme.cardDrawable(activity, UiTheme.BG_SURFACE, UiTheme.BORDER_SUBTLE, 6f, 1f)
            setPadding(dp(10), dp(6), dp(10), dp(6))
        }
        val text = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
        text.addView(TextView(activity).apply {
            this.text = title
            textSize = 13f
            setTypeface(null, Typeface.BOLD)
            setTextColor(UiTheme.TEXT_PRIMARY)
        })
        text.addView(TextView(activity).apply {
            this.text = hint
            textSize = 11f
            setTextColor(UiTheme.TEXT_SECONDARY)
        })
        row.addView(text, LinearLayout.LayoutParams(0, -2, 1f))
        val sw = Switch(activity).apply {
            isChecked = initial
            minimumHeight = dp(40)
            thumbTintList = ColorStateList.valueOf(if (initial) UiTheme.ACCENT_GREEN_BRIGHT else UiTheme.TEXT_MUTED)
            trackTintList = ColorStateList.valueOf(if (initial) UiTheme.ACCENT_GREEN else UiTheme.BORDER_DEFAULT)
            setOnCheckedChangeListener { _, checked ->
                thumbTintList = ColorStateList.valueOf(if (checked) UiTheme.ACCENT_GREEN_BRIGHT else UiTheme.TEXT_MUTED)
                trackTintList = ColorStateList.valueOf(if (checked) UiTheme.ACCENT_GREEN else UiTheme.BORDER_DEFAULT)
                onChange(checked)
            }
        }
        row.addView(sw)
        row.setOnClickListener { sw.isChecked = !sw.isChecked }
        row.layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6) }
        return row
    }

    /** The «App updates» block that goes at the end of the Releases card. */
    fun buildSection(): View {
        val box = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(12), 0, 0)
        }
        box.addView(View(activity).apply { setBackgroundColor(UiTheme.BORDER_SUBTLE) }, LinearLayout.LayoutParams(-1, dp(1)))
        box.addView(TextView(activity).apply {
            text = "📲 App updates"
            textSize = 14f
            setTypeface(null, Typeface.BOLD)
            setTextColor(UiTheme.TEXT_PRIMARY)
            setPadding(0, dp(10), 0, 0)
        })
        box.addView(TextView(activity).apply {
            text = "Updates the app itself, only from the MudaFork releases on GitHub. " +
                "The file is checked (size, checksum, app name and signature) before Android installs it."
            textSize = 11.5f
            setTextColor(UiTheme.TEXT_SECONDARY)
            setPadding(0, dp(3), 0, dp(4))
        })
        statusLine = TextView(activity).apply {
            textSize = 11.5f
            setTextColor(UiTheme.TEXT_MUTED)
            setPadding(0, 0, 0, dp(2))
        }
        box.addView(statusLine)
        refreshStatusLine()
        box.addView(
            switchRow(
                "Check for updates automatically",
                "When the app starts, at most once every 12 hours.",
                AppUpdater.autoCheckEnabled(activity)
            ) { checked -> AppUpdater.prefs(activity).edit().putBoolean(AppUpdater.PREF_AUTO, checked).apply() }
        )
        box.addView(
            switchRow(
                "🧪 Beta app updates",
                "Also offer pre-releases of the app itself (not the Python runtime channel above). Off by default.",
                AppUpdater.betaEnabled(activity)
            ) { checked -> AppUpdater.prefs(activity).edit().putBoolean(AppUpdater.PREF_BETA, checked).apply() }
        )
        val btn = TextView(activity).apply {
            text = "🔄 Check now"
            textSize = 12f
            setTypeface(null, Typeface.BOLD)
            setTextColor(UiTheme.TEXT_PRIMARY)
            gravity = Gravity.CENTER
            background = UiTheme.buttonDrawable(activity, UiTheme.BG_CARD_LIGHT, radiusDp = 6f, borderColor = UiTheme.BORDER_DEFAULT, strokeWidthDp = 1f)
            minHeight = dp(44)
            setPadding(dp(12), dp(10), dp(12), dp(10))
            setOnClickListener { view ->
                view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                checkNow()
            }
        }
        box.addView(btn, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })
        return box
    }

    // ---------------------------------------------------------------- the dialog

    private fun closeDialog() {
        dialog?.dismiss()
        dialog = null
        titleView = null
        metaView = null
        botView = null
        notesView = null
        notesScroll = null
        bar = null
        statusView = null
        shownVersion = ""
    }

    private fun buildDialog(release: AppUpdateCore.ReleaseInfo) {
        val body = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(8), dp(20), dp(4))
        }
        val title = TextView(activity).apply {
            textSize = 15f
            setTypeface(null, Typeface.BOLD)
            setTextColor(UiTheme.TEXT_PRIMARY)
        }
        val meta = TextView(activity).apply {
            textSize = 12f
            setTextColor(UiTheme.TEXT_SECONDARY)
            setPadding(0, dp(2), 0, dp(8))
        }
        val bot = TextView(activity).apply {
            text = "The bot will stop during the update and resume after it."
            textSize = 12f
            setTextColor(UiTheme.ACCENT_YELLOW)
            setPadding(0, 0, 0, dp(8))
            visibility = View.GONE
        }
        val notes = TextView(activity).apply {
            textSize = 12f
            setTextColor(UiTheme.TEXT_PRIMARY)
            setTextIsSelectable(true)
            setPadding(dp(10), dp(8), dp(10), dp(8))
            background = UiTheme.cardDrawable(activity, UiTheme.BG_INPUT, UiTheme.BORDER_DEFAULT, 6f, 1f)
        }
        val scroll = ScrollView(activity).apply { addView(notes) }
        val progress = ProgressBar(activity, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 1000
            visibility = View.GONE
        }
        val status = TextView(activity).apply {
            textSize = 12f
            setTextColor(UiTheme.TEXT_SECONDARY)
            setPadding(0, dp(6), 0, 0)
            visibility = View.GONE
        }
        body.addView(title)
        body.addView(meta)
        body.addView(bot)
        body.addView(scroll, LinearLayout.LayoutParams(-1, -2))
        body.addView(progress, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })
        body.addView(status)

        val d = AlertDialog.Builder(activity)
            .setTitle("MudaFork update")
            .setView(body)
            .setPositiveButton("Update", null)
            .setNegativeButton("Later", null)
            .setNeutralButton("Skip this version", null)
            .create()
        d.setOnCancelListener { AppUpdater.dismiss() }
        d.show()
        d.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener { onPositive() }
        d.getButton(AlertDialog.BUTTON_NEGATIVE).setOnClickListener { onNegative() }
        d.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener { onNeutral() }

        dialog = d
        titleView = title
        metaView = meta
        botView = bot
        notesView = notes
        notesScroll = scroll
        bar = progress
        statusView = status
        shownVersion = release.version

        title.text = "MudaFork v${release.version} is available"
        val date = AppUpdateCore.publishedDate(release.publishedAt)
        val sizePart = if (release.apk.size > 0L) AppUpdateCore.formatMb(release.apk.size) else "size unknown"
        meta.text = "Installed v${AppUpdater.installedVersion(activity)} · $sizePart" +
            (if (date.isNotEmpty()) " · published $date" else "") +
            (if (release.prerelease) " · pre-release" else "")
        val text = AppUpdateCore.notesToText(release.notes)
        notes.text = if (text.isEmpty()) "No release notes." else text
        val tall = text.length > 400 || text.count { it == '\n' } > 8
        scroll.layoutParams = LinearLayout.LayoutParams(-1, if (tall) dp(220) else -2)
    }

    private fun onPositive() {
        val snap = AppUpdater.snapshot
        val release = snap.release ?: return
        when (snap.phase) {
            AppUpdater.Phase.OFFER, AppUpdater.Phase.FAILED -> AppUpdater.startDownload(activity, release)
            AppUpdater.Phase.DOWNLOADING -> AppUpdater.cancel()
            AppUpdater.Phase.NEEDS_PERMISSION -> openInstallSettings()
            AppUpdater.Phase.INSTALLER_OPENED, AppUpdater.Phase.READY -> AppUpdater.launchInstall(activity)
            else -> Unit
        }
    }

    private fun onNegative() {
        if (AppUpdater.isBusy()) return
        AppUpdater.dismiss()
        closeDialog()
    }

    private fun onNeutral() {
        val snap = AppUpdater.snapshot
        val release = snap.release ?: return
        if (snap.phase != AppUpdater.Phase.OFFER) return
        AppUpdater.skipVersion(activity, release.version)
        AppUpdater.dismiss()
        closeDialog()
        toast("v${release.version} skipped. «Check now» still offers it.")
    }

    private fun openInstallSettings() {
        try {
            activity.startActivity(
                Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + activity.packageName))
            )
        } catch (e: Exception) {
            toast("Open Settings > Apps > MudaFork and allow installing apps.")
        }
    }

    private fun render(snap: AppUpdater.Snapshot) {
        if (activity.isFinishing || activity.isDestroyed) return
        val release = snap.release
        if (snap.phase == AppUpdater.Phase.IDLE || release == null) {
            closeDialog()
            return
        }
        if (snap.phase == AppUpdater.Phase.READY) {
            // Verified: straight on to Android's installer.
            AppUpdater.launchInstall(activity)
            return
        }
        if (dialog == null || shownVersion != release.version) {
            closeDialog()
            buildDialog(release)
        }
        val d = dialog ?: return
        val pos = d.getButton(AlertDialog.BUTTON_POSITIVE)
        val neg = d.getButton(AlertDialog.BUTTON_NEGATIVE)
        val neu = d.getButton(AlertDialog.BUTTON_NEUTRAL)
        val progress = bar
        val status = statusView
        botView?.visibility = if (MudaRemoteService.isRunning) View.VISIBLE else View.GONE
        d.setCancelable(!AppUpdater.isBusy())
        d.setCanceledOnTouchOutside(false)
        when (snap.phase) {
            AppUpdater.Phase.OFFER -> {
                pos.text = "Update"; pos.isEnabled = true
                neg.text = "Later"; neg.visibility = View.VISIBLE
                neu.visibility = View.VISIBLE
                progress?.visibility = View.GONE
                status?.visibility = View.GONE
            }
            AppUpdater.Phase.DOWNLOADING -> {
                pos.text = "Cancel"; pos.isEnabled = true
                neg.visibility = View.GONE
                neu.visibility = View.GONE
                progress?.visibility = View.VISIBLE
                status?.visibility = View.VISIBLE
                status?.setTextColor(UiTheme.TEXT_SECONDARY)
                if (snap.total > 0L) {
                    progress?.isIndeterminate = false
                    progress?.progress = ((snap.done * 1000L) / snap.total).toInt()
                    val pct = (snap.done * 100L) / snap.total
                    val base = "$pct%  ·  ${AppUpdateCore.formatMb(snap.done)} / ${AppUpdateCore.formatMb(snap.total)}"
                    status?.text = if (snap.message.isNotEmpty()) snap.message else base
                } else {
                    progress?.isIndeterminate = true
                    status?.text = if (snap.message.isNotEmpty()) snap.message else AppUpdateCore.formatMb(snap.done)
                }
            }
            AppUpdater.Phase.VERIFYING -> {
                pos.text = "Verifying..."; pos.isEnabled = false
                neg.visibility = View.GONE
                neu.visibility = View.GONE
                progress?.visibility = View.VISIBLE
                progress?.isIndeterminate = true
                status?.visibility = View.VISIBLE
                status?.setTextColor(UiTheme.TEXT_SECONDARY)
                status?.text = "Checking the file (size, checksum, app name, signature)..."
            }
            AppUpdater.Phase.NEEDS_PERMISSION -> {
                pos.text = "Open settings"; pos.isEnabled = true
                neg.text = "Later"; neg.visibility = View.VISIBLE
                neu.visibility = View.GONE
                progress?.visibility = View.GONE
                status?.visibility = View.VISIBLE
                status?.setTextColor(UiTheme.ACCENT_YELLOW)
                status?.text = "The file is ready. Allow installing apps from MudaFork on the settings page, then come back; the install continues by itself."
            }
            AppUpdater.Phase.INSTALLER_OPENED -> {
                pos.text = "Install again"; pos.isEnabled = true
                neg.text = "Close"; neg.visibility = View.VISIBLE
                neu.visibility = View.GONE
                progress?.visibility = View.GONE
                status?.visibility = View.VISIBLE
                status?.setTextColor(UiTheme.TEXT_SECONDARY)
                status?.text = "The installer was opened. If you cancelled it, tap Install again."
            }
            AppUpdater.Phase.FAILED -> {
                pos.text = "Try again"; pos.isEnabled = true
                neg.text = "Close"; neg.visibility = View.VISIBLE
                neu.visibility = View.GONE
                progress?.visibility = View.GONE
                status?.visibility = View.VISIBLE
                status?.setTextColor(UiTheme.ACCENT_RED_BRIGHT)
                status?.text = snap.message
            }
            else -> Unit
        }
    }
}
