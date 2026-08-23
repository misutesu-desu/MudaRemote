package com.mudaremote.android

import android.Manifest
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
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
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
 * MudaRemote Android application styled after GitHub Dark & Primer design system.
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

    private var schemaFields = JSONObject()
    private val profiles = linkedMapOf<String, JSONObject>()
    private val tokens = linkedMapOf<String, String>()
    private val fieldViews = linkedMapOf<String, View>()
    private val sectionContainers = linkedMapOf<String, LinearLayout>()
    private val sectionHeaders = linkedMapOf<String, TextView>()
    private val collapsedSections = mutableMapOf<String, Boolean>()

    private var currentProfile = ""
    private var isTokenVisible = false
    private var activeCategoryFilter = "All"
    private var activeSearchQuery = ""
    private var logsVisibleForSession = false
    private var logSessionStartBytes = 0L
    private var displayedLogText = ""
    private var isAutoScrollEnabled = true
    private var isLogsExpanded = false
    private var isUpdateInFlight = false
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
            refreshLogs()
            logHandler.postDelayed(this, 1000)
        }
    }

    private val presetsPicker = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri?.let { importPresets(it) }
    }
    private val secretsPicker = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri?.let { importSecrets(it) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        vault = SecretVault(this)
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 100)
        }
        setContentView(buildRootUi())
        loadSchema()
        restore()
        loadEngineVersion()
    }

    override fun onResume() {
        super.onResume()
        logHandler.post(logRefresh)
        if (lastEngineLabel.isNotEmpty()) {
            // Instant paint from cache; refresh in background afterwards.
            engineVersionText.text = lastEngineLabel
        }
        loadEngineVersion()
        syncRuntimeStatusBadge()
        adoptLiveLogsIfRunning()
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

    override fun onPause() {
        logHandler.removeCallbacks(logRefresh)
        searchHandler.removeCallbacks(searchDebounce)
        saveCurrentProfile(showStatus = false)  // Persist drafts so rotation/process death never loses edits.
        super.onPause()
    }

    private fun syncRuntimeStatusBadge() {
        if (MudaRemoteService.isRunning) {
            updateStatusBadge("● Running: $currentProfile", UiTheme.ACCENT_GREEN_BRIGHT)
            logStatusDot.text = "🟢 "
        } else if (statusBadge.text?.startsWith("● Running") == true) {
            updateStatusBadge("● Stopped", UiTheme.TEXT_MUTED)
            logStatusDot.text = "⚪ "
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
    // UI BUILDER (GITHUB PRIMER DARK SYSTEM)
    // =========================================================================

    private fun buildRootUi(): View {
        val root = FrameLayout(this).apply {
            setBackgroundColor(UiTheme.BG_APP)
        }

        val scrollContent = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(
                UiTheme.dp(this@MainActivity, 14),
                UiTheme.dp(this@MainActivity, 28),
                UiTheme.dp(this@MainActivity, 14),
                UiTheme.dp(this@MainActivity, 120)
            )
        }

        // 1. GitHub Repository Header Card
        scrollContent.addView(buildHeaderCard())

        // 2. Branch & Profile Hub Card
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

        // 6. Python Engine & Releases Card
        scrollContent.addView(buildEngineManagerCard())

        // 7. GitHub Actions Workflow Terminal / Logs
        scrollContent.addView(buildLogConsoleCard())

        val scrollView = ScrollView(this).apply {
            isFillViewport = true
            isVerticalScrollBarEnabled = false
            addView(scrollContent)
        }
        root.addView(scrollView, FrameLayout.LayoutParams(-1, -1))

        // 8. Sticky Bottom Action Bar (GitHub PR / Workflow Action Dock)
        val bottomBarView = buildStickyBottomBar()
        root.addView(bottomBarView, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM))

        // Window Insets listener to safely avoid status bar, notch, and navigation buttons
        ViewCompat.setOnApplyWindowInsetsListener(root) { _, insets ->
            val sysInsets = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()
            )

            scrollContent.setPadding(
                UiTheme.dp(this@MainActivity, 14) + sysInsets.left,
                sysInsets.top + UiTheme.dp(this@MainActivity, 10),
                UiTheme.dp(this@MainActivity, 14) + sysInsets.right,
                sysInsets.bottom + UiTheme.dp(this@MainActivity, 120)
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

    // --- 1. GitHub Repository Header Card ---
    private fun buildHeaderCard(): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = UiTheme.cardDrawable(this@MainActivity, UiTheme.BG_CARD, UiTheme.BORDER_DEFAULT, 8f, 1f)
            setPadding(UiTheme.dp(this@MainActivity, 14), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 14), UiTheme.dp(this@MainActivity, 12))
        }

        val topRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        val titleCol = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }

        // Repository breadcrumb
        val repoBreadcrumb = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        val octocat = TextView(this).apply {
            text = "🐙 "
            textSize = 16f
        }
        repoBreadcrumb.addView(octocat)

        val ownerText = TextView(this).apply {
            text = "misutesu-desu / "
            textSize = 14.5f
            setTextColor(UiTheme.ACCENT_BLUE)
        }
        repoBreadcrumb.addView(ownerText)

        val repoText = TextView(this).apply {
            text = "MudaRemote"
            textSize = 15f
            setTypeface(null, Typeface.BOLD)
            setTextColor(UiTheme.ACCENT_BLUE)
        }
        repoBreadcrumb.addView(repoText)

        val publicPill = TextView(this).apply {
            text = "Public"
            textSize = 10f
            setTypeface(null, Typeface.BOLD)
            setTextColor(UiTheme.TEXT_MUTED)
            background = UiTheme.pillDrawable(this@MainActivity, Color.TRANSPARENT, UiTheme.BORDER_DEFAULT, 10f, 1f)
            setPadding(UiTheme.dp(this@MainActivity, 6), UiTheme.dp(this@MainActivity, 1), UiTheme.dp(this@MainActivity, 6), UiTheme.dp(this@MainActivity, 1))
        }
        val pillParams = LinearLayout.LayoutParams(-2, -2).apply { leftMargin = UiTheme.dp(this@MainActivity, 6) }
        repoBreadcrumb.addView(publicPill, pillParams)
        titleCol.addView(repoBreadcrumb)

        engineVersionText = TextView(this).apply {
            text = "🐍 Python Engine: Loading..."
            textSize = 11f
            setTextColor(UiTheme.TEXT_MUTED)
            setPadding(0, UiTheme.dp(this@MainActivity, 2), 0, 0)
        }
        titleCol.addView(engineVersionText)
        topRow.addView(titleCol, LinearLayout.LayoutParams(0, -2, 1f))

        statusBadge = TextView(this).apply {
            text = "● Idle"
            textSize = 11f
            setTypeface(null, Typeface.BOLD)
            setTextColor(UiTheme.TEXT_MUTED)
            background = UiTheme.pillDrawable(this@MainActivity, UiTheme.BG_CARD_LIGHT, UiTheme.BORDER_DEFAULT, 12f, 1f)
            setPadding(UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 4), UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 4))
        }
        topRow.addView(statusBadge)
        card.addView(topRow)

        val desc = TextView(this).apply {
            text = "Self-updating Mudae Discord automation engine with Android Keystore security."
            textSize = 12f
            setTextColor(UiTheme.TEXT_SECONDARY)
            setPadding(0, UiTheme.dp(this@MainActivity, 6), 0, UiTheme.dp(this@MainActivity, 8))
        }
        card.addView(desc)

        // Action Toolbar (GitHub Repo Action style)
        val actionsRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }

        val btnBattery = createGitHubButton("🔋 Battery Guide") { promptBatteryOptimization() }
        val btnCheckUpdates = createGitHubButton("🔄 Fetch Updates") { checkPythonUpdates(force = true) }
        val btnImportPresets = createGitHubButton("📥 Import Presets") { presetsPicker.launch(arrayOf("application/json", "text/plain")) }

        actionsRow.addView(btnBattery, LinearLayout.LayoutParams(0, -2, 1f).apply { rightMargin = UiTheme.dp(this@MainActivity, 4) })
        actionsRow.addView(btnCheckUpdates, LinearLayout.LayoutParams(0, -2, 1f).apply { rightMargin = UiTheme.dp(this@MainActivity, 4) })
        actionsRow.addView(btnImportPresets, LinearLayout.LayoutParams(0, -2, 1f))
        card.addView(actionsRow)

        return card.apply {
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply {
                bottomMargin = UiTheme.dp(this@MainActivity, 10)
            }
        }
    }

    // --- 2. Branch & Profile Selector Card ---
    private fun buildProfileHubCard(): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = UiTheme.cardDrawable(this@MainActivity, UiTheme.BG_CARD, UiTheme.BORDER_DEFAULT, 8f, 1f)
            setPadding(UiTheme.dp(this@MainActivity, 14), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 14), UiTheme.dp(this@MainActivity, 12))
        }

        val headerRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        val cardTitle = TextView(this).apply {
            text = "🌿 Branches & Profiles"
            textSize = 14f
            setTypeface(null, Typeface.BOLD)
            setTextColor(UiTheme.TEXT_PRIMARY)
        }
        headerRow.addView(cardTitle, LinearLayout.LayoutParams(0, -2, 1f))

        val profileCountBadge = TextView(this).apply {
            text = "${profiles.size}"
            textSize = 10f
            setTypeface(null, Typeface.BOLD)
            setTextColor(UiTheme.ACCENT_BLUE)
            background = UiTheme.pillDrawable(this@MainActivity, UiTheme.LABEL_BLUE_BG, UiTheme.ACCENT_BLUE, 10f, 1f)
            setPadding(UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 2), UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 2))
        }
        this.profileCountBadge = profileCountBadge
        headerRow.addView(profileCountBadge)
        card.addView(headerRow)

        // Action toolbar on its own wrapping row so nothing clips on narrow screens.
        val actionsRow = FlowLayout(this).apply {
            setPadding(0, UiTheme.dp(this@MainActivity, 8), 0, 0)
        }
        actionsRow.addView(createGitHubSmallBtn("➕ New") { _ -> promptCreateProfile() })
        actionsRow.addView(createGitHubSmallBtn("📋 Fork") { _ -> duplicateCurrentProfile() })
        actionsRow.addView(createGitHubSmallBtn("🗑️ Delete") { _ -> promptDeleteCurrentProfile() })
        actionsRow.addView(createGitHubSmallBtn("📦 Export") { _ -> shareCurrentProfile() })
        card.addView(actionsRow)

        // Horizontal Profile Tabs ScrollView
        profileTabs = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, UiTheme.dp(this@MainActivity, 8), 0, UiTheme.dp(this@MainActivity, 2))
        }
        card.addView(HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            addView(profileTabs, FrameLayout.LayoutParams(-2, -2))
        })

        return card.apply {
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply {
                bottomMargin = UiTheme.dp(this@MainActivity, 10)
            }
        }
    }

    // --- 3. Repository Secrets / Token Card ---
    private fun buildTokenCard(): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = UiTheme.cardDrawable(this@MainActivity, UiTheme.BG_CARD, UiTheme.BORDER_DEFAULT, 8f, 1f)
            setPadding(UiTheme.dp(this@MainActivity, 14), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 14), UiTheme.dp(this@MainActivity, 12))
        }

        val titleRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        val title = TextView(this).apply {
            text = "🔑 Repository Secrets / Token"
            textSize = 14f
            setTypeface(null, Typeface.BOLD)
            setTextColor(UiTheme.TEXT_PRIMARY)
        }
        titleRow.addView(title, LinearLayout.LayoutParams(0, -2, 1f))

        val securityBadge = TextView(this).apply {
            text = "🔒 AES-256-GCM"
            textSize = 10f
            setTypeface(null, Typeface.BOLD)
            setTextColor(UiTheme.ACCENT_GREEN_BRIGHT)
            background = UiTheme.pillDrawable(this@MainActivity, UiTheme.LABEL_GREEN_BG, UiTheme.BORDER_DEFAULT, 10f, 1f)
            setPadding(UiTheme.dp(this@MainActivity, 7), UiTheme.dp(this@MainActivity, 2), UiTheme.dp(this@MainActivity, 7), UiTheme.dp(this@MainActivity, 2))
        }
        titleRow.addView(securityBadge)
        card.addView(titleRow)

        val desc = TextView(this).apply {
            text = "Encrypted in Android Keystore. Tokens are never committed to exported presets."
            textSize = 11.5f
            setTextColor(UiTheme.TEXT_SECONDARY)
            setPadding(0, UiTheme.dp(this@MainActivity, 3), 0, UiTheme.dp(this@MainActivity, 8))
        }
        card.addView(desc)

        // Token Input with Action Buttons (Eye, Paste, Clear)
        val inputContainer = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = UiTheme.inputDrawable(this@MainActivity, UiTheme.BG_INPUT)
            setPadding(UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 2), UiTheme.dp(this@MainActivity, 6), UiTheme.dp(this@MainActivity, 2))
        }

        tokenInput = EditText(this).apply {
            hint = "Paste your Discord token here"
            textSize = 12.5f
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
            text = "👁️"
            textSize = 14f
            contentDescription = "Toggle token visibility"
            gravity = Gravity.CENTER
            minHeight = UiTheme.dp(this@MainActivity, 48)
            minWidth = UiTheme.dp(this@MainActivity, 44)
            setOnClickListener { toggleTokenVisibility() }
        }
        inputContainer.addView(tokenShowHideBtn)

        val pasteBtn = TextView(this).apply {
            text = "📋"
            textSize = 14f
            contentDescription = "Paste token from clipboard"
            gravity = Gravity.CENTER
            minHeight = UiTheme.dp(this@MainActivity, 48)
            minWidth = UiTheme.dp(this@MainActivity, 40)
            setOnClickListener { pasteTokenFromClipboard() }
        }
        inputContainer.addView(pasteBtn)

        val clearBtn = TextView(this).apply {
            text = "✕"
            textSize = 14f
            setTypeface(null, Typeface.BOLD)
            setTextColor(UiTheme.ACCENT_RED_BRIGHT)
            contentDescription = "Clear token"
            gravity = Gravity.CENTER
            minHeight = UiTheme.dp(this@MainActivity, 48)
            minWidth = UiTheme.dp(this@MainActivity, 44)
            setOnClickListener {
                tokenInput.setText("")
                tokens.remove(currentProfile)
                toast("Token cleared for $currentProfile")
            }
        }
        inputContainer.addView(clearBtn)
        card.addView(inputContainer)

        val importSecretsBtn = TextView(this).apply {
            text = "📂 Import secrets file (.mudae-secrets.json)"
            textSize = 11f
            setTextColor(UiTheme.ACCENT_BLUE)
            setPadding(0, UiTheme.dp(this@MainActivity, 6), 0, 0)
            setOnClickListener { secretsPicker.launch(arrayOf("application/json", "text/plain")) }
        }
        card.addView(importSecretsBtn)

        return card.apply {
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply {
                bottomMargin = UiTheme.dp(this@MainActivity, 10)
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
            background = UiTheme.inputDrawable(this@MainActivity, UiTheme.BG_INPUT)
            setPadding(UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 4), UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 4))
        }

        val searchIcon = TextView(this).apply {
            text = "🔍 "
            textSize = 13f
            setTextColor(UiTheme.TEXT_MUTED)
        }
        searchBox.addView(searchIcon)

        searchInput = EditText(this).apply {
            hint = "Type \"/\" to search settings (e.g. snipe, kakera, speed)..."
            textSize = 12.5f
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
            textSize = 13f
            setTypeface(null, Typeface.BOLD)
            setTextColor(UiTheme.TEXT_MUTED)
            setPadding(UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 6), UiTheme.dp(this@MainActivity, 6), UiTheme.dp(this@MainActivity, 6))
            visibility = View.GONE
            setOnClickListener { searchInput.setText("") }
        }
        searchBox.addView(searchClearBtn)
        container.addView(searchBox)

        // Result Count Text
        searchResultCountText = TextView(this).apply {
            textSize = 11f
            setTextColor(UiTheme.ACCENT_BLUE)
            visibility = View.GONE
            setPadding(UiTheme.dp(this@MainActivity, 4), UiTheme.dp(this@MainActivity, 4), 0, 0)
        }
        container.addView(searchResultCountText)

        // Category Subnav Tabs
        categoryTabs = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, UiTheme.dp(this@MainActivity, 8), 0, UiTheme.dp(this@MainActivity, 8))
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

    // --- 5. Python Engine Releases & Packages Card ---
    private fun buildEngineManagerCard(): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = UiTheme.cardDrawable(this@MainActivity, UiTheme.BG_CARD, UiTheme.BORDER_DEFAULT, 8f, 1f)
            setPadding(UiTheme.dp(this@MainActivity, 14), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 14), UiTheme.dp(this@MainActivity, 12))
        }

        val headerRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        val title = TextView(this).apply {
            text = "📦 Releases & Python Runtime"
            textSize = 14f
            setTypeface(null, Typeface.BOLD)
            setTextColor(UiTheme.TEXT_PRIMARY)
        }
        headerRow.addView(title, LinearLayout.LayoutParams(0, -2, 1f))
        card.addView(headerRow)

        val desc = TextView(this).apply {
            text = "Cryptographically verified hot-patching. Pull latest scripts from GitHub Releases on the fly."
            textSize = 11.5f
            setTextColor(UiTheme.TEXT_SECONDARY)
            setPadding(0, UiTheme.dp(this@MainActivity, 3), 0, UiTheme.dp(this@MainActivity, 8))
        }
        card.addView(desc)

        val actionRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }

        val btnUpdate = TextView(this).apply {
            text = "🔄 Pull & Apply Updates"
            textSize = 12f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            background = UiTheme.buttonDrawable(this@MainActivity, UiTheme.ACCENT_GREEN, radiusDp = 6f)
            setPadding(UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 8))
            setOnClickListener { checkPythonUpdates(force = true) }
        }
        actionRow.addView(btnUpdate, LinearLayout.LayoutParams(0, -2, 1f).apply { rightMargin = UiTheme.dp(this@MainActivity, 6) })

        val btnRevert = TextView(this).apply {
            text = "⏪ Restore Bundled"
            textSize = 12f
            setTypeface(null, Typeface.BOLD)
            setTextColor(UiTheme.TEXT_PRIMARY)
            gravity = Gravity.CENTER
            background = UiTheme.buttonDrawable(this@MainActivity, UiTheme.BG_CARD_LIGHT, radiusDp = 6f, borderColor = UiTheme.BORDER_DEFAULT, strokeWidthDp = 1f)
            setPadding(UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 8))
            setOnClickListener { promptRevertPython() }
        }
        actionRow.addView(btnRevert, LinearLayout.LayoutParams(0, -2, 1f))
        card.addView(actionRow)

        return card.apply {
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply {
                topMargin = UiTheme.dp(this@MainActivity, 8)
                bottomMargin = UiTheme.dp(this@MainActivity, 10)
            }
        }
    }

    // --- 6. GitHub Actions Workflow Run Terminal / Console ---
    private fun buildLogConsoleCard(): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = UiTheme.cardDrawable(this@MainActivity, UiTheme.BG_TERMINAL, UiTheme.BORDER_DEFAULT, 8f, 1f)
            setPadding(UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 12))
        }

        // Terminal Top Bar (GitHub Actions step style) — two rows so nothing
        // is clipped on narrow screens: row 1 = status + title + expand,
        // row 2 = wrapping tool pills.
        val terminalTopBar = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, 0, 0, UiTheme.dp(this@MainActivity, 8))
        }

        val terminalTitleRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        logStatusDot = TextView(this).apply {
            text = "⚪ "
            textSize = 11f
        }
        terminalTitleRow.addView(logStatusDot)

        val terminalTitle = TextView(this).apply {
            text = "⚡ Actions Workflow: mudae-runtime"
            textSize = 12.5f
            setTypeface(Typeface.MONOSPACE, Typeface.BOLD)
            setTextColor(UiTheme.TEXT_PRIMARY)
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
        }
        terminalTitleRow.addView(terminalTitle, LinearLayout.LayoutParams(0, -2, 1f))

        val sizeToggleBtn = createGitHubSmallBtn("⤢ Expand") { btn ->
            isLogsExpanded = !isLogsExpanded
            val target = if (isLogsExpanded) 560 else 280
            TransitionManager.beginDelayedTransition(card, ChangeBounds().setDuration(220))
            logScroll.layoutParams = logScroll.layoutParams.apply { height = UiTheme.dp(this@MainActivity, target) }
            logScroll.requestLayout()
            btn.text = if (isLogsExpanded) "⤡ Collapse" else "⤢ Expand"
        }
        sizeToggleBtn.layoutParams = LinearLayout.LayoutParams(-2, -2).apply { leftMargin = UiTheme.dp(this@MainActivity, 6) }
        terminalTitleRow.addView(sizeToggleBtn)
        terminalTopBar.addView(terminalTitleRow)

        val toolRow = FlowLayout(this).apply {
            setPadding(0, UiTheme.dp(this@MainActivity, 6), 0, 0)
        }
        toolRow.addView(createGitHubSmallBtn("📋 Raw logs") { _ -> copyLogsToClipboard() })
        toolRow.addView(createGitHubSmallBtn("🗑️ Clear logs") { _ -> clearRuntimeLogs() })
        val scrollToggleBtn = createGitHubSmallBtn("📜 Auto-scroll: on") { btn ->
            isAutoScrollEnabled = !isAutoScrollEnabled
            btn.text = if (isAutoScrollEnabled) "📜 Auto-scroll: on" else "📜 Auto-scroll: off"
            toast(if (isAutoScrollEnabled) "Auto-scroll enabled" else "Auto-scroll paused")
        }
        toolRow.addView(scrollToggleBtn)
        terminalTopBar.addView(toolRow)
        card.addView(terminalTopBar)

        val subtitle = TextView(this).apply {
            text = "Job: mudae_bot.run_cli(['--all']) · Live output"
            textSize = 10.5f
            setTypeface(Typeface.MONOSPACE, Typeface.NORMAL)
            setTextColor(UiTheme.TEXT_MUTED)
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
            setPadding(0, 0, 0, UiTheme.dp(this@MainActivity, 6))
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
            setPadding(UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 8))
            text = "No logs for this launch yet."
        }

        logScroll = ScrollView(this).apply {
            isFillViewport = true
            isVerticalScrollBarEnabled = true
            scrollBarStyle = View.SCROLLBARS_INSIDE_INSET
            background = UiTheme.cardDrawable(this@MainActivity, UiTheme.BG_INPUT, UiTheme.BORDER_DEFAULT, 6f, 1f)
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
                bottomMargin = UiTheme.dp(this@MainActivity, 12)
            }
        }
    }

    // --- 7. Sticky Bottom Action Dock (GitHub PR / Actions Control Dock) ---
    private fun buildStickyBottomBar(): View {
        val dock = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = UiTheme.cardDrawable(
                this@MainActivity,
                Color.parseColor("#FA161b22"),
                UiTheme.BORDER_DEFAULT,
                radiusDp = 12f,
                strokeWidthDp = 1.5f
            )
            setPadding(UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 8))
            elevation = UiTheme.dp(this@MainActivity, 10).toFloat()
        }

        // 1. Commit Changes Button (GitHub Primary Green)
        val btnSave = TextView(this).apply {
            text = "💾 Save"
            textSize = 12.5f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            background = UiTheme.buttonDrawable(this@MainActivity, UiTheme.BG_CARD_LIGHT, radiusDp = 6f, borderColor = UiTheme.BORDER_DEFAULT, strokeWidthDp = 1f)
            setPadding(UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 12))
            setOnClickListener {
                performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                saveCurrentProfile(showStatus = true)
            }
        }
        dock.addView(btnSave, LinearLayout.LayoutParams(0, -2, 1.0f).apply { rightMargin = UiTheme.dp(this@MainActivity, 8) })

        // 2. Run Workflow Button (Primary Action; long-press opens multi-select dispatch)
        val btnStart = TextView(this).apply {
            text = "▶️ Run"
            textSize = 13f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            contentDescription = "Start the selected profile. Hold to pick multiple profiles."
            background = UiTheme.buttonDrawable(this@MainActivity, UiTheme.ACCENT_GREEN, radiusDp = 6f)
            setPadding(UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 12))
            setOnClickListener {
                performHapticFeedback(HapticFeedbackConstants.CONFIRM)
                startRuntime(listOf(currentProfile))
            }
            setOnLongClickListener {
                performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                showStartOptionsDialog()
                true
            }
        }
        dock.addView(btnStart, LinearLayout.LayoutParams(0, -2, 1.3f).apply { rightMargin = UiTheme.dp(this@MainActivity, 8) })

        // 3. Cancel / Stop Workflow Button (GitHub Danger Button)
        val btnStop = TextView(this).apply {
            text = "⏹ Stop"
            textSize = 12.5f
            setTypeface(null, Typeface.BOLD)
            setTextColor(UiTheme.ACCENT_RED_BRIGHT)
            gravity = Gravity.CENTER
            background = UiTheme.buttonDrawable(this@MainActivity, UiTheme.LABEL_RED_BG, radiusDp = 6f, borderColor = UiTheme.ACCENT_RED, strokeWidthDp = 1f)
            setPadding(UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 12))
            setOnClickListener {
                performHapticFeedback(HapticFeedbackConstants.REJECT)
                MudaRemoteService.stop(this@MainActivity)
                clearRuntimeLogs()
                updateStatusBadge("● Stopped", UiTheme.TEXT_MUTED)
                logStatusDot.text = "⚪ "
            }
        }
        dock.addView(btnStop, LinearLayout.LayoutParams(0, -2, 1.0f))

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

        profiles.keys.forEach { name ->
            val isSelected = (name == currentProfile)
            val hasToken = !tokens[name].isNullOrBlank()
            val missingMarker = if (hasToken) "" else " ⚠"
            val pill = TextView(this).apply {
                text = "🌿 $name$missingMarker"
                textSize = 12f
                setTypeface(null, if (isSelected) Typeface.BOLD else Typeface.NORMAL)
                setTextColor(
                    when {
                        isSelected -> UiTheme.ACCENT_BLUE
                        !hasToken -> UiTheme.ACCENT_YELLOW
                        else -> UiTheme.TEXT_SECONDARY
                    }
                )
                gravity = Gravity.CENTER
                contentDescription = "Open profile $name" + if (hasToken) "" else " (token missing)"
                background = if (isSelected) {
                    UiTheme.pressablePillDrawable(this@MainActivity, UiTheme.LABEL_BLUE_BG, UiTheme.ACCENT_BLUE, 6f, 1f)
                } else {
                    UiTheme.pressablePillDrawable(this@MainActivity, UiTheme.BG_CARD_LIGHT, UiTheme.BORDER_DEFAULT, 6f, 1f)
                }
                setPadding(UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 8))
                setOnClickListener { openProfile(name) }
            }

            val params = LinearLayout.LayoutParams(-2, -2).apply {
                rightMargin = UiTheme.dp(this@MainActivity, 6)
            }
            profileTabs.addView(pill, params)
        }
    }

    private fun openProfile(name: String) {
        if (!profiles.containsKey(name)) return
        if (name != currentProfile && currentProfile.isNotBlank()) {
            saveCurrentProfile(showStatus = false)
        }
        currentProfile = name
        renderCurrentProfile()
        refreshProfileTabs()
        updateStatusBadge("● branch: $name", UiTheme.ACCENT_BLUE)
    }

    private fun promptCreateProfile() {
        val input = EditText(this).apply {
            hint = "branch-name (e.g. alt-worker)"
            setText("profile-${profiles.size + 1}")
            setTextColor(UiTheme.TEXT_PRIMARY)
            setHintTextColor(UiTheme.TEXT_MUTED)
        }
        AlertDialog.Builder(this)
            .setTitle("Create New Branch Profile")
            .setMessage("Enter a branch name for the configuration:")
            .setView(input)
            .setPositiveButton("Create branch") { _, _ ->
                val name = input.text.toString().trim()
                if (name.isNotBlank()) {
                    if (profiles.containsKey(name)) {
                        toast("Branch '$name' already exists!")
                    } else {
                        saveCurrentProfile(showStatus = false)
                        val newObj = schemaDefaults().put("channel_id", "").put("roll_command", "wa").put("rolling", true)
                        profiles[name] = newObj
                        tokens.remove(name)
                        currentProfile = name
                        persist()
                        refreshProfileTabs()
                        renderCurrentProfile()
                        toast("Created branch '$name'")
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun duplicateCurrentProfile() {
        if (currentProfile.isBlank() || !profiles.containsKey(currentProfile)) return
        saveCurrentProfile(showStatus = false)
        val copyName = "${currentProfile}_patch"
        var targetName = copyName
        var counter = 2
        while (profiles.containsKey(targetName)) {
            targetName = "${copyName}_$counter"
            counter++
        }
        val currentJson = profiles[currentProfile] ?: JSONObject()
        val clonedJson = JSONObject(currentJson.toString())
        profiles[targetName] = clonedJson
        tokens[currentProfile]?.let { tokens[targetName] = it }
        currentProfile = targetName
        persist()
        refreshProfileTabs()
        renderCurrentProfile()
        toast("Forked to '$targetName'")
    }

    private fun promptDeleteCurrentProfile() {
        if (profiles.size <= 1) {
            toast("Cannot delete the default branch.")
            return
        }
        AlertDialog.Builder(this)
            .setTitle("Delete Branch")
            .setMessage("Are you sure you want to delete branch '$currentProfile'?")
            .setPositiveButton("Delete branch") { _, _ ->
                val toDelete = currentProfile
                profiles.remove(toDelete)
                tokens.remove(toDelete)
                currentProfile = profiles.keys.first()
                persist()
                refreshProfileTabs()
                renderCurrentProfile()
                toast("Deleted branch '$toDelete'")
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun shareCurrentProfile() {
        saveCurrentProfile(showStatus = false)
        val currentJson = profiles[currentProfile] ?: return
        val exportJson = JSONObject(currentJson.toString())
        exportJson.remove("token")
        val formatted = exportJson.toString(2)

        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val clip = ClipData.newPlainText("MudaRemote Preset $currentProfile", formatted)
        clipboard.setPrimaryClip(clip)
        toast("Copied '$currentProfile' JSON to clipboard! 📋")
    }

    // =========================================================================
    // FIELD RENDERING (GITHUB BOXES)
    // =========================================================================

    private fun renderCurrentProfile() {
        val data = profiles[currentProfile] ?: JSONObject()
        tokenInput.setText(tokens[currentProfile].orEmpty())
        fieldsContainer.removeAllViews()
        fieldViews.clear()
        sectionContainers.clear()
        sectionHeaders.clear()

        val keys = data.keys().asSequence().filter { it != "token" }.toList().sortedWith(
            compareBy<String> { sectionRank(schemaFields.optJSONObject(it)?.optString("section", "Advanced") ?: "Advanced") }.thenBy { it }
        )

        var previousSection = ""
        var sectionIndex = 0
        var sectionBody: LinearLayout? = null

        for (key in keys) {
            val value = data.opt(key)
            val meta = schemaFields.optJSONObject(key)
            val section = meta?.optString("section", "Advanced") ?: "Advanced"

            if (section != previousSection) {
                val collapsed = collapsedSections.getOrPut(section) { sectionIndex > 0 }
                val sectionCard = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                    background = UiTheme.cardDrawable(this@MainActivity, UiTheme.BG_CARD, UiTheme.BORDER_DEFAULT, 8f, 1f)
                    setPadding(UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 10))
                }

                val headerLayout = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    background = UiTheme.buttonDrawable(this@MainActivity, UiTheme.BG_CARD_LIGHT, radiusDp = 6f)
                    setPadding(UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 9), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 9))
                }

                val headerTitle = TextView(this).apply {
                    textSize = 13.5f
                    setTypeface(null, Typeface.BOLD)
                    setTextColor(UiTheme.TEXT_PRIMARY)
                }
                headerLayout.addView(headerTitle, LinearLayout.LayoutParams(0, -2, 1f))

                val newBody = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                    setPadding(0, UiTheme.dp(this@MainActivity, 6), 0, 0)
                    visibility = if (collapsed) View.GONE else View.VISIBLE
                }

                fun updateHeader() {
                    val icon = if (newBody.visibility == View.VISIBLE) "▼" else "▶"
                    val sectionEmoji = getSectionEmoji(section)
                    headerTitle.text = "$icon  $sectionEmoji $section"
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
                    topMargin = if (sectionIndex == 0) 0 else UiTheme.dp(this@MainActivity, 10)
                    bottomMargin = UiTheme.dp(this@MainActivity, 4)
                }
                fieldsContainer.addView(sectionCard, cardParams)

                sectionContainers[section] = sectionCard
                sectionHeaders[section] = headerTitle
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
                text = "No configurations found in this branch."
                setTextColor(UiTheme.TEXT_MUTED)
                setPadding(UiTheme.dp(this@MainActivity, 16), UiTheme.dp(this@MainActivity, 16), UiTheme.dp(this@MainActivity, 16), UiTheme.dp(this@MainActivity, 16))
            })
        }

        filterSettings()
    }

    private fun buildFieldView(key: String, value: Any?, meta: JSONObject?): View {
        val labelText = meta?.optString("label", key) ?: key
        val descriptionText = meta?.optString("description", "").orEmpty()

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, UiTheme.dp(this@MainActivity, 5), 0, UiTheme.dp(this@MainActivity, 5))
            tag = "field_container_$key"
        }

        when (value) {
            is Boolean -> {
                // Switch Card
                val switchCard = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    background = UiTheme.cardDrawable(this@MainActivity, UiTheme.BG_INPUT, UiTheme.BORDER_DEFAULT, 6f, 1f)
                    setPadding(UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 12), UiTheme.dp(this@MainActivity, 8))
                }

                val textCol = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                }
                val label = TextView(this).apply {
                    text = labelText
                    textSize = 13f
                    setTypeface(null, Typeface.BOLD)
                    setTextColor(UiTheme.TEXT_PRIMARY)
                }
                textCol.addView(label)

                if (descriptionText.isNotBlank()) {
                    val desc = TextView(this).apply {
                        text = descriptionText
                        textSize = 11f
                        setTextColor(UiTheme.TEXT_SECONDARY)
                        setPadding(0, UiTheme.dp(this@MainActivity, 2), 0, 0)
                    }
                    textCol.addView(desc)
                }
                switchCard.addView(textCol, LinearLayout.LayoutParams(0, -2, 1f))

                val switchView = Switch(this).apply {
                    isChecked = value
                    tag = key
                    thumbTintList = ColorStateList.valueOf(if (value) UiTheme.ACCENT_GREEN_BRIGHT else UiTheme.TEXT_MUTED)
                    trackTintList = ColorStateList.valueOf(if (value) UiTheme.ACCENT_GREEN else UiTheme.BORDER_DEFAULT)
                    setOnCheckedChangeListener { _, isChecked ->
                        thumbTintList = ColorStateList.valueOf(if (isChecked) UiTheme.ACCENT_GREEN_BRIGHT else UiTheme.TEXT_MUTED)
                        trackTintList = ColorStateList.valueOf(if (isChecked) UiTheme.ACCENT_GREEN else UiTheme.BORDER_DEFAULT)
                    }
                }
                switchCard.addView(switchView)

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
                    textSize = 13f
                    setTypeface(null, Typeface.BOLD)
                    setTextColor(UiTheme.TEXT_PRIMARY)
                    setPadding(0, 0, 0, UiTheme.dp(this@MainActivity, 2))
                }
                container.addView(label)

                if (descriptionText.isNotBlank()) {
                    val desc = TextView(this).apply {
                        text = descriptionText
                        textSize = 11f
                        setTextColor(UiTheme.TEXT_SECONDARY)
                        setPadding(0, 0, 0, UiTheme.dp(this@MainActivity, 4))
                    }
                    container.addView(desc)
                }

                val chipList = ChipListView(this, key, value) { updatedArray ->
                    // Synced
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
                    textSize = 13f
                    setTypeface(null, Typeface.BOLD)
                    setTextColor(UiTheme.TEXT_PRIMARY)
                    setPadding(0, 0, 0, UiTheme.dp(this@MainActivity, 2))
                }
                container.addView(label)

                if (descriptionText.isNotBlank()) {
                    val desc = TextView(this).apply {
                        text = descriptionText
                        textSize = 11f
                        setTextColor(UiTheme.TEXT_SECONDARY)
                        setPadding(0, 0, 0, UiTheme.dp(this@MainActivity, 4))
                    }
                    container.addView(desc)
                }

                val input = EditText(this).apply {
                    setText(stringifyValue(value))
                    textSize = 12.5f
                    setTextColor(UiTheme.TEXT_PRIMARY)
                    setHintTextColor(UiTheme.TEXT_MUTED)
                    background = UiTheme.inputDrawable(this@MainActivity)
                    setPadding(UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 7), UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 7))
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

    private fun populateCategoryTabs() {
        if (!::categoryTabs.isInitialized) return
        categoryTabs.removeAllViews()

        val categories = listOf(
            "All", "Connection", "Rolling", "Claiming", "Character Sniping",
            "Kakera Reactions", "Wishlist and Farming", "Spheres and Emoji",
            "Timing and Humanization", "Advanced"
        )

        categories.forEach { cat ->
            val isSelected = (cat == activeCategoryFilter)
            val pill = TextView(this).apply {
                val emoji = getSectionEmoji(cat)
                text = "$emoji $cat"
                textSize = 11.5f
                setTypeface(null, if (isSelected) Typeface.BOLD else Typeface.NORMAL)
                setTextColor(if (isSelected) UiTheme.ACCENT_BLUE else UiTheme.TEXT_SECONDARY)
                background = if (isSelected) {
                    UiTheme.pressablePillDrawable(this@MainActivity, UiTheme.LABEL_BLUE_BG, UiTheme.ACCENT_BLUE, 14f, 1f)
                } else {
                    UiTheme.pressablePillDrawable(this@MainActivity, UiTheme.BG_CARD_LIGHT, UiTheme.BORDER_DEFAULT, 14f, 1f)
                }
                setPadding(UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 7), UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 7))
                contentDescription = "Filter settings by $cat"
                setOnClickListener {
                    activeCategoryFilter = cat
                    populateCategoryTabs()
                    filterSettings()
                }
            }

            val params = LinearLayout.LayoutParams(-2, -2).apply {
                rightMargin = UiTheme.dp(this@MainActivity, 6)
            }
            categoryTabs.addView(pill, params)
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
                    sectionHeaders[sectionName]?.text = "▼  ${getSectionEmoji(sectionName)} $sectionName ($visibleFieldsCount)"
                }
            } else {
                sectionCard.visibility = View.GONE
            }
        }

        if (query.isNotBlank()) {
            searchResultCountText.visibility = View.VISIBLE
            searchResultCountText.text = "🔍 Found $matchCount matching setting(s)"
        } else {
            searchResultCountText.visibility = View.GONE
        }
    }

    private fun getSectionEmoji(section: String): String = when (section) {
        "Connection" -> "⚡"
        "Rolling" -> "🎲"
        "Claiming" -> "💖"
        "Character Sniping" -> "🎯"
        "Kakera Reactions" -> "💎"
        "Wishlist and Farming" -> "🌾"
        "Spheres and Emoji" -> "🔮"
        "Timing and Humanization" -> "⏱️"
        "Advanced" -> "🛠️"
        "All" -> "🐙"
        else -> "⚙️"
    }

    private fun sectionRank(section: String): Int = listOf(
        "Connection", "Rolling", "Claiming", "Character Sniping", "Kakera Reactions",
        "Wishlist and Farming", "Spheres and Emoji", "Timing and Humanization", "Advanced"
    ).indexOf(section).let { if (it < 0) 99 else it }

    // =========================================================================
    // SAVING & RUNTIME MANAGEMENT
    // =========================================================================

    private fun saveCurrentProfile(showStatus: Boolean) {
        if (!::fieldsContainer.isInitialized || currentProfile.isBlank()) return
        val data = profiles[currentProfile] ?: JSONObject()
        val oldKeys = data.keys().asSequence().toList()
        oldKeys.filter { it != "token" && !fieldViews.containsKey(it) }.forEach { data.remove(it) }

        for ((key, view) in fieldViews) {
            val oldValue = data.opt(key)
            val value = when (view) {
                is Switch -> view.isChecked
                is ChipListView -> view.getJsonArray()
                is EditText -> parseValue(view.text.toString(), oldValue)
                else -> view.toString()
            }
            data.put(key, value)
        }
        profiles[currentProfile] = data

        val accountToken = tokenInput.text.toString().trim()
        if (accountToken.isNotBlank()) tokens[currentProfile] = accountToken else tokens.remove(currentProfile)
        persist()
        if (showStatus) toast("Committed changes to '$currentProfile' 💾")
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
        val profileRoot = JSONObject(); profiles.forEach { (name, data) -> profileRoot.put(name, data) }
        val tokenRoot = JSONObject(); tokens.forEach { (name, value) -> tokenRoot.put(name, value) }
        vault.put("profiles", profileRoot.toString())
        vault.put("tokens", tokenRoot.toString())
    }

    private fun startRuntime(profileNames: Collection<String>) {
        saveCurrentProfile(showStatus = false)
        beginLogSession()

        val selectedProfiles = JSONObject()
        val selectedTokens = JSONObject()
        var tokenized = 0
        profileNames.forEach { name ->
            profiles[name]?.let { selectedProfiles.put(name, it) }
            tokens[name]?.let { selectedTokens.put(name, it); tokenized++ }
        }
        if (selectedProfiles.length() == 0) {
            toast("Nothing to run.")
            return
        }
        if (tokenized == 0) {
            toast("Selected profile(s) have no token.")
            return
        }

        MudaRemoteService.start(this, selectedProfiles.toString(), selectedTokens.toString())
        updateStatusBadge(
            if (selectedProfiles.length() == 1) "● Running: ${profileNames.first()}"
            else "● Running ${selectedProfiles.length()} profiles",
            UiTheme.ACCENT_GREEN_BRIGHT
        )
        logStatusDot.text = "🟢 "
        toast(
            if (selectedProfiles.length() == 1) "Started workflow '${profileNames.first()}' 🚀"
            else "Started ${selectedProfiles.length()} workflows 🚀"
        )
    }

    private fun showStartOptionsDialog() {
        val names = profiles.keys.toList()
        if (names.isEmpty()) return
        val checked = BooleanArray(names.size) { names[it] == currentProfile }
        AlertDialog.Builder(this)
            .setTitle("Dispatch Workflow")
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

    private fun updateStatusBadge(text: String, color: Int) {
        if (::statusBadge.isInitialized) {
            statusBadge.text = text
            statusBadge.setTextColor(color)
        }
    }

    // =========================================================================
    // LOGS CONSOLE HUB (ACTIONS VIEWER)
    // =========================================================================

    private fun refreshLogs() {
        if (!::logView.isInitialized) return
        if (!logsVisibleForSession) return

        val rawText = formatSessionLogs(readSessionLog()).ifBlank { "Waiting for workflow output..." }
        if (rawText != displayedLogText) {
            displayedLogText = rawText
            val highlighted = UiTheme.highlightLogs(rawText)
            logView.text = highlighted
            if (::logScroll.isInitialized && isAutoScrollEnabled) {
                logScroll.post { logScroll.scrollTo(0, 0) }
            }
        }
    }

    private fun clearRuntimeLogs() {
        logsVisibleForSession = false
        displayedLogText = "No logs for this launch yet."
        if (::logView.isInitialized) logView.text = displayedLogText
        if (::logScroll.isInitialized) logScroll.scrollTo(0, 0)
        toast("Console cleared")
    }

    private fun copyLogsToClipboard() {
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val clip = ClipData.newPlainText("MudaRemote Console Logs", displayedLogText)
        clipboard.setPrimaryClip(clip)
        toast("Copied raw logs to clipboard! 📋")
    }

    private fun beginLogSession() {
        val logFile = File(filesDir, "mudaremote_android.log")
        logSessionStartBytes = if (logFile.exists()) logFile.length() else 0L
        logsVisibleForSession = true
        displayedLogText = "Waiting for workflow output..."
        if (::logView.isInitialized) logView.text = displayedLogText
        if (::logScroll.isInitialized) logScroll.scrollTo(0, 0)
    }

    private fun readSessionLog(): String = runCatching {
        val logFile = File(filesDir, "mudaremote_android.log")
        if (!logFile.exists()) return@runCatching ""
        val fileLength = logFile.length()
        if (fileLength < logSessionStartBytes) logSessionStartBytes = 0L
        if (fileLength <= logSessionStartBytes) return@runCatching ""

        val maximumBytes = 512L * 1024L
        val readFrom = maxOf(logSessionStartBytes, fileLength - maximumBytes)
        val bytes = ByteArray((fileLength - readFrom).toInt())
        RandomAccessFile(logFile, "r").use { file ->
            file.seek(readFrom)
            file.readFully(bytes)
        }
        var result = String(bytes, Charsets.UTF_8)
        if (readFrom > logSessionStartBytes) result = result.substringAfter('\n', "")
        result
    }.getOrDefault("")

    private fun formatSessionLogs(raw: String): String {
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
        return entries.takeLast(200).asReversed().joinToString("\n\n") { entry ->
            entry.joinToString("\n")
        }
    }

    // =========================================================================
    // TOKEN TOGGLE & CLIPBOARD
    // =========================================================================

    private fun toggleTokenVisibility() {
        isTokenVisible = !isTokenVisible
        if (isTokenVisible) {
            tokenInput.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
            tokenShowHideBtn.text = "🙈"
        } else {
            tokenInput.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            tokenShowHideBtn.text = "👁️"
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
                val current = info.optString("current_version", "1.0.0")
                val isUpdated = info.optBoolean("is_updated", false)
                val label = "🐍 Python Engine: v$current ${if (isUpdated) "(Live Release)" else "(Bundled)"}"
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
                        engineVersionText.text = "🐍 Python Engine: Ready"
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
                val resultJson = Python.getInstance().getModule("android_bridge")
                    .callAttr("check_and_apply_update", filesDir.absolutePath, force, 10.0)
                    .toString()
                val result = JSONObject(resultJson)
                val resStatus = result.optString("status", "")
                val version = result.optString("version", "")
                val error = result.optString("error", "")

                when (resStatus) {
                    "updated" -> {
                        badgeText = "● Updated v$version"; badgeColor = UiTheme.ACCENT_GREEN_BRIGHT
                        message = "Updated runtime to v$version! 🌟"
                    }
                    "staged" -> {
                        // Runtime busy: files verified and staged; activation deferred to next start.
                        badgeText = "● Staged v$version"; badgeColor = UiTheme.ACCENT_YELLOW
                        message = "v$version staged — restart the runtime to apply."
                    }
                    "current" -> {
                        badgeText = "● Up to date"; badgeColor = UiTheme.ACCENT_BLUE
                        message = "Runtime is up to date (v$version). ✨"
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
                isUpdateInFlight = false
                loadEngineVersion()
                refreshLogs()
            }
        }.start()
    }

    private fun promptRevertPython() {
        AlertDialog.Builder(this)
            .setTitle("Restore Bundled Version")
            .setMessage("Restore Python runtime to the bundled APK version? Staged update cache will be cleared.")
            .setPositiveButton("Restore") { _, _ -> resetPythonRuntime() }
            .setNegativeButton("Cancel", null)
            .show()
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

    private fun promptBatteryOptimization() {
        val pm = getSystemService(PowerManager::class.java)
        val directlyExemptable = Build.VERSION.SDK_INT >= Build.VERSION_CODES.M &&
            !pm.isIgnoringBatteryOptimizations(packageName)
        AlertDialog.Builder(this)
            .setTitle("Background Execution")
            .setMessage(
                "To keep MudaRemote active when your screen is off or another app is open, " +
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
        val text = readUri(uri) ?: return
        runCatching {
            var root = JSONObject(text)
            if (root.opt("presets") is JSONObject) root = root.getJSONObject("presets")
            val importedNames = mutableListOf<String>()
            root.keys().asSequence().forEach { name ->
                val data = root.getJSONObject(name)
                val embeddedToken = data.optString("token", "").trim()
                if (embeddedToken.isNotBlank()) tokens[name] = embeddedToken
                data.remove("token")
                mergeSchemaDefaults(data)
                profiles[name] = data
                importedNames += name
            }
            if (importedNames.isNotEmpty()) {
                currentProfile = importedNames.first()
                persist()
                refreshProfileTabs()
                renderCurrentProfile()
                toast("Imported ${importedNames.size} branch preset(s)! 🌟")
            }
        }.onFailure { toast("Presets error: ${it.message}") }
    }

    private fun importSecrets(uri: Uri) {
        val text = readUri(uri) ?: return
        runCatching {
            val root = JSONObject(text)
            var imported = 0
            var encrypted = 0
            root.keys().asSequence().forEach { name ->
                val raw = root.optString(name, "").trim()
                val arrayHasDpapi = raw.startsWith("[") && runCatching {
                    val values = JSONArray(raw)
                    (0 until values.length()).any { values.optString(it).startsWith("AQAAANCMnd8BFdER", ignoreCase = true) }
                }.getOrDefault(false)
                if (raw.startsWith("AQAAANCMnd8BFdER", ignoreCase = true) || arrayHasDpapi) {
                    encrypted++
                } else if (raw.isNotBlank()) {
                    tokens[name] = raw
                    imported++
                }
            }
            persist()
            if (encrypted > 0) {
                toast("Imported $imported secret(s). $encrypted Windows DPAPI token(s) need manual re-entry on Android.")
            } else {
                toast("Imported $imported secret(s) to Keystore! 🔒")
            }
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
        schemaFields.keys().asSequence().filter { it != "token" }.forEach { key ->
            data.put(key, schemaFields.optJSONObject(key)?.opt("default") ?: "")
        }
        return data
    }

    private fun mergeSchemaDefaults(data: JSONObject) {
        schemaFields.keys().asSequence().filter { it != "token" }.forEach { key ->
            if (!data.has(key)) data.put(key, schemaFields.optJSONObject(key)?.opt("default") ?: "")
        }
    }

    private fun restore() {
        val storedProfiles = vault.get("profiles")
        if (storedProfiles.isNotBlank()) {
            runCatching {
                val root = JSONObject(storedProfiles)
                root.keys().asSequence().forEach { name -> profiles[name] = root.getJSONObject(name) }
            }
        }
        val storedTokens = vault.get("tokens")
        if (storedTokens.isNotBlank()) runCatching {
            val root = JSONObject(storedTokens)
            root.keys().asSequence().forEach { name -> tokens[name] = root.optString(name) }
        }
        if (profiles.isEmpty()) {
            val legacy = vault.get("profile")
            if (legacy.isNotBlank()) runCatching {
                val data = JSONObject(legacy)
                val name = data.optString("name", "MAIN")
                data.remove("name")
                profiles[name] = data
                vault.get("token").takeIf { it.isNotBlank() }?.let { tokens[name] = it }
            }
        }
        if (profiles.isEmpty()) profiles["MAIN"] = schemaDefaults().put("channel_id", "").put("roll_command", "wa").put("rolling", true)
        profiles.values.forEach { mergeSchemaDefaults(it) }
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
    // GITHUB BUTTON & BADGE HELPERS
    // =========================================================================

    private fun createGitHubButton(text: String, onClick: () -> Unit): TextView = TextView(this).apply {
        this.text = text
        textSize = 11f
        setTypeface(null, Typeface.BOLD)
        setTextColor(UiTheme.TEXT_PRIMARY)
        gravity = Gravity.CENTER
        background = UiTheme.buttonDrawable(this@MainActivity, UiTheme.BG_CARD_LIGHT, radiusDp = 6f, borderColor = UiTheme.BORDER_DEFAULT, strokeWidthDp = 1f)
        minHeight = UiTheme.dp(this@MainActivity, 44)
        setPadding(UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 10), UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 10))
        setOnClickListener { view ->
            view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            onClick()
        }
    }

    private fun createGitHubSmallBtn(text: String, onClick: (TextView) -> Unit): TextView = TextView(this).apply {
        this.text = text
        textSize = 11f
        setTypeface(null, Typeface.BOLD)
        setTextColor(UiTheme.TEXT_PRIMARY)
        gravity = Gravity.CENTER
        minHeight = UiTheme.dp(this@MainActivity, 40)
        background = UiTheme.pressablePillDrawable(this@MainActivity, UiTheme.BG_CARD_LIGHT, UiTheme.BORDER_DEFAULT, 6f, 1f)
        setPadding(UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 8), UiTheme.dp(this@MainActivity, 8))
        val params = LinearLayout.LayoutParams(-2, -2).apply {
            leftMargin = UiTheme.dp(this@MainActivity, 4)
        }
        layoutParams = params
        setOnClickListener { view ->
            view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            @Suppress("UNCHECKED_CAST")
            onClick(view as TextView)
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
        val LOG_ENTRY_START = Regex("^\\[(?:\\d{4}-\\d{2}-\\d{2}|INFO|ERROR|WARN|CHECK|RESET|CLAIM|KAKERA|UPDATER|ANDROID|DEBUG)")
    }
}
