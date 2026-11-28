package com.mudaremote.android

import android.Manifest
import android.app.ActivityManager
import android.app.AlertDialog
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.text.Editable
import android.text.InputType
import android.text.Layout
import android.text.TextWatcher
import android.transition.ChangeBounds
import android.transition.TransitionManager
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import com.chaquo.python.Python
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.RandomAccessFile

/**
 * MudaFork Android application in a dark Material 3 Expressive style (see UiTheme).
 */
class MainActivity : ComponentActivity() {

    private lateinit var tokenInput: EditText
    private lateinit var tokenShowHideBtn: TextView
    private lateinit var fieldsContainer: LinearLayout
    private lateinit var profileTabs: LinearLayout
    private lateinit var profileCountBadge: TextView
    private lateinit var statusBadge: TextView
    private lateinit var engineVersionText: TextView
    private lateinit var searchInput: EditText
    private lateinit var searchClearBtn: TextView
    private lateinit var searchResultCountText: TextView
    private lateinit var categoryTabs: LinearLayout
    private lateinit var logView: TextView
    private lateinit var logScroll: ScrollView
    private lateinit var logStatusDot: TextView
    private lateinit var vault: SecretVault
    private lateinit var rootScroll: ScrollView
    private lateinit var keepRunningCard: LinearLayout
    private lateinit var keepRunningStatus: LinearLayout
    private lateinit var profileSummaryTitle: TextView
    private lateinit var profileRoleChip: TextView
    private lateinit var profileRunChip: TextView
    private lateinit var giveKakeraQuickBtn: TextView
    private var pendingNoticeResume = false

    private var schemaFields = JSONObject()
    private val profiles = linkedMapOf<String, JSONObject>()
    private val tokens = linkedMapOf<String, String>()
    private val fieldViews = linkedMapOf<String, View>()
    private val inheritedKakeraFields = setOf("chaos_emojis", "sphere_perk_emojis", "mk_kakera_emojis", "op5_kakera_emojis")
    private var inheritedKakeraAtRender = "[]"
    private val sectionContainers = linkedMapOf<String, LinearLayout>()
    private val sectionHeaders = linkedMapOf<String, TextView>()
    private val sectionChevrons = linkedMapOf<String, TextView>()
    private val collapsedSections = mutableMapOf<String, Boolean>()

    private var currentProfile = ""
    private val profileIdPattern = Regex("^[A-Za-z0-9_-]{1,64}$")
    private var storageHealthy = true
    private var isTokenVisible = false
    private var activeCategoryFilter = "All"
    private var activeSearchQuery = ""
    private var logsVisibleForSession = false
    private var logSessionStartBytes = 0L
    private var displayedLogText = ""
    // Log filters (profile, kind, errors only, search text); empty = no filter.
    private var logFilterProfile = ""
    private var logFilterKind = ""
    private var logFilterErrorsOnly = false
    private var logFilterSearch = ""
    private var isAutoScrollEnabled = true
    private var isLogsExpanded = false
    private var isUpdateInFlight = false
    private lateinit var appUpdateUi: AppUpdateUi
    private var engineInfoInFlight = false
    private var lastEngineLabel = ""

    private val searchHandler = Handler(Looper.getMainLooper())
    private val searchDebounce = Runnable {
        activeSearchQuery = searchInput.text?.toString()?.trim().orEmpty()
        searchClearBtn.visibility = if (activeSearchQuery.isNotEmpty()) View.VISIBLE else View.GONE
        filterSettings()
    }

    private val logHandler = Handler(Looper.getMainLooper())
    private val logRefresh = object : Runnable {
        override fun run() {
            syncRuntimeStateIfChanged()
            refreshLogs()
            logHandler.postDelayed(this, 1000)
        }
    }

    // Log pipeline: the file read, parsing, filtering and highlighting run on this one background
    // thread; the main thread only checks the file's size/time and sets the finished text.
    private val logExecutor = java.util.concurrent.Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "mudafork-log").apply { isDaemon = true }
    }
    private var logJobInFlight = false
    private var logGeneration = 0
    private var lastLogSignature = ""
    private var lastSeenRuntimeState: MudaRemoteService.RuntimeState? = null

    /** The log filters as one immutable value, so the background thread never reads Activity fields. */
    private data class LogFilters(val profile: String, val kind: String, val errorsOnly: Boolean, val search: String)

    private val presetsPicker = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri?.let { importPresets(it) }
    }
    private val secretsPicker = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri?.let { importSecrets(it) }
    }
    // "Save as TXT": the system "create document" picker; the filtered lines are written to the chosen file.
    private val logExportPicker = registerForActivityResult(ActivityResultContracts.CreateDocument("text/plain")) { uri ->
        uri?.let { writeLogExport(it) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        vault = SecretVault(this)
        appUpdateUi = AppUpdateUi(this)
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 100)
        }
        setContentView(buildRootUi())
        loadSchema()
        restore()
        loadEngineVersion()
        AppUpdater.cleanup(applicationContext)
        appUpdateUi.autoCheck()
        if (savedInstanceState == null && intent?.action == KeepAlive.ACTION_RESUME_FROM_NOTICE) {
            intent?.action = null
            pendingNoticeResume = true  // started from onResume, when the app is in the foreground
        }
    }

    override fun onResume() {
        super.onResume()
        appUpdateUi.onResume()
        logHandler.post(logRefresh)
        if (lastEngineLabel.isNotEmpty()) {
            // Instant paint from cache; refresh in background afterwards.
            engineVersionText.text = lastEngineLabel
        }
        loadEngineVersion()
        syncRuntimeStatusBadge()
        adoptLiveLogsIfRunning()
        if (::keepRunningStatus.isInitialized) refreshKeepRunningStatus()
        if (pendingNoticeResume) {
            pendingNoticeResume = false
            resumeFromNotice()
        }
    }

    /** "Tap to resume": the app is in the foreground now, so Android allows the start. */
    private fun resumeFromNotice() {
        KeepAlive.clearTapToResume(this)
        if (MudaRemoteService.runtimeState != MudaRemoteService.RuntimeState.STOPPED) return
        if (!KeepAlive.shouldBeRunning(this)) {
            toast("Nothing to resume: the bot was stopped.")
            return
        }
        runCatching { MudaRemoteService.resume(this, KeepAlive.REASON_NOTICE) }
            .onSuccess {
                beginLogSession()
                updateStatusBadge("● Resuming...", UiTheme.ACCENT_YELLOW)
                toast("Resuming the bot...")
            }
            .onFailure { error -> toast("Could not resume: ${error.message}") }
    }

    /**
     * The foreground service outlives Activity instances (reopen, process
     * restart). Without this the console stays on "No logs for this launch
     * yet." forever even though the runtime is streaming output — the session
     * flag is only set by pressing Run/Fetch inside this instance.
     */
    private fun adoptLiveLogsIfRunning() {
        if (!MudaRemoteService.isRunning || logsVisibleForSession) return
        logSessionStartBytes = 0L  // surface the existing tail of the live run
        logsVisibleForSession = true
        refreshLogs()
    }

    override fun onDestroy() {
        logExecutor.shutdownNow()
        super.onDestroy()
    }

    /** Runs on each tick but touches views only when the service's state really changed. */
    private fun syncRuntimeStateIfChanged() {
        val state = MudaRemoteService.runtimeState
        if (state == lastSeenRuntimeState) return
        lastSeenRuntimeState = state
        syncRuntimeStatusBadge()
        refreshProfileSummary()
    }

    override fun onPause() {
        appUpdateUi.onPause()
        logHandler.removeCallbacks(logRefresh)
        searchHandler.removeCallbacks(searchDebounce)
        if (storageHealthy) {
            saveCurrentProfile(showStatus = false)  // Persist drafts so rotation/process death never loses edits.
        }
        super.onPause()
    }

    private fun syncRuntimeStatusBadge() {
        when (MudaRemoteService.runtimeState) {
            MudaRemoteService.RuntimeState.STARTING -> {
                updateStatusBadge("● Starting...", UiTheme.ACCENT_YELLOW)
                setLogDot(UiTheme.TERTIARY)
            }
            MudaRemoteService.RuntimeState.RUNNING -> {
                updateStatusBadge("● Runtime active", UiTheme.ACCENT_GREEN_BRIGHT)
                setLogDot(UiTheme.PRIMARY)
            }
            MudaRemoteService.RuntimeState.STOPPING -> {
                updateStatusBadge("● Stopping all...", UiTheme.ACCENT_YELLOW)
                setLogDot(UiTheme.TERTIARY)
            }
            MudaRemoteService.RuntimeState.STOPPED -> {
                if (statusBadge.text?.startsWith("●") == true) {
                    updateStatusBadge("● Stopped", UiTheme.TEXT_MUTED)
                    setLogDot(UiTheme.TEXT_MUTED)
                }
            }
        }
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        // GitHub-style "/" shortcut jumps straight into settings search.
        if (keyCode == KeyEvent.KEYCODE_SLASH && currentFocus != searchInput) {
            searchInput.requestFocus()
            searchInput.setSelection(searchInput.text?.length ?: 0)
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    // =========================================================================
    // UI BUILDER (DARK MATERIAL 3 EXPRESSIVE, SEE UiTheme)
    // =========================================================================

    private fun buildRootUi(): View {
        val root = FrameLayout(this).apply {
            setBackgroundColor(UiTheme.BG_APP)
        }

        val scrollContent = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(
                UiTheme.dp(this@MainActivity, 16),
                UiTheme.dp(this@MainActivity, 28),
                UiTheme.dp(this@MainActivity, 16),
                UiTheme.dp(this@MainActivity, 120)
            )
        }

        // 1. GitHub Repository Header Card
        scrollContent.addView(buildHeaderCard())

        // 2. Profiles card
        scrollContent.addView(buildProfileHubCard())

        // 3. Secrets / Discord Token Card
        scrollContent.addView(buildTokenCard())

        // 4. Search & Category Subnav
        scrollContent.addView(buildSearchAndFilterBar())

        // 5. Dynamic Settings Fields Container (GitHub Boxes)
        fieldsContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        scrollContent.addView(fieldsContainer)

        // 6a. Keep running (phones that close background apps)
        keepRunningCard = buildKeepRunningCard()
        scrollContent.addView(keepRunningCard)

        // 6. Python Engine & Releases Card
        scrollContent.addView(buildEngineManagerCard())

        // 7. GitHub Actions Workflow Terminal / Logs
        scrollContent.addView(buildLogConsoleCard())

        val scrollView = ScrollView(this).apply {
            isFillViewport = true
            isVerticalScrollBarEnabled = false
            addView(scrollContent)
        }
        rootScroll = scrollView
        root.addView(scrollView, FrameLayout.LayoutParams(-1, -1))

        // 8. Sticky Bottom Action Bar (GitHub PR / Workflow Action Dock)
        val bottomBarView = buildStickyBottomBar()
        root.addView(bottomBarView, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM))

        // Window Insets listener to safely avoid status bar, notch, and navigation buttons
        ViewCompat.setOnApplyWindowInsetsListener(root) { _, insets ->
            val sysInsets = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()
            )

            // The keyboard (adjustResize) is in the ime inset; the dock stays above the system bars.
            val imeBottom = insets.getInsets(WindowInsetsCompat.Type.ime()).bottom
            scrollContent.setPadding(
                UiTheme.dp(this@MainActivity, 16) + sysInsets.left,
                sysInsets.top + UiTheme.dp(this@MainActivity, 12),
                UiTheme.dp(this@MainActivity, 16) + sysInsets.right,
                maxOf(sysInsets.bottom, imeBottom) + UiTheme.dp(this@MainActivity, 120)
            )

            bottomBarView.setPadding(
                UiTheme.dp(this@MainActivity, 12) + sysInsets.left,
                0,
                UiTheme.dp(this@MainActivity, 12) + sysInsets.right,
                sysInsets.bottom + UiTheme.dp(this@MainActivity, 10)
            )

            insets
        }

        return root
    }

    // --- 1. App header card ---
    private fun buildHeaderCard(): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = UiTheme.surfaceCard(this@MainActivity)
            setPaddingRelative(UiTheme.dp(this@MainActivity, 20), UiTheme.dp(this@MainActivity, 20), UiTheme.dp(this@MainActivity, 20), UiTheme.dp(this@MainActivity, 18))
        }

        val topRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        val titleCol = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }

        titleCol.addView(TextView(this).apply {
            text = "MudaFork"
            UiTheme.styleTitle(this, large = true)
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
        })

        engineVersionText = TextView(this).apply {
            text = "Python engine: loading..."
            textSize = UiTheme.TYPE_LABEL
            setTextColor(UiTheme.TEXT_MUTED)
            maxLines = 2
            ellipsize = android.text.TextUtils.TruncateAt.END
            setPaddingRelative(0, UiTheme.dp(this@MainActivity, 2), 0, 0)
        }
        titleCol.addView(engineVersionText)
        topRow.addView(titleCol, LinearLayout.LayoutParams(0, -2, 1f))

        statusBadge = TextView(this).apply {
            text = "● Idle"
            UiTheme.styleStatusChip(this, UiTheme.TEXT_MUTED)
            maxWidth = UiTheme.dp(this@MainActivity, 180)
        }
        topRow.addView(statusBadge, LinearLayout.LayoutParams(-2, -2).apply { marginStart = UiTheme.dp(this@MainActivity, 8) })
        card.addView(topRow)

        val desc = TextView(this).apply {
            text = "Mudae automation for your own Discord accounts. Tokens stay encrypted on this phone."
            UiTheme.styleSupporting(this)
            setPaddingRelative(0, UiTheme.dp(this@MainActivity, 8), 0, UiTheme.dp(this@MainActivity, 12))
        }
        card.addView(desc)

        // Three equal-width actions.
        val actionsRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }

        val btnBattery = createGitHubButton("Keep running") { scrollToKeepRunning() }
        val btnCheckUpdates = createGitHubButton("Fetch updates") { checkPythonUpdates(force = true) }
        val btnImportPresets = createGitHubButton("Import presets") { presetsPicker.launch(arrayOf("application/json", "text/plain")) }

        actionsRow.addView(btnBattery, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = UiTheme.dp(this@MainActivity, 8) })
        actionsRow.addView(btnCheckUpdates, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = UiTheme.dp(this@MainActivity, 8) })
        actionsRow.addView(btnImportPresets, LinearLayout.LayoutParams(0, -2, 1f))
        card.addView(actionsRow)

        return card.apply {
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply {
                bottomMargin = UiTheme.dp(this@MainActivity, 16)
            }
        }
    }

    // --- 2. Profiles card: tabs, the open profile's role and state, quick actions ---
    private fun buildProfileHubCard(): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = UiTheme.surfaceCard(this@MainActivity)
            setPaddingRelative(UiTheme.dp(this@MainActivity, 20), UiTheme.dp(this@MainActivity, 18), UiTheme.dp(this@MainActivity, 20), UiTheme.dp(this@MainActivity, 18))
        }

        val headerRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        val cardTitle = TextView(this).apply {
            text = "Profiles"
            UiTheme.styleTitle(this)
        }
        headerRow.addView(cardTitle, LinearLayout.LayoutParams(0, -2, 1f))

        val profileCountBadge = TextView(this).apply {
            text = "${profiles.size}"
            UiTheme.styleStatusChip(this, UiTheme.PRIMARY)
        }
        this.profileCountBadge = profileCountBadge
        headerRow.addView(profileCountBadge)
        card.addView(headerRow)

        card.addView(TextView(this).apply {
            text = "Pick a profile to edit it. Run starts the open profile; hold Run to pick several."
            UiTheme.styleSupporting(this)
            setPaddingRelative(0, UiTheme.dp(this@MainActivity, 4), 0, 0)
        })

        // Horizontal profile tabs
        profileTabs = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPaddingRelative(0, UiTheme.dp(this@MainActivity, 12), 0, UiTheme.dp(this@MainActivity, 4))
        }
        card.addView(HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            addView(profileTabs, FrameLayout.LayoutParams(-2, -2))
        })

        // The open profile: role (Main/Side) and the runtime state
        val summaryRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = UiTheme.rowSurface(this@MainActivity)
            minimumHeight = UiTheme.dp(this@MainActivity, 56)
            setPaddingRelative(UiTheme.dp(this@MainActivity, 16), UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 10))
        }
        profileSummaryTitle = TextView(this).apply {
            UiTheme.styleLabel(this)
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
        }
        profileRoleChip = TextView(this).apply { UiTheme.styleStatusChip(this, UiTheme.SECONDARY) }
        profileRunChip = TextView(this).apply { UiTheme.styleStatusChip(this, UiTheme.TEXT_MUTED) }
        summaryRow.addView(profileSummaryTitle, LinearLayout.LayoutParams(0, -2, 1f))
        summaryRow.addView(profileRoleChip, LinearLayout.LayoutParams(-2, -2).apply { marginStart = UiTheme.dp(this@MainActivity, 8) })
        summaryRow.addView(profileRunChip, LinearLayout.LayoutParams(-2, -2).apply { marginStart = UiTheme.dp(this@MainActivity, 8) })
        card.addView(summaryRow, LinearLayout.LayoutParams(-1, -2).apply { topMargin = UiTheme.dp(this@MainActivity, 8) })

        // Quick actions: equal widths, never touching
        val quickRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val runBtn = createGitHubButton("Run", UiTheme.ButtonStyle.FILLED, HapticFeedbackConstants.CONFIRM) { startRuntime(listOf(currentProfile)) }.apply {
            contentDescription = "Start the open profile. Hold to pick several profiles."
            setOnLongClickListener {
                performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                showStartOptionsDialog()
                true
            }
        }
        val stopBtn = createGitHubButton("Stop all", UiTheme.ButtonStyle.DANGER, HapticFeedbackConstants.REJECT) { doStopAll() }
        quickRow.addView(runBtn, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = UiTheme.dp(this@MainActivity, 8) })
        quickRow.addView(stopBtn, LinearLayout.LayoutParams(0, -2, 1f))
        card.addView(quickRow, LinearLayout.LayoutParams(-1, -2).apply { topMargin = UiTheme.dp(this@MainActivity, 12) })

        giveKakeraQuickBtn = createGitHubButton("Give all kakera", UiTheme.ButtonStyle.TONAL) { requestGiveAllKakera() }
        card.addView(giveKakeraQuickBtn, LinearLayout.LayoutParams(-1, -2).apply { topMargin = UiTheme.dp(this@MainActivity, 8) })

        // Profile management on its own wrapping row so nothing clips on narrow screens.
        val actionsRow = FlowLayout(this).apply {
            setPaddingRelative(0, UiTheme.dp(this@MainActivity, 12), 0, 0)
        }
        actionsRow.addView(createGitHubSmallBtn("New") { _ -> promptCreateProfile() })
        actionsRow.addView(createGitHubSmallBtn("Duplicate") { _ -> duplicateCurrentProfile() })
        actionsRow.addView(createGitHubSmallBtn("Rename") { _ -> promptRenameProfile() })
        actionsRow.addView(createGitHubSmallBtn("Export") { _ -> shareCurrentProfile() })
        actionsRow.addView(createGitHubSmallBtn("Delete", UiTheme.ButtonStyle.DANGER) { _ -> promptDeleteCurrentProfile() })
        card.addView(actionsRow)

        return card.apply {
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply {
                bottomMargin = UiTheme.dp(this@MainActivity, 16)
            }
        }
    }

    /** Role, runtime state and the side-only action of the open profile; changes only what differs. */
    private fun refreshProfileSummary() {
        if (!::profileSummaryTitle.isInitialized) return
        val data = profiles[currentProfile]
        val isSide = data?.optString("account_role", "main") == "side"
        val hasToken = currentProfile.isNotBlank() && allTokensForProfile(currentProfile).isNotEmpty()
        setTextIfChanged(profileSummaryTitle, if (hasToken) currentProfile else "$currentProfile · no token")
        setTextIfChanged(profileRoleChip, if (isSide) "Side" else "Main")
        val (runText, runColor) = when (MudaRemoteService.runtimeState) {
            MudaRemoteService.RuntimeState.RUNNING -> "Bot running" to UiTheme.PRIMARY
            MudaRemoteService.RuntimeState.STARTING -> "Starting" to UiTheme.TERTIARY
            MudaRemoteService.RuntimeState.STOPPING -> "Stopping" to UiTheme.TERTIARY
            MudaRemoteService.RuntimeState.STOPPED -> "Bot stopped" to UiTheme.TEXT_MUTED
        }
        if (profileRunChip.text?.toString() != runText) {
            profileRunChip.text = runText
            UiTheme.styleStatusChip(profileRunChip, runColor)
        }
        val kakeraVisibility = if (isSide) View.VISIBLE else View.GONE
        if (giveKakeraQuickBtn.visibility != kakeraVisibility) giveKakeraQuickBtn.visibility = kakeraVisibility
    }

    private fun setTextIfChanged(view: TextView, value: String) {
        if (view.text?.toString() != value) view.text = value
    }

    private fun doStopAll() {
        beginLogSession()
        MudaRemoteService.stop(this@MainActivity)
        updateStatusBadge("● Stopping all...", UiTheme.ACCENT_YELLOW)
        setLogDot(UiTheme.TERTIARY)
        toast("Stop requested for all running profiles.")
    }

    // --- 3. Repository Secrets / Token Card ---
    private fun buildTokenCard(): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = UiTheme.surfaceCard(this@MainActivity)
            setPaddingRelative(UiTheme.dp(this@MainActivity, 20), UiTheme.dp(this@MainActivity, 18), UiTheme.dp(this@MainActivity, 20), UiTheme.dp(this@MainActivity, 18))
        }

        val titleRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        val title = TextView(this).apply {
            text = "Account token"
            UiTheme.styleTitle(this)
        }
        titleRow.addView(title, LinearLayout.LayoutParams(0, -2, 1f))

        val securityBadge = TextView(this).apply {
            text = "AES-256-GCM"
            UiTheme.styleStatusChip(this, UiTheme.TERTIARY)
        }
        titleRow.addView(securityBadge)
        card.addView(titleRow)

        val desc = TextView(this).apply {
            text = "Encrypted with the Android Keystore. Tokens are never written into exported presets."
            UiTheme.styleSupporting(this)
            setPaddingRelative(0, UiTheme.dp(this@MainActivity, 4), 0, UiTheme.dp(this@MainActivity, 12))
        }
        card.addView(desc)

        // Token Input with Action Buttons (Eye, Paste, Clear)
        val inputContainer = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = UiTheme.inputDrawable(this@MainActivity, radiusDp = UiTheme.SHAPE_FULL)
            setAddStatesFromChildren(true)  // the focus ring follows the field inside
            minimumHeight = UiTheme.dp(this@MainActivity, 56)
            setPaddingRelative(UiTheme.dp(this@MainActivity, 20), 0, UiTheme.dp(this@MainActivity, 4), 0)
        }

        tokenInput = EditText(this).apply {
            hint = "Paste your Discord token here"
            textSize = UiTheme.TYPE_BODY
            typeface = Typeface.MONOSPACE
            setTextColor(UiTheme.TEXT_PRIMARY)
            setHintTextColor(UiTheme.TEXT_MUTED)
            background = null
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            imeOptions = EditorInfo.IME_ACTION_DONE
            importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
        }
        inputContainer.addView(tokenInput, LinearLayout.LayoutParams(0, -2, 1f))

        tokenShowHideBtn = TextView(this).apply {
            text = "Show"
            UiTheme.styleButton(this, UiTheme.ButtonStyle.TEXT, compact = true)
            setPaddingRelative(UiTheme.dp(this@MainActivity, 8), 0, UiTheme.dp(this@MainActivity, 8), 0)
            contentDescription = "Toggle token visibility"
            gravity = Gravity.CENTER
            minHeight = UiTheme.dp(this@MainActivity, 48)
            minWidth = UiTheme.dp(this@MainActivity, 48)
            setOnClickListener { toggleTokenVisibility() }
        }
        inputContainer.addView(tokenShowHideBtn)

        val pasteBtn = TextView(this).apply {
            text = "Paste"
            UiTheme.styleButton(this, UiTheme.ButtonStyle.TEXT, compact = true)
            setPaddingRelative(UiTheme.dp(this@MainActivity, 8), 0, UiTheme.dp(this@MainActivity, 8), 0)
            contentDescription = "Paste token from clipboard"
            gravity = Gravity.CENTER
            minHeight = UiTheme.dp(this@MainActivity, 48)
            minWidth = UiTheme.dp(this@MainActivity, 48)
            setOnClickListener { pasteTokenFromClipboard() }
        }
        inputContainer.addView(pasteBtn)

        val clearBtn = TextView(this).apply {
            text = "✕"
            textSize = 16f
            setTextColor(UiTheme.ERROR)
            background = UiTheme.listItemDrawable(this@MainActivity, radiusDp = UiTheme.SHAPE_FULL)
            contentDescription = "Clear token"
            gravity = Gravity.CENTER
            minHeight = UiTheme.dp(this@MainActivity, 48)
            minWidth = UiTheme.dp(this@MainActivity, 48)
            setOnClickListener {
                // Destructive (the next save drops the token), so it asks first.
                AlertDialog.Builder(this@MainActivity)
                    .setTitle("Clear the token?")
                    .setMessage("The token of '$currentProfile' is removed from this phone when the profile is saved.")
                    .setPositiveButton("Clear") { _, _ ->
                        tokenInput.setText("")
                        tokens.remove(currentProfile)
                        toast("Token cleared for $currentProfile")
                    }
                    .setNegativeButton("Cancel", null)
                    .show()
            }
        }
        inputContainer.addView(clearBtn)
        card.addView(inputContainer)

        val importSecretsBtn = createGitHubButton("Import secrets file (.mudae-secrets.json)", UiTheme.ButtonStyle.TEXT) {
            secretsPicker.launch(arrayOf("application/json", "text/plain"))
        }
        card.addView(importSecretsBtn, LinearLayout.LayoutParams(-2, -2).apply { topMargin = UiTheme.dp(this@MainActivity, 8) })

        return card.apply {
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply {
                bottomMargin = UiTheme.dp(this@MainActivity, 16)
            }
        }
    }

    // --- 4. Search & Category Subnav ---
    private fun buildSearchAndFilterBar(): View {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }

        // Search Input Box (GitHub command search style)
        val searchBox = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = UiTheme.inputDrawable(this@MainActivity, radiusDp = UiTheme.SHAPE_FULL)
            setAddStatesFromChildren(true)  // the focus ring follows the field inside
            minimumHeight = UiTheme.dp(this@MainActivity, 56)
            setPaddingRelative(UiTheme.dp(this@MainActivity, 20), 0, UiTheme.dp(this@MainActivity, 4), 0)
        }

        searchInput = EditText(this).apply {
            hint = "Search settings (snipe, kakera, speed...)"
            textSize = UiTheme.TYPE_BODY
            maxLines = 1
            setSingleLine(true)
            setTextColor(UiTheme.TEXT_PRIMARY)
            setHintTextColor(UiTheme.TEXT_MUTED)
            background = null
            inputType = InputType.TYPE_CLASS_TEXT
            addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit
                override fun afterTextChanged(s: Editable?) {
                    searchHandler.removeCallbacks(searchDebounce)
                    searchHandler.postDelayed(searchDebounce, 220)
                }
            })
        }
        searchBox.addView(searchInput, LinearLayout.LayoutParams(0, -2, 1f))

        searchClearBtn = TextView(this).apply {
            text = "✕"
            textSize = 16f
            setTextColor(UiTheme.ON_SURFACE_VARIANT)
            gravity = Gravity.CENTER
            minHeight = UiTheme.dp(this@MainActivity, 48)
            minWidth = UiTheme.dp(this@MainActivity, 48)
            background = UiTheme.listItemDrawable(this@MainActivity, radiusDp = UiTheme.SHAPE_FULL)
            contentDescription = "Clear search"
            visibility = View.GONE
            setOnClickListener { searchInput.setText("") }
        }
        searchBox.addView(searchClearBtn)
        container.addView(searchBox)

        // Result Count Text
        searchResultCountText = TextView(this).apply {
            textSize = UiTheme.TYPE_LABEL
            setTextColor(UiTheme.PRIMARY)
            visibility = View.GONE
            setPaddingRelative(UiTheme.dp(this@MainActivity, 20), UiTheme.dp(this@MainActivity, 6), 0, 0)
        }
        container.addView(searchResultCountText)

        // Category Subnav Tabs
        categoryTabs = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPaddingRelative(0, UiTheme.dp(this@MainActivity, 12), 0, UiTheme.dp(this@MainActivity, 8))
        }
        container.addView(HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            addView(categoryTabs, FrameLayout.LayoutParams(-2, -2))
        })

        populateCategoryTabs()

        return container.apply {
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply {
                bottomMargin = UiTheme.dp(this@MainActivity, 8)
            }
        }
    }

    // --- 5. Releases and Python runtime card ---
    private fun buildEngineManagerCard(): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = UiTheme.surfaceCard(this@MainActivity)
            setPaddingRelative(UiTheme.dp(this@MainActivity, 20), UiTheme.dp(this@MainActivity, 18), UiTheme.dp(this@MainActivity, 20), UiTheme.dp(this@MainActivity, 18))
        }

        card.addView(TextView(this).apply {
            text = "Releases and Python runtime"
            UiTheme.styleTitle(this)
        })

        card.addView(TextView(this).apply {
            text = "Verified updates of the bot's scripts from the GitHub releases, applied without reinstalling the app."
            UiTheme.styleSupporting(this)
            setPaddingRelative(0, UiTheme.dp(this@MainActivity, 4), 0, UiTheme.dp(this@MainActivity, 12))
        })

        val prefs = getSharedPreferences("mudaremote_prefs", Context.MODE_PRIVATE)
        val isBeta = prefs.getBoolean("pref_beta_channel", true)

        // Beta channel: an M3 switch row
        val channelRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            minimumHeight = UiTheme.dp(this@MainActivity, 56)
            background = UiTheme.listItemDrawable(this@MainActivity, UiTheme.SURFACE_CONTAINER_HIGH)
            setPaddingRelative(UiTheme.dp(this@MainActivity, 16), UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 8))
        }
        val channelText = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        channelText.addView(TextView(this).apply {
            text = "Beta runtime updates"
            UiTheme.styleLabel(this)
        })
        val channelLabel = TextView(this).apply {
            text = if (isBeta) "Channel: beta (previews)" else "Channel: stable (official)"
            UiTheme.styleSupporting(this)
            setTextColor(if (isBeta) UiTheme.TERTIARY else UiTheme.TEXT_MUTED)
        }
        channelText.addView(channelLabel)
        channelRow.addView(channelText, LinearLayout.LayoutParams(0, -2, 1f))

        val betaSwitch = Switch(this).apply {
            UiTheme.styleSwitch(this)
            contentDescription = "Beta runtime updates"
            isChecked = isBeta
            setOnCheckedChangeListener { _, checked ->
                prefs.edit().putBoolean("pref_beta_channel", checked).apply()
                val ch = if (checked) "beta" else "main"
                channelLabel.text = if (checked) "Channel: beta (previews)" else "Channel: stable (official)"
                channelLabel.setTextColor(if (checked) UiTheme.TERTIARY else UiTheme.TEXT_MUTED)
                Thread {
                    try {
                        PythonRuntime.ensureStarted(applicationContext)
                        Python.getInstance().getModule("android_bridge")
                            .callAttr("set_update_channel", filesDir.absolutePath, ch)
                    } catch (_: Exception) {}
                }.start()
                val msg = if (checked) "Beta channel enabled. Preview releases will be checked." else "Stable channel enabled. Only official releases will be checked."
                toast(msg)
                loadEngineVersion()
            }
        }
        channelRow.addView(betaSwitch, LinearLayout.LayoutParams(-2, -2).apply { marginStart = UiTheme.dp(this@MainActivity, 12) })
        channelRow.setOnClickListener { betaSwitch.isChecked = !betaSwitch.isChecked }
        card.addView(channelRow)

        // Two equal-width actions, then the version picker
        val actionRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }
        val btnUpdate = createGitHubButton("Pull and apply updates", UiTheme.ButtonStyle.FILLED) { checkPythonUpdates(force = true) }
        actionRow.addView(btnUpdate, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = UiTheme.dp(this@MainActivity, 8) })
        val btnRevert = createGitHubButton("Restore bundled", UiTheme.ButtonStyle.OUTLINED) { promptRevertPython() }
        actionRow.addView(btnRevert, LinearLayout.LayoutParams(0, -2, 1f))
        card.addView(actionRow, LinearLayout.LayoutParams(-1, -2).apply { topMargin = UiTheme.dp(this@MainActivity, 12) })

        val selectVersionBtn = createGitHubButton("Pick a version...", UiTheme.ButtonStyle.TONAL) { promptSelectVersion() }
        card.addView(selectVersionBtn, LinearLayout.LayoutParams(-1, -2).apply { topMargin = UiTheme.dp(this@MainActivity, 8) })

        // The app's own updater (MudaFork releases only): switches and "Check now".
        card.addView(appUpdateUi.buildSection(), LinearLayout.LayoutParams(-1, -2).apply { topMargin = UiTheme.dp(this@MainActivity, 16) })

        return card.apply {
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply {
                topMargin = UiTheme.dp(this@MainActivity, 0)
                bottomMargin = UiTheme.dp(this@MainActivity, 16)
            }
        }
    }

    // --- 6. Live log card ---
    private fun buildLogConsoleCard(): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = UiTheme.surfaceCard(this@MainActivity)
            setPaddingRelative(UiTheme.dp(this@MainActivity, 16), UiTheme.dp(this@MainActivity, 16), UiTheme.dp(this@MainActivity, 16), UiTheme.dp(this@MainActivity, 16))
        }

        // Row 1 = status dot + title + expand; row 2 = wrapping tool buttons, so nothing clips.
        val terminalTopBar = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPaddingRelative(0, 0, 0, UiTheme.dp(this@MainActivity, 8))
        }

        val terminalTitleRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        logStatusDot = TextView(this).apply {
            text = "●"
            textSize = 14f
            setTextColor(UiTheme.TEXT_MUTED)
            setPaddingRelative(UiTheme.dp(this@MainActivity, 4), 0, UiTheme.dp(this@MainActivity, 8), 0)
        }
        terminalTitleRow.addView(logStatusDot)

        val terminalTitle = TextView(this).apply {
            text = "Live log"
            UiTheme.styleTitle(this)
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
        }
        terminalTitleRow.addView(terminalTitle, LinearLayout.LayoutParams(0, -2, 1f))

        val sizeToggleBtn = createGitHubSmallBtn("Expand", UiTheme.ButtonStyle.TEXT) { btn ->
            isLogsExpanded = !isLogsExpanded
            val target = if (isLogsExpanded) 560 else 280
            TransitionManager.beginDelayedTransition(card, ChangeBounds().setDuration(220))
            logScroll.layoutParams = logScroll.layoutParams.apply { height = UiTheme.dp(this@MainActivity, target) }
            logScroll.requestLayout()
            btn.text = if (isLogsExpanded) "Collapse" else "Expand"
        }
        sizeToggleBtn.layoutParams = LinearLayout.LayoutParams(-2, -2).apply { marginStart = UiTheme.dp(this@MainActivity, 8) }
        terminalTitleRow.addView(sizeToggleBtn)
        terminalTopBar.addView(terminalTitleRow)

        val toolRow = FlowLayout(this).apply {
            setPaddingRelative(0, UiTheme.dp(this@MainActivity, 8), 0, 0)
        }
        toolRow.addView(createGitHubSmallBtn("Copy") { _ -> copyLogsToClipboard() })
        toolRow.addView(createGitHubSmallBtn("Save as TXT") { _ -> exportLogsAsTxt() })
        toolRow.addView(createGitHubSmallBtn("Share") { _ -> shareLogs() })
        toolRow.addView(createGitHubSmallBtn("Profile: all") { btn -> pickLogProfile(btn) })
        toolRow.addView(createGitHubSmallBtn("Kind: all") { btn -> pickLogKind(btn) })
        toolRow.addView(createGitHubSmallBtn("Errors only: off") { btn ->
            logFilterErrorsOnly = !logFilterErrorsOnly
            btn.text = if (logFilterErrorsOnly) "Errors only: on" else "Errors only: off"
            refreshLogs(force = true)
        })
        toolRow.addView(createGitHubSmallBtn("Search") { btn -> askLogSearch(btn) })
        val scrollToggleBtn = createGitHubSmallBtn("Auto-scroll: on") { btn ->
            isAutoScrollEnabled = !isAutoScrollEnabled
            btn.text = if (isAutoScrollEnabled) "Auto-scroll: on" else "Auto-scroll: off"
            toast(if (isAutoScrollEnabled) "Auto-scroll enabled" else "Auto-scroll paused")
        }
        toolRow.addView(scrollToggleBtn)
        toolRow.addView(createGitHubSmallBtn("Clear", UiTheme.ButtonStyle.DANGER) { _ -> clearRuntimeLogs() })
        terminalTopBar.addView(toolRow)
        card.addView(terminalTopBar)

        val subtitle = TextView(this).apply {
            text = "Newest first · the last 200 entries of this launch"
            UiTheme.styleSupporting(this)
            setTextColor(UiTheme.TEXT_MUTED)
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
            setPaddingRelative(UiTheme.dp(this@MainActivity, 4), 0, 0, UiTheme.dp(this@MainActivity, 8))
        }
        card.addView(subtitle)

        logView = TextView(this).apply {
            minLines = 10
            gravity = Gravity.TOP or Gravity.START
            setTextIsSelectable(true)
            setSingleLine(false)
            setHorizontallyScrolling(false)
            breakStrategy = Layout.BREAK_STRATEGY_SIMPLE
            hyphenationFrequency = Layout.HYPHENATION_FREQUENCY_NONE
            typeface = Typeface.MONOSPACE
            textSize = 11.5f
            setTextColor(UiTheme.TEXT_PRIMARY)
            textDirection = View.TEXT_DIRECTION_LOCALE
            setPaddingRelative(UiTheme.dp(this@MainActivity, 14), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 14), UiTheme.dp(this@MainActivity, 12))
            text = "No logs for this launch yet."
        }

        logScroll = ScrollView(this).apply {
            isFillViewport = true
            isVerticalScrollBarEnabled = true
            scrollBarStyle = View.SCROLLBARS_INSIDE_INSET
            background = UiTheme.insetSurface(this@MainActivity)
            clipToOutline = true
            addView(logView, FrameLayout.LayoutParams(-1, -2))
            setOnTouchListener { view, event ->
                when (event.actionMasked) {
                    MotionEvent.ACTION_DOWN, MotionEvent.ACTION_MOVE -> view.parent.requestDisallowInterceptTouchEvent(true)
                    MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> view.parent.requestDisallowInterceptTouchEvent(false)
                }
                false
            }
        }
        card.addView(logScroll, LinearLayout.LayoutParams(-1, UiTheme.dp(this@MainActivity, 280)))

        return card.apply {
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply {
                bottomMargin = UiTheme.dp(this@MainActivity, 16)
            }
        }
    }

    private fun setLogDot(color: Int) {
        if (::logStatusDot.isInitialized) logStatusDot.setTextColor(color)
    }

    // --- 7. Bottom dock: Save / Run / Stop all, three equal widths ---
    private fun buildStickyBottomBar(): View {
        val dock = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = UiTheme.cardDrawable(
                this@MainActivity,
                UiTheme.withAlpha(UiTheme.SURFACE_CONTAINER_HIGH, 0xF5),
                Color.TRANSPARENT,
                radiusDp = UiTheme.SHAPE_XL,
                strokeWidthDp = 0f
            )
            setPaddingRelative(UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 10))
            elevation = UiTheme.dp(this@MainActivity, 6).toFloat()
        }

        val btnSave = createGitHubButton("Save", UiTheme.ButtonStyle.TONAL) { saveCurrentProfile(showStatus = true) }
        dock.addView(btnSave, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = UiTheme.dp(this@MainActivity, 8) })

        // Primary action; long-press opens the multi-profile dispatch
        val btnStart = createGitHubButton("Run", UiTheme.ButtonStyle.FILLED, HapticFeedbackConstants.CONFIRM) { startRuntime(listOf(currentProfile)) }.apply {
            contentDescription = "Start the selected profile. Hold to pick multiple profiles."
            setOnLongClickListener {
                performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                showStartOptionsDialog()
                true
            }
        }
        dock.addView(btnStart, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = UiTheme.dp(this@MainActivity, 8) })

        val btnStop = createGitHubButton("Stop all", UiTheme.ButtonStyle.DANGER, HapticFeedbackConstants.REJECT) { doStopAll() }
        dock.addView(btnStop, LinearLayout.LayoutParams(0, -2, 1f))

        return FrameLayout(this).apply {
            setPadding(UiTheme.dp(this@MainActivity, 12), 0, UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 10))
            addView(dock)
        }
    }

    // =========================================================================
    // PROFILE MANAGEMENT
    // =========================================================================

    private fun refreshProfileTabs() {
        if (!::profileTabs.isInitialized) return
        profileTabs.removeAllViews()
        if (::profileCountBadge.isInitialized) {
            profileCountBadge.text = "${profiles.size}"
        }

        profiles.forEach { (name, data) ->
            val isSelected = (name == currentProfile)
            val hasToken = allTokensForProfile(name).isNotEmpty()
            val isSide = data.optString("account_role", "main") == "side"
            val pill = TextView(this).apply {
                text = name + (if (isSide) " · Side" else "") + (if (hasToken) "" else " · no token")
                UiTheme.styleChip(this, isSelected)
                maxWidth = UiTheme.dp(this@MainActivity, 240)
                if (!hasToken && !isSelected) setTextColor(UiTheme.TERTIARY)
                contentDescription = "Open profile $name" + (if (isSide) ", side account" else ", main account") +
                    if (hasToken) "" else " (token missing)"
                setOnClickListener { openProfile(name) }
            }

            val params = LinearLayout.LayoutParams(-2, -2).apply {
                marginEnd = UiTheme.dp(this@MainActivity, 8)
            }
            profileTabs.addView(pill, params)
        }
        refreshProfileSummary()
    }

    private fun openProfile(name: String) {
        if (!profiles.containsKey(name)) return
        if (name != currentProfile && currentProfile.isNotBlank()) {
            saveCurrentProfile(showStatus = false)
        }
        currentProfile = name
        renderCurrentProfile()
        refreshProfileTabs()
        updateStatusBadge("● Profile: $name", UiTheme.ACCENT_BLUE)
    }

    private fun promptCreateProfile() {
        val input = EditText(this).apply {
            hint = "Profile name (e.g. alt-worker)"
            setText("profile-${profiles.size + 1}")
            setTextColor(UiTheme.TEXT_PRIMARY)
            setHintTextColor(UiTheme.TEXT_MUTED)
        }
        AlertDialog.Builder(this)
            .setTitle("New profile")
            .setMessage("Name the new profile:")
            .setView(wrapForDialog(input))
            .setPositiveButton("Create") { _, _ ->
                if (!ensureWritableStorage()) return@setPositiveButton
                val name = input.text.toString().trim()
                if (name.isNotBlank()) {
                    val nameError = profileNameError(name, null)
                    if (nameError != null) {
                        toast(nameError)
                    } else {
                        saveCurrentProfile(showStatus = false)
                        val newObj = schemaDefaults().put("channel_id", "").put("roll_command", "wa").put("rolling", true)
                            .put("profile_id", newProfileId())
                        profiles[name] = newObj
                        currentProfile = name
                        persist()
                        refreshProfileTabs()
                        renderCurrentProfile()
                        toast("Created profile '$name'")
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun duplicateCurrentProfile() {
        if (!ensureWritableStorage()) return
        if (currentProfile.isBlank() || !profiles.containsKey(currentProfile)) return
        saveCurrentProfile(showStatus = false)
        val copyName = "${currentProfile}_patch"
        var targetName = copyName
        var counter = 2
        while (profiles.keys.any { it.equals(targetName, ignoreCase = true) }) {
            targetName = "${copyName}_$counter"
            counter++
        }
        val currentJson = profiles[currentProfile] ?: JSONObject()
        val clonedJson = JSONObject(currentJson.toString())
        // A fork is a new profile: it never shares the stable id of its source.
        clonedJson.put("profile_id", newProfileId())
        profiles[targetName] = clonedJson
        tokens[currentProfile]?.let { tokens[targetName] = it }
        currentProfile = targetName
        persist()
        refreshProfileTabs()
        renderCurrentProfile()
        toast("Forked to '$targetName'")
    }

    private fun newProfileId(): String =
        "p" + java.util.UUID.randomUUID().toString().replace("-", "").take(15)

    /**
     * Every profile gets a stable id (tokens, side-account links and runtime
     * keys follow the id, so a rename loses nothing). Profiles saved before
     * roles existed and carrying a Main Account ID become Side accounts.
     */
    private fun ensureProfileIdentity(): Boolean {
        var changed = false
        val seen = HashSet<String>()
        profiles.values.forEach { data ->
            var id = data.optString("profile_id", "").trim()
            if (!profileIdPattern.matches(id) || !seen.add(id)) {
                do { id = newProfileId() } while (!seen.add(id))
                data.put("profile_id", id)
                changed = true
            }
            if (!data.has("account_role")) {
                val legacyMain = data.optString("main_account_id", "").trim()
                data.put("account_role", if (legacyMain.isNotEmpty()) "side" else "main")
                changed = true
            }
        }
        return changed
    }

    /** Same rules as the desktop editor: trimmed, 1-40 characters, unique ignoring case. */
    private fun profileNameError(name: String, ignore: String?): String? {
        if (name.isEmpty()) return "Profile name cannot be empty."
        if (name.codePointCount(0, name.length) > 40) return "Profile name must be at most 40 characters."
        if (name.any { it.code < 32 }) return "Profile name cannot contain control characters."
        val clash = profiles.keys.firstOrNull { existing ->
            existing.equals(name, ignoreCase = true) && (ignore == null || !existing.equals(ignore, ignoreCase = true))
        }
        return clash?.let { "A profile named '$it' already exists." }
    }

    private fun promptRenameProfile() {
        if (currentProfile.isBlank() || !profiles.containsKey(currentProfile)) return
        val oldName = currentProfile
        val input = EditText(this).apply {
            hint = "1-40 characters, any language"
            setText(oldName)
            setSelection(oldName.length)
            setTextColor(UiTheme.TEXT_PRIMARY)
            setHintTextColor(UiTheme.TEXT_MUTED)
        }
        AlertDialog.Builder(this)
            .setTitle("Rename profile")
            .setMessage("The profile keeps its settings, tokens, schedule and side-account links.")
            .setView(wrapForDialog(input))
            .setPositiveButton("Rename") { _, _ -> renameProfile(oldName, input.text.toString()) }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun renameProfile(oldName: String, rawName: String) {
        if (!ensureWritableStorage()) return
        if (!profiles.containsKey(oldName)) return
        val newName = rawName.trim()
        if (newName == oldName) return
        profileNameError(newName, oldName)?.let { toast(it); return }
        if (oldName == currentProfile) saveCurrentProfile(showStatus = false)
        // Re-key both maps in place so the tab order stays the same.
        val renamedProfiles = LinkedHashMap<String, JSONObject>()
        profiles.forEach { (name, data) -> renamedProfiles[if (name == oldName) newName else name] = data }
        val renamedTokens = LinkedHashMap<String, String>()
        tokens.forEach { (name, value) -> renamedTokens[if (name == oldName) newName else name] = value }
        profiles.clear(); profiles.putAll(renamedProfiles)
        tokens.clear(); tokens.putAll(renamedTokens)
        if (currentProfile == oldName) currentProfile = newName
        persist()
        refreshProfileTabs()
        renderCurrentProfile()
        val running = MudaRemoteService.runtimeState != MudaRemoteService.RuntimeState.STOPPED
        toast(if (running) "Renamed to '$newName'. Restart the runtime to see the new name in logs."
              else "Renamed to '$newName'")
    }

    private fun promptDeleteCurrentProfile() {
        if (profiles.size <= 1) {
            toast("The last profile cannot be deleted.")
            return
        }
        AlertDialog.Builder(this)
            .setTitle("Delete profile?")
            .setMessage("Profile '$currentProfile', its settings and its token are deleted from this phone. This cannot be undone.")
            .setPositiveButton("Delete") { _, _ ->
                if (!ensureWritableStorage()) return@setPositiveButton
                val toDelete = currentProfile
                profiles.remove(toDelete)
                tokens.remove(toDelete)
                currentProfile = profiles.keys.first()
                persist()
                refreshProfileTabs()
                renderCurrentProfile()
                toast("Deleted profile '$toDelete'")
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun shareCurrentProfile() {
        saveCurrentProfile(showStatus = false)
        val currentJson = profiles[currentProfile] ?: return
        val exportJson = JSONObject(currentJson.toString())
        exportJson.remove("token")
        exportJson.remove("tokens")
        exportJson.remove("additional_tokens")
        val formatted = exportJson.toString(2)

        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val clip = ClipData.newPlainText("MudaFork Preset $currentProfile", formatted)
        clipboard.setPrimaryClip(clip)
        toast("Copied '$currentProfile' JSON to the clipboard.")
    }

    // =========================================================================
    // FIELD RENDERING (GITHUB BOXES)
    // =========================================================================

    private fun renderCurrentProfile() {
        val data = profiles[currentProfile] ?: JSONObject()
        inheritedKakeraAtRender = (data.optJSONArray("kakera_emojis") ?: schemaFields.getJSONObject("kakera_emojis").getJSONArray("default")).toString()
        tokenInput.setText(tokens[currentProfile].orEmpty())
        fieldsContainer.removeAllViews()
        fieldViews.clear()
        sectionContainers.clear()
        sectionHeaders.clear()
        sectionChevrons.clear()

        val keys = (data.keys().asSequence().toList() + inheritedKakeraFields).distinct().asSequence()
            .filter { it != "token" && it != "additional_tokens" && it != "profile_id" }
            .toList().sortedWith(
            compareBy<String> { sectionRank(schemaFields.optJSONObject(it)?.optString("section", "Advanced") ?: "Advanced") }
                .thenBy { schemaFields.optJSONObject(it)?.optInt("order", 100) ?: 100 }.thenBy { it }
        )

        var previousSection = ""
        var sectionIndex = 0
        var sectionBody: LinearLayout? = null

        for (key in keys) {
            val value = data.opt(key) ?: if (key in inheritedKakeraFields) {
                JSONArray(inheritedKakeraAtRender)
            } else null
            val meta = schemaFields.optJSONObject(key)
            val section = meta?.optString("section", "Advanced") ?: "Advanced"

            if (section != previousSection) {
                val collapsed = collapsedSections.getOrPut(section) { sectionIndex > 0 }
                val sectionCard = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                    background = UiTheme.surfaceCard(this@MainActivity)
                    setPaddingRelative(UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 8))
                }

                // Child 0 = the pressable header (title, one-line description, chevron); child 1 = the body.
                val headerLayout = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    background = UiTheme.listItemDrawable(this@MainActivity, radiusDp = 22f)
                    minimumHeight = UiTheme.dp(this@MainActivity, 64)
                    setPaddingRelative(UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 10))
                }

                val headerText = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
                val headerTitle = TextView(this).apply {
                    UiTheme.styleTitle(this)
                    maxLines = 2
                    ellipsize = android.text.TextUtils.TruncateAt.END
                }
                headerText.addView(headerTitle)
                headerText.addView(TextView(this).apply {
                    text = getSectionDescription(section)
                    UiTheme.styleSupporting(this)
                    maxLines = 1
                    ellipsize = android.text.TextUtils.TruncateAt.END
                })
                headerLayout.addView(headerText, LinearLayout.LayoutParams(0, -2, 1f))

                val chevron = TextView(this).apply {
                    textSize = 14f
                    setTextColor(UiTheme.ON_SURFACE_VARIANT)
                    gravity = Gravity.CENTER
                    minWidth = UiTheme.dp(this@MainActivity, 40)
                    importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
                }
                headerLayout.addView(chevron)

                val newBody = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                    setPaddingRelative(UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 4), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 8))
                    visibility = if (collapsed) View.GONE else View.VISIBLE
                }

                fun updateHeader() {
                    val open = newBody.visibility == View.VISIBLE
                    chevron.text = if (open) "▲" else "▼"
                    headerTitle.text = section
                    headerLayout.contentDescription = "$section, " + if (open) "expanded" else "collapsed"
                }
                updateHeader()

                headerLayout.setOnClickListener {
                    TransitionManager.beginDelayedTransition(
                        sectionCard,
                        ChangeBounds().setDuration(180).setInterpolator(android.view.animation.DecelerateInterpolator())
                    )
                    newBody.visibility = if (newBody.visibility == View.VISIBLE) View.GONE else View.VISIBLE
                    collapsedSections[section] = (newBody.visibility != View.VISIBLE)
                    updateHeader()
                }

                sectionCard.addView(headerLayout)
                sectionCard.addView(newBody)

                val cardParams = LinearLayout.LayoutParams(-1, -2).apply {
                    topMargin = if (sectionIndex == 0) 0 else UiTheme.dp(this@MainActivity, 12)
                    bottomMargin = UiTheme.dp(this@MainActivity, 4)
                }
                fieldsContainer.addView(sectionCard, cardParams)

                sectionContainers[section] = sectionCard
                sectionHeaders[section] = headerTitle
                sectionChevrons[section] = chevron
                sectionBody = newBody
                sectionIndex++
                previousSection = section
            }

            val body = sectionBody ?: fieldsContainer
            val fieldCard = buildFieldView(key, value, meta)
            body.addView(fieldCard)
        }

        if (keys.isEmpty()) {
            fieldsContainer.addView(TextView(this).apply {
                text = "No settings found in this profile."
                setTextColor(UiTheme.TEXT_MUTED)
                setPadding(UiTheme.dp(this@MainActivity, 16), UiTheme.dp(this@MainActivity, 16), UiTheme.dp(this@MainActivity, 16), UiTheme.dp(this@MainActivity, 16))
            })
        }

        filterSettings()
    }

    /** Pick another profile by name; the stable profile id is what gets stored. */
    private fun buildProfilePicker(key: String, value: Any?, labelText: String, descriptionText: String, container: LinearLayout): View {
        container.addView(TextView(this).apply {
            text = labelText
            UiTheme.styleLabel(this)
        })
        val ownId = profiles[currentProfile]?.optString("profile_id", "").orEmpty()
        val current = (value as? String).orEmpty()
        val group = RadioGroup(this)
        fun addChoice(tagValue: String, label: String) {
            val radio = RadioButton(this).apply {
                id = View.generateViewId()
                tag = tagValue
                text = label
                textSize = UiTheme.TYPE_BODY
                setTextColor(UiTheme.TEXT_PRIMARY)
                minHeight = UiTheme.dp(this@MainActivity, 48)
                buttonTintList = ColorStateList.valueOf(UiTheme.PRIMARY)
            }
            group.addView(radio)
            if (tagValue == current) group.check(radio.id)
        }
        addChoice("", "(none)")
        profiles.forEach { (name, data) ->
            val id = data.optString("profile_id", "")
            val isSide = data.optString("account_role", "main") == "side"
            if (id.isNotEmpty() && id != ownId && (!isSide || id == current)) {
                addChoice(id, if (isSide) "$name (a side account: pick a main instead)" else name)
            }
        }
        if (current.isNotEmpty() && profiles.values.none { it.optString("profile_id", "") == current }) {
            addChoice(current, "(deleted profile: runs as an ordinary account)")
        }
        fieldViews[key] = group
        container.addView(group)
        if (descriptionText.isNotBlank()) {
            container.addView(TextView(this).apply {
                text = descriptionText
                UiTheme.styleSupporting(this)
            })
        }
        return container
    }

    private fun sideRoleWarning(data: JSONObject): String? {
        if (data.optString("account_role", "main") != "side") return null
        val mainId = data.optString("main_profile_id", "")
        if (mainId.isEmpty()) {
            return if (data.optString("main_account_id", "").isBlank())
                "No main profile is picked; this side runs as an ordinary account." else null
        }
        if (mainId == data.optString("profile_id", "")) return "A side account cannot be its own main."
        val main = profiles.values.firstOrNull { it.optString("profile_id", "") == mainId }
            ?: return "Its main profile no longer exists; this side runs as an ordinary account."
        if (main.optString("account_role", "main") == "side") return "Its main is itself a side account; pick a main account."
        return null
    }

    private fun buildFieldView(key: String, value: Any?, meta: JSONObject?): View {
        if (meta?.optString("widget", "") == "send_again") return buildSendAgainField(key, value, meta)
        if (meta?.optString("widget", "") == "request_now") return buildRequestNowField(key, value, meta)
        var shown = value
        var note: String? = null
        if (key == "fast_setup" && value == true) {
            fastSetupSentAt()?.let {
                shown = false
                note = "Sent once ($it); it stays off. Use «Send again» to repeat it once."
            }
        }
        val view = buildFieldViewInner(key, shown, meta)
        if (meta?.optBoolean("side_only", false) == true) {
            val role = profiles[currentProfile]?.optString("account_role", "main") ?: "main"
            if (role != "side") {
                setViewTreeEnabled(view, false)
                view.alpha = 0.55f
                note = "Side accounts only: this profile is a Main account, so this setting is disabled."
            }
        }
        note?.let { text ->
            (view as? LinearLayout)?.addView(TextView(this).apply {
                this.text = text
                UiTheme.styleSupporting(this)
                setTextColor(UiTheme.TEXT_MUTED)
                setPaddingRelative(0, UiTheme.dp(this@MainActivity, 4), 0, 0)
            })
        }
        return view
    }

    private fun setViewTreeEnabled(view: View, enabled: Boolean) {
        view.isEnabled = enabled
        if (view is android.view.ViewGroup) {
            for (index in 0 until view.childCount) setViewTreeEnabled(view.getChildAt(index), enabled)
        }
    }

    /** When Fast setup was already sent for this profile's first account (runtime state file), else null. */
    private fun fastSetupSentAt(): String? {
        val data = profiles[currentProfile] ?: return null
        val id = data.optString("profile_id", "")
        if (id.isEmpty()) return null
        val file = File(filesDir, "mudafork_account_state.json")
        if (!file.isFile) return null
        return runCatching {
            val record = JSONObject(file.readText()).optJSONObject("accounts")
                ?.optJSONObject("$id#1")?.optJSONObject("fast_setup")
            if (record != null && record.optInt("round", 0) >= data.optInt("fast_setup_round", 0))
                record.optString("at", "").take(16).replace('T', ' ').ifEmpty { "date unknown" }
            else null
        }.getOrNull()
    }

    /** «Send again» for Fast setup: raises the stored round and switches Fast setup on. */
    private fun buildSendAgainField(key: String, value: Any?, meta: JSONObject): View {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPaddingRelative(0, UiTheme.dp(this@MainActivity, 8), 0, UiTheme.dp(this@MainActivity, 8))
            tag = "field_container_$key"
        }
        val counter = EditText(this).apply {
            setText(((value as? Number)?.toInt() ?: 0).toString())
            inputType = InputType.TYPE_CLASS_NUMBER
            visibility = View.GONE
            tag = key
        }
        fieldViews[key] = counter
        container.addView(TextView(this).apply {
            text = meta.optString("label", key)
            UiTheme.styleLabel(this)
        })
        val description = meta.optString("description", "")
        if (description.isNotBlank()) {
            container.addView(TextView(this).apply {
                text = description
                UiTheme.styleSupporting(this)
            })
        }
        container.addView(createGitHubSmallBtn("Send again", UiTheme.ButtonStyle.TONAL) { _ ->
            val next = (counter.text.toString().toIntOrNull() ?: 0) + 1
            counter.setText(next.toString())
            (fieldViews["fast_setup"] as? Switch)?.isChecked = true
            toast("Fast setup will be sent once more after you save.")
        }, LinearLayout.LayoutParams(-2, -2).apply { topMargin = UiTheme.dp(this@MainActivity, 8) })
        container.addView(counter)
        return container
    }

    /** «Give all kakera now»: a hidden request counter and a button that raises it and saves (live apply). */
    private fun buildRequestNowField(key: String, value: Any?, meta: JSONObject): View {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPaddingRelative(0, UiTheme.dp(this@MainActivity, 8), 0, UiTheme.dp(this@MainActivity, 8))
            tag = "field_container_$key"
        }
        val counter = EditText(this).apply {
            setText(((value as? Number)?.toInt() ?: 0).toString())
            inputType = InputType.TYPE_CLASS_NUMBER
            visibility = View.GONE
            tag = key
        }
        fieldViews[key] = counter
        val description = meta.optString("description", "")
        if (description.isNotBlank()) {
            container.addView(TextView(this).apply {
                text = description
                UiTheme.styleSupporting(this)
            })
        }
        container.addView(
            createGitHubSmallBtn(meta.optString("label", "Give all kakera now"), UiTheme.ButtonStyle.TONAL) { _ ->
                if (key == "give_spheres_now_round") requestGiveAllSpheres() else requestGiveAllKakera()
            },
            LinearLayout.LayoutParams(-2, -2).apply { topMargin = UiTheme.dp(this@MainActivity, 8) }
        )
        container.addView(counter)
        return container
    }

    /** Raise the profile's «Give all kakera now» counter and save; the running side gives its whole total once. */
    private fun requestGiveAllKakera() {
        val data = profiles[currentProfile] ?: return
        if (data.optString("account_role", "main") != "side") {
            toast("Give all kakera now: only a side account gives kakera to its main.")
            return
        }
        val counter = fieldViews["give_kakera_now_round"] as? EditText
        if (counter == null) {
            toast("Give all kakera now: open this profile's settings first.")
            return
        }
        val next = (counter.text.toString().toIntOrNull() ?: 0) + 1
        counter.setText(next.toString())
        saveCurrentProfile(true)
        toast("Give all kakera requested; the result appears in the logs and the account's status.")
    }

    /** Raise the profile's «Give all spheres now» counter and save; the running side gives its spheres once. */
    private fun requestGiveAllSpheres() {
        val data = profiles[currentProfile] ?: return
        if (data.optString("account_role", "main") != "side") {
            toast("Give all spheres now: only a side account gives spheres to its main.")
            return
        }
        val counter = fieldViews["give_spheres_now_round"] as? EditText
        if (counter == null) {
            toast("Give all spheres now: open this profile's settings first.")
            return
        }
        val next = (counter.text.toString().toIntOrNull() ?: 0) + 1
        counter.setText(next.toString())
        saveCurrentProfile(true)
        toast("Give all spheres requested; the result appears in the logs and the account's status.")
    }

    private fun buildFieldViewInner(key: String, value: Any?, meta: JSONObject?): View {
        val labelText = meta?.optString("label", key) ?: key
        val descriptionText = meta?.optString("description", "").orEmpty()

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPaddingRelative(0, UiTheme.dp(this@MainActivity, 8), 0, UiTheme.dp(this@MainActivity, 8))
            tag = "field_container_$key"
        }

        if (meta?.optString("picker", "") == "profile") {
            return buildProfilePicker(key, value, labelText, descriptionText, container)
        }

        val choices = meta?.optJSONObject("choices")
        if (choices != null) {
            container.addView(TextView(this).apply {
                text = labelText
                UiTheme.styleLabel(this)
            })
            val group = RadioGroup(this)
            choices.keys().asSequence().sorted().forEach { choice ->
                val radio = RadioButton(this).apply {
                    id = View.generateViewId()
                    tag = choice
                    text = choices.getString(choice)
                    textSize = UiTheme.TYPE_BODY
                    setTextColor(UiTheme.TEXT_PRIMARY)
                    minHeight = UiTheme.dp(this@MainActivity, 48)
                    buttonTintList = ColorStateList.valueOf(UiTheme.PRIMARY)
                }
                group.addView(radio)
                if (choice == value) group.check(radio.id)
            }
            fieldViews[key] = group
            container.addView(group)
            container.addView(TextView(this).apply {
                text = descriptionText
                UiTheme.styleSupporting(this)
            })
            return container
        }

        when (value) {
            is Boolean -> {
                // Switch Card
                val switchCard = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    background = UiTheme.listItemDrawable(this@MainActivity, UiTheme.SURFACE_CONTAINER_HIGH)
                    minimumHeight = UiTheme.dp(this@MainActivity, 56)
                    setPaddingRelative(UiTheme.dp(this@MainActivity, 16), UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 10))
                }

                val textCol = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                }
                val label = TextView(this).apply {
                    text = labelText
                    UiTheme.styleLabel(this)
                }
                textCol.addView(label)

                if (descriptionText.isNotBlank()) {
                    val desc = TextView(this).apply {
                        text = descriptionText
                        UiTheme.styleSupporting(this)
                        setPaddingRelative(0, UiTheme.dp(this@MainActivity, 2), 0, 0)
                    }
                    textCol.addView(desc)
                }
                switchCard.addView(textCol, LinearLayout.LayoutParams(0, -2, 1f))

                val switchView = Switch(this).apply {
                    UiTheme.styleSwitch(this)
                    isChecked = value
                    tag = key
                    contentDescription = labelText
                }
                switchCard.addView(switchView, LinearLayout.LayoutParams(-2, -2).apply { marginStart = UiTheme.dp(this@MainActivity, 12) })

                switchCard.setOnClickListener {
                    switchView.isChecked = !switchView.isChecked
                }

                fieldViews[key] = switchView
                container.addView(switchCard)
            }
            is JSONArray -> {
                // GitHub Labels Chip View
                val label = TextView(this).apply {
                    text = labelText
                    UiTheme.styleLabel(this)
                    setPadding(0, 0, 0, UiTheme.dp(this@MainActivity, 2))
                }
                container.addView(label)

                if (descriptionText.isNotBlank()) {
                    val desc = TextView(this).apply {
                        text = descriptionText
                        UiTheme.styleSupporting(this)
                        setPadding(0, 0, 0, UiTheme.dp(this@MainActivity, 4))
                    }
                    container.addView(desc)
                }

                val chipList = ChipListView(this, key, value) { updatedArray ->
                    profiles[currentProfile]?.put(key, updatedArray)
                }.apply {
                    tag = key
                }
                fieldViews[key] = chipList
                container.addView(chipList)
            }
            else -> {
                // Text or Numeric Field
                val label = TextView(this).apply {
                    text = labelText
                    UiTheme.styleLabel(this)
                    setPadding(0, 0, 0, UiTheme.dp(this@MainActivity, 2))
                }
                container.addView(label)

                if (descriptionText.isNotBlank()) {
                    val desc = TextView(this).apply {
                        text = descriptionText
                        UiTheme.styleSupporting(this)
                        setPadding(0, 0, 0, UiTheme.dp(this@MainActivity, 4))
                    }
                    container.addView(desc)
                }

                val input = EditText(this).apply {
                    setText(stringifyValue(value))
                    textSize = UiTheme.TYPE_BODY
                    setTextColor(UiTheme.TEXT_PRIMARY)
                    setHintTextColor(UiTheme.TEXT_MUTED)
                    background = UiTheme.inputDrawable(this@MainActivity)
                    minHeight = UiTheme.dp(this@MainActivity, 52)
                    setPaddingRelative(UiTheme.dp(this@MainActivity, 16), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 16), UiTheme.dp(this@MainActivity, 12))
                    tag = key

                    if (value is Int || value is Long || value is Double || value is Float) {
                        inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL or InputType.TYPE_NUMBER_FLAG_SIGNED
                    } else if (value is JSONObject) {
                        minLines = 3
                        typeface = Typeface.MONOSPACE
                        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
                    } else {
                        inputType = InputType.TYPE_CLASS_TEXT
                    }
                }
                fieldViews[key] = input
                container.addView(input)
            }
        }

        return container
    }

    // =========================================================================
    // SEARCH & SUBNAV NAVIGATION
    // =========================================================================

    /** Builds the filter chips once; a tap only restyles the two chips that change. */
    private fun populateCategoryTabs() {
        if (!::categoryTabs.isInitialized) return
        categoryTabs.removeAllViews()

        val categories = listOf(
            "All", "Connection", "Main & Side Accounts", "Rolling", "Claiming", "Character Sniping",
            "Kakera Reactions", "Kakera Loot", "Wishlist and Farming", "Spheres and Emoji",
            "Timing and Humanization", "Advanced"
        )

        categories.forEach { cat ->
            val pill = TextView(this).apply {
                text = cat
                tag = cat
                UiTheme.styleChip(this, cat == activeCategoryFilter)
                contentDescription = "Filter settings by $cat"
                setOnClickListener {
                    if (activeCategoryFilter == cat) return@setOnClickListener
                    activeCategoryFilter = cat
                    restyleCategoryTabs()
                    filterSettings()
                }
            }

            val params = LinearLayout.LayoutParams(-2, -2).apply {
                marginEnd = UiTheme.dp(this@MainActivity, 8)
            }
            categoryTabs.addView(pill, params)
        }
    }

    private fun restyleCategoryTabs() {
        for (i in 0 until categoryTabs.childCount) {
            val chip = categoryTabs.getChildAt(i) as? TextView ?: continue
            UiTheme.styleChip(chip, chip.tag == activeCategoryFilter)
        }
    }

    private fun filterSettings() {
        val query = activeSearchQuery.lowercase()
        var matchCount = 0

        sectionContainers.forEach { (sectionName, sectionCard) ->
            val categoryMatches = (activeCategoryFilter == "All" || activeCategoryFilter == sectionName)

            var visibleFieldsCount = 0
            val body = (sectionCard.getChildAt(1) as? LinearLayout) ?: return@forEach

            for (i in 0 until body.childCount) {
                val fieldContainer = body.getChildAt(i) as? LinearLayout ?: continue
                val tagStr = fieldContainer.tag as? String ?: ""
                val key = tagStr.removePrefix("field_container_")
                val meta = schemaFields.optJSONObject(key)
                val label = (meta?.optString("label", key) ?: key).lowercase()
                val desc = (meta?.optString("description", "") ?: "").lowercase()

                val queryMatches = (query.isBlank() || key.lowercase().contains(query) || label.contains(query) || desc.contains(query))

                if (categoryMatches && queryMatches) {
                    fieldContainer.visibility = View.VISIBLE
                    visibleFieldsCount++
                    matchCount++
                } else {
                    fieldContainer.visibility = View.GONE
                }
            }

            if (visibleFieldsCount > 0) {
                sectionCard.visibility = View.VISIBLE
                if (query.isNotBlank()) {
                    body.visibility = View.VISIBLE
                    collapsedSections[sectionName] = false
                    sectionHeaders[sectionName]?.text = "$sectionName ($visibleFieldsCount)"
                    sectionChevrons[sectionName]?.text = "▲"
                } else {
                    sectionHeaders[sectionName]?.let { setTextIfChanged(it, sectionName) }
                    sectionChevrons[sectionName]?.let { setTextIfChanged(it, if (body.visibility == View.VISIBLE) "▲" else "▼") }
                }
            } else {
                sectionCard.visibility = View.GONE
            }
        }

        if (query.isNotBlank()) {
            searchResultCountText.visibility = View.VISIBLE
            searchResultCountText.text = "Found $matchCount matching setting(s)"
        } else {
            searchResultCountText.visibility = View.GONE
        }
    }

    /** One line under each settings card's title. */
    private fun getSectionDescription(section: String): String = when (section) {
        "Connection" -> "Channel, commands and how the bot connects."
        "Main & Side Accounts" -> "Whether this profile is a main or a side account."
        "Rolling" -> "When and how the bot rolls."
        "Claiming" -> "Which characters to claim and when."
        "Character Sniping" -> "Catching wished characters from other rolls."
        "Kakera Reactions" -> "Which kakera to react to."
        "Kakera Loot" -> "Collecting and giving kakera."
        "Wishlist and Farming" -> "Wishes, series and farming rules."
        "Spheres and Emoji" -> "Spheres, perks and the emoji the bot reads."
        "Timing and Humanization" -> "Delays and pacing that look human."
        "Advanced" -> "Everything else. Change with care."
        else -> "More settings."
    }

    private fun sectionRank(section: String): Int = listOf(
        "Connection", "Main & Side Accounts", "Rolling", "Claiming", "Character Sniping", "Kakera Reactions", "Kakera Loot",
        "Wishlist and Farming", "Spheres and Emoji", "Timing and Humanization", "Advanced"
    ).indexOf(section).let { if (it < 0) 99 else it }

    // =========================================================================
    // SAVING & RUNTIME MANAGEMENT
    // =========================================================================

    private fun saveCurrentProfile(showStatus: Boolean) {
        if (!storageHealthy) {
            if (showStatus) ensureWritableStorage()
            return
        }
        if (!::fieldsContainer.isInitialized || currentProfile.isBlank()) return
        val data = profiles[currentProfile] ?: JSONObject()
        val oldKeys = data.keys().asSequence().toList()
        oldKeys.filter { it != "token" && it != "profile_id" && !fieldViews.containsKey(it) }.forEach { data.remove(it) }
        if (!profileIdPattern.matches(data.optString("profile_id", ""))) data.put("profile_id", newProfileId())

        for ((key, view) in fieldViews) {
            val oldValue = data.opt(key)
            val value = when (view) {
                is Switch -> view.isChecked
                is RadioGroup -> view.findViewById<RadioButton>(view.checkedRadioButtonId)?.tag ?: oldValue
                is ChipListView -> view.getJsonArray()
                is EditText -> parseValue(view.text.toString(), oldValue)
                else -> view.toString()
            }
            if (key in inheritedKakeraFields && !data.has(key) && value.toString() == inheritedKakeraAtRender) continue
            data.put(key, value)
        }
        val accountToken = tokenInput.text.toString().trim()
        if (accountToken.isNotBlank()) tokens[currentProfile] = accountToken else tokens.remove(currentProfile)
        normalizeProfileTokens(currentProfile, data)
        profiles[currentProfile] = data
        persist()
        if (showStatus) refreshProfileTabs() else refreshProfileSummary()  // role / token marks follow the saved values
        if (showStatus) {
            val applying = MudaRemoteService.applySavedProfile(this, currentProfile, data, allTokensForProfile(currentProfile))
            val roleNote = sideRoleWarning(data)?.let { " Note: $it" }.orEmpty()
            toast((if (applying) "Saved '$currentProfile'. Live update requested; see logs for the result."
                  else "Saved '$currentProfile'.") + roleNote)
        }
    }

    private fun decodeTokenValues(raw: Any?): List<String> {
        val candidates = when (raw) {
            null, JSONObject.NULL -> emptyList()
            is JSONArray -> (0 until raw.length()).mapNotNull { index -> raw.opt(index) as? String }
            is String -> {
                val text = raw.trim()
                if (text.startsWith("[")) {
                    runCatching {
                        val array = JSONArray(text)
                        (0 until array.length()).mapNotNull { index -> array.opt(index) as? String }
                    }.getOrDefault(emptyList())
                } else {
                    listOf(text)
                }
            }
            else -> emptyList()
        }
        return LinkedHashSet(candidates.map(String::trim).filter(String::isNotBlank)).toList()
    }

    private fun decodeAdditionalTokenValues(raw: Any?): List<String> {
        if (raw == null || raw == JSONObject.NULL) return emptyList()
        if (raw is JSONArray || (raw is String && raw.trim().startsWith("["))) {
            return decodeTokenValues(raw)
        }
        if (raw !is String) return emptyList()
        return LinkedHashSet(
            raw?.toString().orEmpty()
                .split(Regex("[,\\s]+"))
                .map(String::trim)
                .filter(String::isNotBlank)
        ).toList()
    }

    private fun normalizeProfileTokens(name: String, data: JSONObject) {
        val secureValues = decodeTokenValues(tokens[name])
        val legacyValues = decodeTokenValues(data.opt("token"))
        val primary = secureValues.firstOrNull() ?: legacyValues.firstOrNull()
        val additional = LinkedHashSet<String>()
        additional.addAll(secureValues.drop(if (primary == null) 0 else 1))
        additional.addAll(legacyValues.drop(if (secureValues.isEmpty() && primary != null) 1 else 0))
        additional.addAll(decodeTokenValues(data.opt("tokens")))
        additional.addAll(decodeAdditionalTokenValues(data.opt("additional_tokens")))
        if (primary != null) additional.remove(primary)
        data.remove("token")
        data.remove("additional_tokens")
        if (primary == null) {
            tokens.remove(name)
        } else {
            tokens[name] = primary
        }
        data.put("tokens", JSONArray(additional.toList()))
    }

    private fun setCanonicalTokens(name: String, values: Collection<String>) {
        val clean = LinkedHashSet(values.map(String::trim).filter(String::isNotBlank)).toList()
        val data = profiles[name] ?: schemaDefaults()
            .put("channel_id", "")
            .put("roll_command", "wa")
            .put("rolling", true)
            .also { profiles[name] = it }
        if (clean.isEmpty()) {
            tokens.remove(name)
            data.put("tokens", JSONArray())
            return
        }
        tokens[name] = clean.first()
        data.put("tokens", JSONArray(clean.drop(1)))
        data.remove("token")
        data.remove("additional_tokens")
    }

    private fun allTokensForProfile(name: String): List<String> {
        val all = LinkedHashSet<String>()
        all.addAll(decodeTokenValues(tokens[name]))
        profiles[name]?.let { data ->
            all.addAll(decodeTokenValues(data.opt("token")))
            all.addAll(decodeTokenValues(data.opt("tokens")))
            all.addAll(decodeAdditionalTokenValues(data.opt("additional_tokens")))
        }
        return all.toList()
    }

    private fun parseValue(raw: String, oldValue: Any?): Any {
        val text = raw.trim()
        if (oldValue is JSONObject || text.startsWith("{")) return runCatching { JSONObject(text) }.getOrDefault(text)
        if (oldValue is JSONArray || text.startsWith("[")) return runCatching { JSONArray(text) }.getOrDefault(text)
        return when (oldValue) {
            is Int -> text.toIntOrNull() ?: oldValue
            is Long -> text.toLongOrNull() ?: oldValue
            is Double -> text.toDoubleOrNull() ?: oldValue
            is Float -> text.toFloatOrNull() ?: oldValue
            else -> raw
        }
    }

    private fun persist() {
        if (!storageHealthy) return
        val profileRoot = JSONObject(); profiles.forEach { (name, data) -> profileRoot.put(name, data) }
        val tokenRoot = JSONObject(); tokens.forEach { (name, value) -> tokenRoot.put(name, value) }
        vault.put("profiles", profileRoot.toString())
        vault.put("tokens", tokenRoot.toString())
    }

    private fun ensureWritableStorage(): Boolean {
        if (storageHealthy) return true
        toast("Secure storage is unavailable; changes were not saved.")
        return false
    }

    private fun startRuntime(profileNames: Collection<String>) {
        saveCurrentProfile(showStatus = false)

        val selectedProfiles = JSONObject()
        val selectedTokens = JSONObject()
        val runnableNames = profileNames.filter { allTokensForProfile(it).isNotEmpty() }
        val skippedCount = profileNames.size - runnableNames.size
        runnableNames.forEach { name ->
            profiles[name]?.let { source ->
                val cleanProfile = JSONObject(source.toString()).apply {
                    remove("token")
                    remove("tokens")
                    remove("additional_tokens")
                }
                selectedProfiles.put(name, cleanProfile)
            }
            selectedTokens.put(name, JSONArray(allTokensForProfile(name)).toString())
        }
        if (selectedProfiles.length() == 0) {
            toast("Selected profile(s) have no usable account token.")
            return
        }

        beginLogSession()
        val addingToRuntime = MudaRemoteService.runtimeState != MudaRemoteService.RuntimeState.STOPPED
        MudaRemoteService.start(this, selectedProfiles.toString(), selectedTokens.toString())
        updateStatusBadge(
            if (addingToRuntime) "● Adding profile(s)..." else "● Starting profile(s)...",
            UiTheme.ACCENT_YELLOW
        )
        setLogDot(UiTheme.TERTIARY)
        val action = if (addingToRuntime) "Add request sent" else "Start request sent"
        val skipped = if (skippedCount > 0) " ($skippedCount without tokens skipped)" else ""
        toast("$action for ${selectedProfiles.length()} profile(s)$skipped.")
    }

    private fun showStartOptionsDialog() {
        val names = profiles.keys.toList()
        if (names.isEmpty()) return
        val checked = BooleanArray(names.size) { names[it] == currentProfile }
        AlertDialog.Builder(this)
            .setTitle("Run profiles")
            .setMultiChoiceItems(names.toTypedArray(), checked) { _, which, isChecked ->
                checked[which] = isChecked
            }
            .setPositiveButton("Run selected") { _, _ ->
                val picked = names.filterIndexed { index, _ -> checked[index] }
                if (picked.isEmpty()) {
                    toast("No profiles selected.")
                } else {
                    window.decorView.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
                    startRuntime(picked)
                }
            }
            .setNeutralButton("Run all") { _, _ ->
                window.decorView.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
                startRuntime(names)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private var statusBadgeColor = 0

    /** Changes the header's status chip only when its text or colour differs (no relayout per tick). */
    private fun updateStatusBadge(text: String, color: Int) {
        if (!::statusBadge.isInitialized) return
        if (statusBadge.text?.toString() != text) statusBadge.text = text
        if (statusBadgeColor != color) {
            statusBadgeColor = color
            UiTheme.styleStatusChip(statusBadge, color)
        }
    }

    // =========================================================================
    // LIVE LOG (read and highlighted off the main thread)
    // =========================================================================

    private fun refreshLogs(force: Boolean = false) {
        if (!::logView.isInitialized) return
        if (!logsVisibleForSession) return
        if (logJobInFlight && !force) return  // one read at a time; the next tick catches up

        val logFile = File(filesDir, "mudaremote_android.log")
        val filters = currentLogFilters()
        val startBytes = logSessionStartBytes
        // Two cheap stats instead of reading 512 KB every second: nothing changed, nothing to do.
        val signature = "${logFile.length()}|${logFile.lastModified()}|$startBytes|$filters"
        if (!force && signature == lastLogSignature) return
        lastLogSignature = signature

        val generation = ++logGeneration
        logJobInFlight = true
        val job = Runnable {
            val read = readSessionLog(startBytes)
            val rawText = formatSessionLogs(read.first, filters).ifBlank {
                if (filtersActive(filters)) "No log lines match the filters." else "Waiting for workflow output..."
            }
            val highlighted = UiTheme.highlightLogs(rawText)
            runOnUiThread {
                logJobInFlight = false
                if (generation != logGeneration || isFinishing || isDestroyed || !logsVisibleForSession) return@runOnUiThread
                // The file was truncated or rotated: read from its start from now on.
                if (read.second && logSessionStartBytes == startBytes) logSessionStartBytes = 0L
                if (force || rawText != displayedLogText) {
                    displayedLogText = rawText
                    logView.text = highlighted
                    if (::logScroll.isInitialized && isAutoScrollEnabled) {
                        logScroll.post { logScroll.scrollTo(0, 0) }
                    }
                }
            }
        }
        try {
            logExecutor.execute(job)
        } catch (_: java.util.concurrent.RejectedExecutionException) {
            logJobInFlight = false  // the Activity is being destroyed
        }
    }

    /** Drops any result still being computed (the console was cleared or a new session began). */
    private fun cancelPendingLogResult() {
        logGeneration++
        logJobInFlight = false
        lastLogSignature = ""
    }

    private fun clearRuntimeLogs() {
        cancelPendingLogResult()
        logsVisibleForSession = false
        displayedLogText = "No logs for this launch yet."
        if (::logView.isInitialized) logView.text = displayedLogText
        if (::logScroll.isInitialized) logScroll.scrollTo(0, 0)
        toast("Console cleared")
    }

    private fun copyLogsToClipboard() {
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val clip = ClipData.newPlainText("MudaFork Console Logs", displayedLogText)
        clipboard.setPrimaryClip(clip)
        toast("Copied raw logs to the clipboard.")
    }

    private fun beginLogSession() {
        val logFile = File(filesDir, "mudaremote_android.log")
        logSessionStartBytes = if (logFile.exists()) logFile.length() else 0L
        cancelPendingLogResult()
        logsVisibleForSession = true
        displayedLogText = "Waiting for workflow output..."
        if (::logView.isInitialized) logView.text = displayedLogText
        if (::logScroll.isInitialized) logScroll.scrollTo(0, 0)
    }

    /** The current session's log text (at most the last 512 KB). */
    private fun readSessionLog(): String {
        val read = readSessionLog(logSessionStartBytes)
        if (read.second) logSessionStartBytes = 0L
        return read.first
    }

    /**
     * Thread-safe read from [startBytes]: returns the text and whether the file was shorter than
     * [startBytes] (truncated or rotated), in which case it is read from its start.
     */
    private fun readSessionLog(startBytes: Long): Pair<String, Boolean> {
        var reset = false
        val text = runCatching {
            val logFile = File(filesDir, "mudaremote_android.log")
            if (!logFile.exists()) return@runCatching ""
            val fileLength = logFile.length()
            var start = startBytes
            if (fileLength < start) {
                start = 0L
                reset = true
            }
            if (fileLength <= start) return@runCatching ""

            val maximumBytes = 512L * 1024L
            val readFrom = maxOf(start, fileLength - maximumBytes)
            val bytes = ByteArray((fileLength - readFrom).toInt())
            RandomAccessFile(logFile, "r").use { file ->
                file.seek(readFrom)
                file.readFully(bytes)
            }
            var result = String(bytes, Charsets.UTF_8)
            if (readFrom > start) result = result.substringAfter('\n', "")
            result
        }.getOrDefault("")
        return text to reset
    }

    /** Pure (no Activity state): the newest 200 matching entries, newest first. */
    private fun formatSessionLogs(raw: String, filters: LogFilters): String {
        if (raw.isBlank()) return ""
        val entries = mutableListOf<MutableList<String>>()
        LOG_ANSI_REGEX.replace(raw, "").replace("\r", "").lineSequence().forEach { line ->
            if (line.isBlank()) return@forEach
            if (entries.isEmpty() || LOG_ENTRY_START.containsMatchIn(line)) {
                entries.add(mutableListOf(line))
            } else {
                entries.last().add(line)
            }
        }
        return entries.filter { entryMatchesLogFilters(it, filters) }.takeLast(200).asReversed().joinToString("\n\n") { entry ->
            entry.joinToString("\n")
        }
    }

    private fun currentLogFilters(): LogFilters =
        LogFilters(logFilterProfile, logFilterKind, logFilterErrorsOnly, logFilterSearch)

    private fun filtersActive(filters: LogFilters): Boolean =
        filters.profile.isNotEmpty() || filters.kind.isNotEmpty() || filters.errorsOnly || filters.search.isNotEmpty()

    // One entry = its first line plus any continuation lines. A line that is not in the shared
    // "date | profile | KIND | message" shape is kept only while no profile/kind/errors filter is set.
    private fun entryMatchesLogFilters(entry: List<String>, filters: LogFilters = currentLogFilters()): Boolean {
        val first = entry.firstOrNull() ?: return false
        val parsed = LOG_LINE_SHAPE.matchEntire(first)
        if (parsed == null) {
            if (filters.profile.isNotEmpty() || filters.kind.isNotEmpty() || filters.errorsOnly) return false
        } else {
            val profile = parsed.groupValues[2]
            val kind = parsed.groupValues[3]
            if (filters.profile.isNotEmpty() && !profile.equals(filters.profile, ignoreCase = true)) return false
            if (filters.errorsOnly && kind != "ERROR") return false
            if (filters.kind.isNotEmpty() && kind != filters.kind) return false
        }
        if (filters.search.isNotEmpty() && entry.none { it.contains(filters.search, ignoreCase = true) }) return false
        return true
    }

    // The session's lines, oldest first, with the current filters applied (what is saved or shared).
    private fun filteredLogLines(): List<String> {
        val raw = LOG_ANSI_REGEX.replace(readSessionLog(), "").replace("\r", "")
        val entries = mutableListOf<MutableList<String>>()
        raw.lineSequence().forEach { line ->
            if (line.isBlank()) return@forEach
            if (entries.isEmpty() || LOG_ENTRY_START.containsMatchIn(line)) entries.add(mutableListOf(line))
            else entries.last().add(line)
        }
        return entries.filter { entryMatchesLogFilters(it) }.flatten()
    }

    private fun pickLogProfile(btn: TextView) {
        val names = LOG_ANSI_REGEX.replace(readSessionLog(), "").lineSequence()
            .mapNotNull { LOG_LINE_SHAPE.matchEntire(it)?.groupValues?.get(2) }
            .distinct().sortedBy { it.lowercase() }.toList()
        val choices = (listOf("All profiles") + names).toTypedArray()
        AlertDialog.Builder(this)
            .setTitle("Show one profile")
            .setItems(choices) { _, which ->
                logFilterProfile = if (which == 0) "" else choices[which]
                btn.text = if (which == 0) "Profile: all" else "Profile: ${choices[which]}"
                refreshLogs(force = true)
            }
            .show()
    }

    private fun pickLogKind(btn: TextView) {
        val choices = (listOf("All kinds") + LOG_KINDS).toTypedArray()
        AlertDialog.Builder(this)
            .setTitle("Show one kind")
            .setItems(choices) { _, which ->
                logFilterKind = if (which == 0) "" else choices[which]
                btn.text = if (which == 0) "Kind: all" else "Kind: ${choices[which]}"
                refreshLogs(force = true)
            }
            .show()
    }

    private fun askLogSearch(btn: TextView) {
        val input = EditText(this).apply {
            setText(logFilterSearch)
            setSingleLine(true)
            hint = "Text to find (empty = show all)"
        }
        AlertDialog.Builder(this)
            .setTitle("Search the logs")
            .setView(wrapForDialog(input))
            .setPositiveButton("Search") { _, _ ->
                logFilterSearch = input.text?.toString()?.trim().orEmpty()
                btn.text = if (logFilterSearch.isEmpty()) "Search" else "Search: \"$logFilterSearch\""
                refreshLogs(force = true)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun exportLogsAsTxt() {
        if (filteredLogLines().isEmpty()) {
            toast("No log lines to save.")
            return
        }
        val day = java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US).format(java.util.Date())
        logExportPicker.launch("mudaremote_logs_$day.txt")
    }

    private fun writeLogExport(uri: Uri) {
        val lines = filteredLogLines()
        val ok = runCatching {
            contentResolver.openOutputStream(uri)?.use { out ->
                out.write((lines.joinToString("\n") + "\n").toByteArray(Charsets.UTF_8))
            } != null
        }.getOrDefault(false)
        toast(if (ok) "Saved ${lines.size} log lines." else "Could not save the log file.")
    }

    private fun shareLogs() {
        val lines = filteredLogLines()
        if (lines.isEmpty()) {
            toast("No log lines to share.")
            return
        }
        // Keep the newest part so the text stays within what an intent can carry.
        var text = lines.joinToString("\n")
        if (text.length > 200_000) text = text.takeLast(200_000).substringAfter('\n', "")
        val send = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_SUBJECT, "MudaFork logs")
            putExtra(Intent.EXTRA_TEXT, text)
        }
        startActivity(Intent.createChooser(send, "Share logs"))
    }

    // =========================================================================
    // TOKEN TOGGLE & CLIPBOARD
    // =========================================================================

    private fun toggleTokenVisibility() {
        isTokenVisible = !isTokenVisible
        if (isTokenVisible) {
            tokenInput.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
            tokenShowHideBtn.text = "Hide"
        } else {
            tokenInput.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            tokenShowHideBtn.text = "Show"
        }
        tokenInput.setSelection(tokenInput.text.length)
    }

    private fun pasteTokenFromClipboard() {
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val clip = clipboard.primaryClip
        if (clip != null && clip.itemCount > 0) {
            val text = clip.getItemAt(0).text?.toString()?.trim().orEmpty()
            if (text.isNotBlank()) {
                tokenInput.setText(text)
                toast("Token pasted from clipboard!")
            }
        }
    }

    // =========================================================================
    // PYTHON UPDATER & ENGINE VERSION
    // =========================================================================

    private fun loadEngineVersion() {
        if (engineInfoInFlight) return
        engineInfoInFlight = true
        Thread {
            try {
                PythonRuntime.ensureStarted(applicationContext)
                val infoJson = Python.getInstance().getModule("android_bridge")
                    .callAttr("get_runtime_info", filesDir.absolutePath)
                    .toString()
                val info = JSONObject(infoJson)
                val installed = info.optString("installed_version", info.optString("current_version", "4.9.1-beta.2"))
                val live = info.optString("live_version", "")
                val isUpdated = info.optBoolean("is_updated", false)
                val isStaged = info.optBoolean("is_staged", false)
                val displayVer = if (live.isNotBlank()) live else installed
                val statusTag = if (isStaged) "(v$installed staged)" else if (isUpdated) "(Live Release)" else "(Bundled)"
                val prefs = getSharedPreferences("mudaremote_prefs", Context.MODE_PRIVATE)
                val isBeta = prefs.getBoolean("pref_beta_channel", true)
                val channelBadge = if (isBeta) "[Beta]" else "[Stable]"
                val label = "Python engine v$displayVer $statusTag $channelBadge"
                lastEngineLabel = label
                runOnUiThread {
                    if (::engineVersionText.isInitialized) {
                        engineVersionText.text = label
                        engineVersionText.setTextColor(if (isUpdated) UiTheme.ACCENT_GREEN_BRIGHT else UiTheme.TEXT_MUTED)
                    }
                }
            } catch (_: Exception) {
                runOnUiThread {
                    if (::engineVersionText.isInitialized && lastEngineLabel.isEmpty()) {
                        engineVersionText.text = "Python engine: ready"
                    }
                }
            } finally {
                engineInfoInFlight = false
            }
        }.start()
    }

    private fun checkPythonUpdates(force: Boolean) {
        if (isUpdateInFlight) {
            toast("Update check already running...")
            return
        }
        isUpdateInFlight = true
        updateStatusBadge("● Fetching updates...", UiTheme.ACCENT_YELLOW)
        beginLogSession()
        toast("Checking for releases...")

        Thread {
            var badgeText = "● Fetch failed"
            var badgeColor = UiTheme.ACCENT_RED_BRIGHT
            var message = ""
            try {
                PythonRuntime.ensureStarted(applicationContext)
                val prefs = getSharedPreferences("mudaremote_prefs", Context.MODE_PRIVATE)
                val isBeta = prefs.getBoolean("pref_beta_channel", true)
                val ch = if (isBeta) "beta" else "main"
                val resultJson = Python.getInstance().getModule("android_bridge")
                    .callAttr("check_and_apply_update", filesDir.absolutePath, force, 10.0, ch)
                    .toString()
                val result = JSONObject(resultJson)
                val resStatus = result.optString("status", "")
                val version = result.optString("version", "")
                val error = result.optString("error", "")
                when (resStatus) {
                    "updated" -> {
                        badgeText = "● Updated v$version"; badgeColor = UiTheme.ACCENT_GREEN_BRIGHT
                        message = "Updated the runtime to v$version."
                    }
                    "staged" -> {
                        // Runtime busy: files verified and staged; activation deferred to next start.
                        badgeText = "● Staged v$version"; badgeColor = UiTheme.ACCENT_YELLOW
                        message = "v$version staged — restart the runtime to apply."
                    }
                    "current" -> {
                        badgeText = "● Up to date"; badgeColor = UiTheme.ACCENT_BLUE
                        message = "The runtime is up to date (v$version)."
                    }
                    else -> {
                        message = if (error.isNotBlank()) "Update error: $error" else "Update check complete."
                    }
                }
            } catch (e: Exception) {
                badgeText = "● Error"; badgeColor = UiTheme.ACCENT_RED_BRIGHT
                message = "Update error: ${e.message ?: e.javaClass.simpleName}"
            }
            val finalBadge = badgeText
            val finalColor = badgeColor
            val finalMessage = message
            runOnUiThread {
                updateStatusBadge(finalBadge, finalColor)
                if (finalMessage.isNotBlank()) toast(finalMessage)
                // The app (APK) itself is updated by AppUpdater, not here.
                isUpdateInFlight = false
                loadEngineVersion()
            }
        }.start()
    }

    private fun promptRevertPython() {
        AlertDialog.Builder(this)
            .setTitle("Restore the bundled version?")
            .setMessage("Restore Python runtime to the bundled APK version? Staged update cache will be cleared.")
            .setPositiveButton("Restore") { _, _ -> resetPythonRuntime() }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun promptSelectVersion() {
        toast("Fetching available releases...")
        Thread {
            try {
                PythonRuntime.ensureStarted(applicationContext)
                val prefs = getSharedPreferences("mudaremote_prefs", Context.MODE_PRIVATE)
                val isBeta = prefs.getBoolean("pref_beta_channel", true)
                val channel = if (isBeta) "beta" else "main"
                val relsJson = Python.getInstance().getModule("android_bridge")
                    .callAttr("fetch_available_versions", "android", channel)
                    .toString()
                val envelope = JSONObject(relsJson)
                if (envelope.optString("status") != "ok") {
                    val reason = envelope.optString("error", "unknown error")
                    runOnUiThread { toast("Failed to fetch releases: $reason") }
                    return@Thread
                }
                val array = envelope.optJSONArray("releases") ?: JSONArray()
                val items = mutableListOf<Triple<String, String, String>>()
                for (i in 0 until array.length()) {
                    val obj = array.getJSONObject(i)
                    val tag = obj.optString("tag", "")
                    if (tag.isEmpty()) continue
                    val isPre = obj.optBoolean("prerelease", false)
                    val isApk = obj.optBoolean("is_apk", false)
                    // optString turns a JSON null into the text "null".
                    val apkUrl = if (obj.isNull("apk_url")) "" else obj.optString("apk_url", "")
                    val typeLabel = if (isApk) "[APK]" else if (isPre) "[Beta]" else "[Stable]"
                    val apkLabel = if (!isApk && apkUrl.isNotBlank()) " + APK" else ""
                    items.add(Triple(tag, "$tag $typeLabel$apkLabel", apkUrl))
                }
                if (items.isEmpty()) {
                    runOnUiThread {
                        toast(
                            if (isBeta) "No releases are available yet."
                            else "No stable releases available yet. Enable Beta Updates to see previews."
                        )
                    }
                    return@Thread
                }
                runOnUiThread {
                    if (isFinishing) return@runOnUiThread
                    val displayNames = items.map { it.second }.toTypedArray()
                    AlertDialog.Builder(this)
                        .setTitle(if (isBeta) "Pick a version (beta)" else "Pick a version (stable)")
                        .setItems(displayNames) { _, which ->
                            val (selectedTag, _, _) = items[which]
                            if (selectedTag.startsWith("android-")) {
                                toast("The app is updated from App updates in this card.")
                            } else {
                                promptConfirmInstallVersion(selectedTag)
                            }
                        }
                        .setNeutralButton("Custom tag") { _, _ ->
                            promptCustomVersionInput()
                        }
                        .setNegativeButton("Cancel", null)
                        .show()
                }
            } catch (e: Exception) {
                runOnUiThread {
                    toast("Failed to fetch releases: ${e.message}")
                }
            }
        }.start()
    }

    private fun promptConfirmInstallVersion(tag: String) {
        AlertDialog.Builder(this)
            .setTitle("Switch the version?")
            .setMessage("Switch Python runtime to $tag?\n\nYour presets, secrets, and configurations will be kept intact.")
            .setPositiveButton("Install") { _, _ ->
                installSpecificPythonVersion(tag)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun promptCustomVersionInput() {
        val input = EditText(this).apply {
            hint = "e.g. v4.9.0 or v4.9.1-beta.2"
            setSingleLine()
        }
        AlertDialog.Builder(this)
            .setTitle("Version tag")
            .setView(wrapForDialog(input))
            .setPositiveButton("Install") { _, _ ->
                val tag = input.text.toString().trim()
                if (tag.isNotBlank()) {
                    installSpecificPythonVersion(tag)
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun installSpecificPythonVersion(tag: String) {
        if (isUpdateInFlight) {
            toast("Another runtime operation is in progress...")
            return
        }
        isUpdateInFlight = true
        updateStatusBadge("● Installing $tag...", UiTheme.ACCENT_YELLOW)
        beginLogSession()
        toast("Installing $tag...")

        Thread {
            try {
                PythonRuntime.ensureStarted(applicationContext)
                val resultJson = Python.getInstance().getModule("android_bridge")
                    .callAttr("install_specific_version", filesDir.absolutePath, tag)
                    .toString()
                val result = JSONObject(resultJson)
                val status = result.optString("status", "")
                val ver = result.optString("version", tag)
                val error = result.optString("error", "")

                runOnUiThread {
                    when (status) {
                        "updated" -> {
                            updateStatusBadge("● Updated v$ver", UiTheme.ACCENT_GREEN_BRIGHT)
                            toast("Updated to v$ver.")
                        }
                        "staged" -> {
                            updateStatusBadge("● Staged v$ver", UiTheme.ACCENT_YELLOW)
                            toast("v$ver staged — restart runtime to apply.")
                        }
                        "current" -> {
                            updateStatusBadge("● Active v$ver", UiTheme.ACCENT_BLUE)
                            toast("Already running v$ver.")
                        }
                        else -> {
                            updateStatusBadge("● Error", UiTheme.ACCENT_RED_BRIGHT)
                            toast(if (error.isNotBlank()) "Error: $error" else "Install failed.")
                        }
                    }
                    loadEngineVersion()
                    refreshLogs()
                }
            } catch (e: Exception) {
                runOnUiThread {
                    updateStatusBadge("● Error", UiTheme.ACCENT_RED_BRIGHT)
                    toast("Install error: ${e.message}")
                    refreshLogs()
                }
            } finally {
                isUpdateInFlight = false
            }
        }.start()
    }

    private fun resetPythonRuntime() {
        if (isUpdateInFlight) {
            toast("Another runtime operation is in progress...")
            return
        }
        isUpdateInFlight = true
        updateStatusBadge("● Resetting...", UiTheme.ACCENT_YELLOW)
        Thread {
            try {
                PythonRuntime.ensureStarted(applicationContext)
                val resultJson = Python.getInstance().getModule("android_bridge")
                    .callAttr("reset_to_bundled_code", filesDir.absolutePath)
                    .toString()
                val result = JSONObject(resultJson)
                val version = result.optString("version", "")
                runOnUiThread {
                    updateStatusBadge("● Restored v$version", UiTheme.ACCENT_BLUE)
                    toast("Restored bundled APK version (v$version).")
                    loadEngineVersion()
                    refreshLogs()
                }
            } catch (e: Exception) {
                runOnUiThread {
                    updateStatusBadge("● Error", UiTheme.ACCENT_RED_BRIGHT)
                    toast("Reset failed: ${e.message}")
                    refreshLogs()
                }
            } finally {
                isUpdateInFlight = false
            }
        }.start()
    }

    // =========================================================================
    // KEEP RUNNING (phones that close background apps)
    // =========================================================================

    private fun scrollToKeepRunning() {
        if (!::rootScroll.isInitialized || !::keepRunningCard.isInitialized) return
        refreshKeepRunningStatus()
        rootScroll.post { rootScroll.smoothScrollTo(0, keepRunningCard.top) }
    }

    private fun buildKeepRunningCard(): LinearLayout {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = UiTheme.surfaceCard(this@MainActivity)
            setPaddingRelative(UiTheme.dp(this@MainActivity, 20), UiTheme.dp(this@MainActivity, 18), UiTheme.dp(this@MainActivity, 20), UiTheme.dp(this@MainActivity, 18))
        }
        card.addView(TextView(this).apply {
            text = "Keep running"
            UiTheme.styleTitle(this)
        })
        card.addView(TextView(this).apply {
            text = "Some phones close background apps even when battery optimisation is off. " +
                "Check each row, then follow the steps for your phone."
            UiTheme.styleSupporting(this)
            setPaddingRelative(0, UiTheme.dp(this@MainActivity, 4), 0, UiTheme.dp(this@MainActivity, 12))
        })

        keepRunningStatus = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        card.addView(keepRunningStatus)
        refreshKeepRunningStatus()

        // Start again after reboot (switch, default on)
        val bootRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            minimumHeight = UiTheme.dp(this@MainActivity, 56)
            background = UiTheme.listItemDrawable(this@MainActivity, UiTheme.SURFACE_CONTAINER_HIGH)
            setPaddingRelative(UiTheme.dp(this@MainActivity, 16), UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 10))
        }
        val bootText = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        bootText.addView(TextView(this).apply {
            text = "Start again after reboot"
            UiTheme.styleLabel(this)
        })
        bootText.addView(TextView(this).apply {
            text = "If the bot was running when the phone turned off, start it again after the phone starts."
            UiTheme.styleSupporting(this)
        })
        bootRow.addView(bootText, LinearLayout.LayoutParams(0, -2, 1f))
        val initialBoot = KeepAlive.resumeAfterBoot(this)
        val bootSwitch = Switch(this).apply {
            UiTheme.styleSwitch(this)
            isChecked = initialBoot
            contentDescription = "Start again after reboot"
            setOnCheckedChangeListener { _, checked ->
                KeepAlive.setResumeAfterBoot(this@MainActivity, checked)
            }
        }
        bootRow.addView(bootSwitch, LinearLayout.LayoutParams(-2, -2).apply { marginStart = UiTheme.dp(this@MainActivity, 12) })
        bootRow.setOnClickListener { bootSwitch.isChecked = !bootSwitch.isChecked }
        card.addView(bootRow, LinearLayout.LayoutParams(-1, -2).apply {
            topMargin = UiTheme.dp(this@MainActivity, 0)
            bottomMargin = UiTheme.dp(this@MainActivity, 16)
        })

        // Phone maker steps
        val maker = KeepAlive.maker()
        card.addView(TextView(this).apply {
            text = "Steps for ${KeepAlive.makerTitle(maker)}"
            UiTheme.styleLabel(this)
            setPaddingRelative(0, 0, 0, UiTheme.dp(this@MainActivity, 6))
        })
        KeepAlive.makerSteps(maker).forEachIndexed { index, step ->
            card.addView(TextView(this).apply {
                text = "${index + 1}. $step"
                UiTheme.styleSupporting(this)
                setPaddingRelative(0, 0, 0, UiTheme.dp(this@MainActivity, 4))
            })
        }

        val actions = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPaddingRelative(0, UiTheme.dp(this@MainActivity, 12), 0, 0)
        }
        actions.addView(
            createGitHubButton("Open auto-start page") { openAutoStartSettings() },
            LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = UiTheme.dp(this@MainActivity, 8) }
        )
        actions.addView(
            createGitHubButton("App info", UiTheme.ButtonStyle.OUTLINED) { openAppDetails() },
            LinearLayout.LayoutParams(0, -2, 1f)
        )
        card.addView(actions)

        return card.apply {
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply {
                topMargin = UiTheme.dp(this@MainActivity, 4)
                bottomMargin = UiTheme.dp(this@MainActivity, 16)
            }
        }
    }

    private fun refreshKeepRunningStatus() {
        if (!::keepRunningStatus.isInitialized) return
        keepRunningStatus.removeAllViews()

        val pm = getSystemService(PowerManager::class.java)
        val batteryExempt = runCatching { pm.isIgnoringBatteryOptimizations(packageName) }.getOrDefault(false)
        addKeepRunningRow(
            "Battery optimisation",
            batteryExempt,
            if (batteryExempt) "Off for MudaFork (good)" else "On: Android may stop the bot"
        ) { promptBatteryOptimization() }

        val notificationsOn = runCatching { NotificationManagerCompat.from(this).areNotificationsEnabled() }.getOrDefault(true)
        addKeepRunningRow(
            "Notifications",
            notificationsOn,
            if (notificationsOn) "Allowed (good)" else "Blocked: you will not see stop or resume notices"
        ) { openNotificationSettings() }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            val restricted = runCatching {
                getSystemService(ActivityManager::class.java).isBackgroundRestricted
            }.getOrDefault(false)
            addKeepRunningRow(
                "Background activity",
                !restricted,
                if (restricted) "Restricted: Android will stop the bot in the background" else "Allowed (good)"
            ) { openAppDetails() }
        }
    }

    private fun addKeepRunningRow(label: String, ok: Boolean, state: String, onOpen: () -> Unit) {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            minimumHeight = UiTheme.dp(this@MainActivity, 56)
            background = UiTheme.rowSurface(this@MainActivity)
            setPaddingRelative(UiTheme.dp(this@MainActivity, 16), UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 8))
        }
        val texts = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        texts.addView(TextView(this).apply {
            text = (if (ok) "✓ " else "! ") + label
            UiTheme.styleLabel(this)
        })
        texts.addView(TextView(this).apply {
            text = state
            UiTheme.styleSupporting(this)
            setTextColor(if (ok) UiTheme.PRIMARY else UiTheme.TERTIARY)
        })
        row.addView(texts, LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(
            createGitHubSmallBtn("Open", if (ok) UiTheme.ButtonStyle.OUTLINED else UiTheme.ButtonStyle.TONAL) { onOpen() },
            LinearLayout.LayoutParams(-2, -2).apply { marginStart = UiTheme.dp(this@MainActivity, 8) }
        )
        keepRunningStatus.addView(row, LinearLayout.LayoutParams(-1, -2).apply {
            bottomMargin = UiTheme.dp(this@MainActivity, 8)
        })
    }

    private fun openNotificationSettings() {
        runCatching {
            startActivity(
                Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                    .putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
            )
        }.onFailure { openAppDetails() }
    }

    private fun openAppDetails() {
        runCatching {
            startActivity(
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                    .setData(Uri.parse("package:$packageName"))
            )
        }.onFailure {
            runCatching { startActivity(Intent(Settings.ACTION_SETTINGS)) }
        }
    }

    /** Tries the maker's known auto-start pages; falls back to this app's details page. */
    private fun openAutoStartSettings() {
        for (component in KeepAlive.autoStartComponents(KeepAlive.maker())) {
            val candidate = Intent().setComponent(component)
            val resolvable = runCatching { candidate.resolveActivity(packageManager) != null }.getOrDefault(false)
            if (!resolvable) continue
            if (runCatching { startActivity(candidate) }.isSuccess) return
        }
        toast("No auto-start page found on this phone. Opening app info instead.")
        openAppDetails()
    }

    private fun promptBatteryOptimization() {
        val pm = getSystemService(PowerManager::class.java)
        val directlyExemptable = Build.VERSION.SDK_INT >= Build.VERSION_CODES.M &&
            !pm.isIgnoringBatteryOptimizations(packageName)
        AlertDialog.Builder(this)
            .setTitle("Running in the background")
            .setMessage(
                "To keep MudaFork active when your screen is off or another app is open, " +
                    "please disable battery optimizations for this application."
            )
            .setPositiveButton("Allow") { _, _ ->
                if (directlyExemptable) {
                    runCatching {
                        startActivity(
                            Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
                                .setData(Uri.parse("package:$packageName"))
                        )
                        return@setPositiveButton
                    }
                }
                runCatching {
                    startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                }.onFailure {
                    runCatching { startActivity(Intent(Settings.ACTION_SETTINGS)) }
                }
            }
            .setNegativeButton("Close", null)
            .show()
    }

    // =========================================================================
    // IMPORTING PRESETS & SECRETS
    // =========================================================================

    private fun importPresets(uri: Uri) {
        if (!ensureWritableStorage()) return
        val text = readUri(uri) ?: return
        runCatching {
            var counter = profiles.size + 1
            var candidate = "profile-$counter"
            while (profiles.containsKey(candidate)) {
                counter++
                candidate = "profile-$counter"
            }

            val staged = PresetImportParser.parse(text, schemaFields, candidate)
            if (staged.isEmpty()) return@runCatching

            val importedNames = mutableListOf<String>()
            staged.forEach { (name, data) ->
                val existingTokens = allTokensForProfile(name)
                val importedTokens = LinkedHashSet<String>().apply {
                    addAll(decodeTokenValues(data.opt("token")))
                    addAll(decodeTokenValues(data.opt("tokens")))
                    addAll(decodeAdditionalTokenValues(data.opt("additional_tokens")))
                }.toList()
                data.remove("token")
                data.remove("tokens")
                data.remove("additional_tokens")
                mergeSchemaDefaults(data)
                profiles[name] = data
                setCanonicalTokens(name, if (importedTokens.isEmpty()) existingTokens else importedTokens + existingTokens)
                importedNames += name
            }
            if (importedNames.isNotEmpty()) {
                ensureProfileIdentity()
                currentProfile = importedNames.first()
                persist()
                refreshProfileTabs()
                renderCurrentProfile()
                toast("Imported ${importedNames.size} preset(s).")
            }
        }.onFailure { toast("Presets error: ${it.message}") }
    }

    private fun importSecrets(uri: Uri) {
        if (!ensureWritableStorage()) return
        val text = readUri(uri) ?: return
        runCatching {
            val root = JSONObject(text)
            var imported = 0
            var encrypted = 0
            var invalid = 0
            root.keys().asSequence().forEach { name ->
                val raw = root.opt(name)
                invalid += when (raw) {
                    is JSONArray -> (0 until raw.length()).count { raw.opt(it) !is String }
                    is String -> if (raw.trim().startsWith("[") && runCatching { JSONArray(raw) }.isFailure) 1 else 0
                    null, JSONObject.NULL -> 0
                    else -> 1
                }
                val values = decodeTokenValues(raw)
                val portable = values.filterNot {
                    it.startsWith("AQAAANCMnd8BFdER", ignoreCase = true)
                }
                encrypted += values.size - portable.size
                // Desktop now stores tokens under "profile:<stable id>".
                val targetName = if (name.startsWith("profile:")) {
                    val wantedId = name.removePrefix("profile:")
                    profiles.entries.firstOrNull { it.value.optString("profile_id", "") == wantedId }?.key ?: name
                } else name
                if (portable.isNotEmpty()) {
                    setCanonicalTokens(targetName, portable)
                    imported += portable.size
                }
            }
            persist()
            if (encrypted > 0 || invalid > 0) {
                val warnings = mutableListOf<String>()
                if (encrypted > 0) warnings += "$encrypted Windows DPAPI token(s) need manual re-entry"
                if (invalid > 0) warnings += "$invalid invalid non-text value(s) were ignored"
                toast("Imported $imported secret(s). ${warnings.joinToString("; ")}.")
            } else {
                toast("Imported $imported secret(s) into the Keystore.")
            }
            refreshProfileTabs()
            renderCurrentProfile()
        }.onFailure { toast("Secrets error: ${it.message}") }
    }

    private fun readUri(uri: Uri): String? = runCatching {
        contentResolver.openInputStream(uri)?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }
    }.getOrElse { toast("Could not read file: ${it.message}"); null }

    // =========================================================================
    // SCHEMA & RESTORE
    // =========================================================================

    private fun loadSchema() {
        runCatching {
            assets.open("android_schema.json").bufferedReader(Charsets.UTF_8).use {
                schemaFields = JSONObject(it.readText()).optJSONObject("fields") ?: JSONObject()
            }
        }.onFailure { toast("Could not load schema: ${it.message}") }
    }

    private fun schemaDefaults(): JSONObject {
        val data = JSONObject()
        schemaFields.keys().asSequence().filter { it != "token" && it !in inheritedKakeraFields }.forEach { key ->
            data.put(key, schemaFields.optJSONObject(key)?.opt("default") ?: "")
        }
        return data
    }

    private fun mergeSchemaDefaults(data: JSONObject) {
        schemaFields.keys().asSequence().filter { it != "token" && it !in inheritedKakeraFields }.forEach { key ->
            if (!data.has(key)) data.put(key, schemaFields.optJSONObject(key)?.opt("default") ?: "")
        }
    }

    private fun restore() {
        val profilesRead = vault.read("profiles")
        val tokensRead = vault.read("tokens")
        storageHealthy = profilesRead.isSuccess && tokensRead.isSuccess
        val storedProfiles = profilesRead.getOrNull().orEmpty()
        val storedTokens = tokensRead.getOrNull().orEmpty()
        if (storedProfiles.isNotBlank()) {
            runCatching {
                val root = JSONObject(storedProfiles)
                root.keys().asSequence().forEach { name -> profiles[name] = root.getJSONObject(name) }
            }.onFailure { storageHealthy = false }
        }
        if (storedTokens.isNotBlank()) {
            runCatching {
                val root = JSONObject(storedTokens)
                root.keys().asSequence().forEach { name ->
                    val value = root.opt(name)
                    if (value !is String) throw IllegalArgumentException("Invalid token entry for '$name'")
                    tokens[name] = value
                }
            }.onFailure { storageHealthy = false }
        }
        val storedProfileSnapshot = profiles.mapValues { (_, data) -> data.toString() }
        val storedTokenSnapshot = tokens.toMap()
        if (profiles.isEmpty()) {
            val legacyProfileRead = vault.read("profile")
            val legacyTokenRead = vault.read("token")
            if (legacyProfileRead.isFailure || legacyTokenRead.isFailure) storageHealthy = false
            val legacy = legacyProfileRead.getOrNull().orEmpty()
            if (legacy.isNotBlank()) runCatching {
                val data = JSONObject(legacy)
                val name = data.optString("name", "MAIN")
                data.remove("name")
                profiles[name] = data
                legacyTokenRead.getOrNull()?.takeIf { it.isNotBlank() }?.let { tokens[name] = it }
            }.onFailure { storageHealthy = false }
        }
        if (profiles.isEmpty()) profiles["MAIN"] = schemaDefaults().put("channel_id", "").put("roll_command", "wa").put("rolling", true)
        // Before defaults are merged, so an old Main Account ID still marks a side.
        ensureProfileIdentity()
        profiles.forEach { (name, data) ->
            mergeSchemaDefaults(data)
            normalizeProfileTokens(name, data)
        }
        val normalizedProfileSnapshot = profiles.mapValues { (_, data) -> data.toString() }
        if (storageHealthy && (normalizedProfileSnapshot != storedProfileSnapshot || tokens != storedTokenSnapshot)) {
            persist()
        }
        if (!storageHealthy) {
            toast("Secure storage could not be read. Existing encrypted data was left untouched.")
        }
        currentProfile = profiles.keys.first()
        refreshProfileTabs()
        renderCurrentProfile()
    }

    private fun stringifyValue(value: Any?): String = when (value) {
        null, JSONObject.NULL -> ""
        is JSONObject, is JSONArray -> value.toString()
        else -> value.toString()
    }

    // =========================================================================
    // BUTTON & DIALOG HELPERS (styles come from UiTheme)
    // =========================================================================

    /** A full-size M3 button (48dp, pill with pressed morph); tonal unless told otherwise. */
    private fun createGitHubButton(
        text: String,
        style: UiTheme.ButtonStyle = UiTheme.ButtonStyle.TONAL,
        haptic: Int = HapticFeedbackConstants.VIRTUAL_KEY,
        onClick: () -> Unit
    ): TextView = TextView(this).apply {
        this.text = text
        UiTheme.styleButton(this, style)
        setOnClickListener { view ->
            view.performHapticFeedback(haptic)
            onClick()
        }
    }

    /** A compact M3 button for toolbars (still a 48dp touch target); outlined unless told otherwise. */
    private fun createGitHubSmallBtn(
        text: String,
        style: UiTheme.ButtonStyle = UiTheme.ButtonStyle.OUTLINED,
        onClick: (TextView) -> Unit
    ): TextView = TextView(this).apply {
        this.text = text
        UiTheme.styleButton(this, style, compact = true)
        layoutParams = LinearLayout.LayoutParams(-2, -2)
        setOnClickListener { view ->
            view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            onClick(view as TextView)
        }
    }

    /** Styles a dialog's text field as a filled M3 field with the dialog's side padding. */
    private fun wrapForDialog(input: EditText): View {
        input.background = UiTheme.inputDrawable(this)
        input.textSize = UiTheme.TYPE_BODY
        input.setTextColor(UiTheme.TEXT_PRIMARY)
        input.setHintTextColor(UiTheme.TEXT_MUTED)
        input.minHeight = UiTheme.dp(this, 52)
        input.setPaddingRelative(UiTheme.dp(this, 16), UiTheme.dp(this, 12), UiTheme.dp(this, 16), UiTheme.dp(this, 12))
        return FrameLayout(this).apply {
            setPaddingRelative(UiTheme.dp(this@MainActivity, 24), UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 24), 0)
            addView(input, FrameLayout.LayoutParams(-1, -2))
        }
    }

    private fun toast(msg: String) {
        // Safe from any thread: runOnUiThread runs inline on the main looper,
        // posts otherwise. Toast from a background thread crashes the process.
        runOnUiThread {
            Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
        }
    }

    private companion object {
        val LOG_ANSI_REGEX = Regex("\u001B\\[[;\\d]*m")
        val LOG_ENTRY_START = Regex("^(?:\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2} \\||\\[(?:\\d{4}-\\d{2}-\\d{2}|INFO|ERROR|WARN|CHECK|RESET|CLAIM|KAKERA|UPDATER|ANDROID|DEBUG))")
        val LOG_LINE_SHAPE = Regex("^(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}) \\| (.*?) \\| ([A-Z]+) \\| (.*)$")
        val LOG_KINDS = listOf("ROLL", "CLAIM", "KAKERA", "GIVE", "PERK", "SIDE", "SETUP", "SPHERE", "STATUS", "SYSTEM", "WARN", "ERROR")
    }
}
