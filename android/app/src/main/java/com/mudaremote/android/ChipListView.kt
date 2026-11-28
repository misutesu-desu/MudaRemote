package com.mudaremote.android

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.text.TextUtils
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONArray

/**
 * Interactive list and tag editor: M3 input chips, an «Add» field and a raw-JSON mode.
 */
class ChipListView(
    context: Context,
    private val key: String,
    initialData: JSONArray?,
    private val onListChanged: (JSONArray) -> Unit
) : LinearLayout(context) {

    // LinkedHashSet keeps insertion order while making add/dedupe O(1)
    // (wishlists can contain hundreds of entries).
    private val items = LinkedHashSet<String>()
    private val chipsContainer: FlowLayout
    private val jsonEditText: EditText
    private val addItemInput: EditText
    private val modeToggleButton: TextView
    private val countBadge: TextView
    private val isSensitive = key == "tokens"
    private var isJsonMode = false
    private var isUpdatingInternal = false

    init {
        orientation = VERTICAL
        setPaddingRelative(UiTheme.dp(context, 12), UiTheme.dp(context, 10), UiTheme.dp(context, 12), UiTheme.dp(context, 12))
        background = UiTheme.insetSurface(context)

        // Parse initial data
        initialData?.let { array ->
            for (i in 0 until array.length()) {
                val str = array.optString(i, "").trim()
                if (str.isNotBlank()) items.add(str)
            }
        }
        // Header Row: Count badge + Mode toggle (Tags vs JSON)
        val headerRow = LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, 0, 0, UiTheme.dp(context, 6))
        }

        countBadge = TextView(context).apply {
            text = "${items.size} item(s)"
            textSize = UiTheme.TYPE_LABEL
            setTextColor(UiTheme.TEXT_MUTED)
        }
        headerRow.addView(countBadge, LayoutParams(0, -2, 1f))

        modeToggleButton = TextView(context).apply {
            text = "Raw JSON"
            UiTheme.styleButton(this, UiTheme.ButtonStyle.TEXT, compact = true)
            setOnClickListener { toggleMode() }
            visibility = if (isSensitive) GONE else VISIBLE
        }
        headerRow.addView(modeToggleButton)
        addView(headerRow)

        // Visual Chips Container
        chipsContainer = FlowLayout(context).apply {
            setPadding(0, UiTheme.dp(context, 4), 0, UiTheme.dp(context, 6))
        }
        addView(chipsContainer)

        // Add Item Input Row (Visual Mode)
        val addRow = LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, UiTheme.dp(context, 4), 0, 0)
        }

        addItemInput = EditText(context).apply {
            hint = if (isSensitive) "Paste alt tokens" else "Add item (e.g. wa, 102938...)"
            textSize = UiTheme.TYPE_BODY
            setTextColor(UiTheme.TEXT_PRIMARY)
            setHintTextColor(UiTheme.TEXT_MUTED)
            background = UiTheme.inputDrawable(context, radiusDp = UiTheme.SHAPE_FULL)
            minHeight = UiTheme.dp(context, 48)
            setPaddingRelative(UiTheme.dp(context, 16), UiTheme.dp(context, 10), UiTheme.dp(context, 16), UiTheme.dp(context, 10))
            inputType = InputType.TYPE_CLASS_TEXT or if (isSensitive) {
                InputType.TYPE_TEXT_VARIATION_PASSWORD or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            } else {
                InputType.TYPE_TEXT_VARIATION_NORMAL
            }
            if (isSensitive) {
                importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
            }
            contentDescription = if (isSensitive) "Add account token" else "Add list item"
            setOnEditorActionListener { _, _, _ ->
                addItemFromInput()
                true
            }
        }
        addRow.addView(addItemInput, LayoutParams(0, -2, 1f))

        val addButton = TextView(context).apply {
            text = "Add"
            UiTheme.styleButton(this, UiTheme.ButtonStyle.FILLED, compact = true)
            minHeight = UiTheme.dp(context, 48)
            setOnClickListener { addItemFromInput() }
        }
        val addBtnParams = LayoutParams(-2, -2).apply {
            marginStart = UiTheme.dp(context, 8)
        }
        addRow.addView(addButton, addBtnParams)
        addView(addRow)

        // Raw JSON Editor
        jsonEditText = EditText(context).apply {
            textSize = 12.5f
            typeface = Typeface.MONOSPACE
            setTextColor(UiTheme.TEXT_PRIMARY)
            setHintTextColor(UiTheme.TEXT_MUTED)
            background = UiTheme.inputDrawable(context)
            setPaddingRelative(UiTheme.dp(context, 14), UiTheme.dp(context, 12), UiTheme.dp(context, 14), UiTheme.dp(context, 12))
            minLines = 3
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
            visibility = GONE
            addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit
                override fun afterTextChanged(s: Editable?) {
                    if (isUpdatingInternal || !isJsonMode) return
                    val text = s?.toString()?.trim().orEmpty()
                    runCatching {
                        val array = JSONArray(text)
                        items.clear()
                        for (i in 0 until array.length()) {
                            val v = array.optString(i, "").trim()
                            if (v.isNotBlank()) items.add(v)
                        }
                        renderChips()
                        onListChanged(toJsonArray())
                    }
                }
            })
        }
        addView(jsonEditText)

        renderChips()
    }

    fun getJsonArray(): JSONArray = toJsonArray()

    fun setJsonArray(array: JSONArray?) {
        items.clear()
        array?.let {
            for (i in 0 until it.length()) {
                val str = it.optString(i, "").trim()
                if (str.isNotBlank()) items.add(str)
            }
        }
        renderChips()
        if (isJsonMode) {
            isUpdatingInternal = true
            jsonEditText.setText(toJsonArray().toString(2))
            isUpdatingInternal = false
        }
    }

    private fun toJsonArray(): JSONArray {
        val array = JSONArray()
        items.forEach { array.put(it) }
        return array
    }

    private fun addItemFromInput() {
        val raw = addItemInput.text?.toString()?.trim().orEmpty()
        if (raw.isBlank()) return
        val splitItems = raw.split(',', '\n').map { it.trim().trim('"', '\'') }.filter { it.isNotBlank() }
        val wasEmpty = items.isEmpty()
        val added = mutableListOf<String>()
        for (item in splitItems) {
            if (!items.contains(item)) {
                items.add(item)
                added.add(item)
            }
        }
        addItemInput.setText("")
        if (wasEmpty) {
            renderChips()
        } else {
            // Only the new chips are added; the existing ones stay as they are.
            added.forEach { chipsContainer.addView(createChip(it)) }
            countBadge.text = "${items.size} item(s)"
        }
        onListChanged(toJsonArray())
    }

    private fun removeItem(item: String) {
        items.remove(item)
        val chip = chipsContainer.findViewWithTag<View>(chipTag(item))
        if (items.isEmpty() || chip == null) {
            renderChips()
        } else {
            chipsContainer.removeView(chip)  // only this chip goes; no rebuild of the list
            countBadge.text = "${items.size} item(s)"
        }
        onListChanged(toJsonArray())
    }

    private fun chipTag(item: String): String = "chip:$item"

    private fun renderChips() {
        chipsContainer.removeAllViews()
        countBadge.text = "${items.size} item(s)"

        if (items.isEmpty()) {
            val emptyNotice = TextView(context).apply {
                text = "No items. Type a value and tap Add."
                textSize = UiTheme.TYPE_SUPPORTING
                setTextColor(UiTheme.TEXT_MUTED)
                setPaddingRelative(UiTheme.dp(context, 4), UiTheme.dp(context, 4), 0, UiTheme.dp(context, 4))
            }
            chipsContainer.addView(emptyNotice)
        } else {
            items.forEach { item ->
                chipsContainer.addView(createChip(item))
            }
        }

        // The raw-JSON editor is filled when it is opened (toggleMode), not on every change:
        // pretty-printing a long list into a hidden field on each add/remove was wasted work, and
        // rewriting it while the user typed in it moved the cursor.
    }

    private fun createChip(item: String): View {
        val chip = LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = UiTheme.pillDrawable(context, UiTheme.SECONDARY_CONTAINER, Color.TRANSPARENT, UiTheme.SHAPE_SM, 0f)
            setPaddingRelative(UiTheme.dp(context, 12), 0, 0, 0)
            tag = chipTag(item)
        }

        val label = TextView(context).apply {
            text = if (isSensitive) maskedTokenLabel(item) else item
            textSize = 13f
            setTextColor(UiTheme.ON_SECONDARY_CONTAINER)
            maxWidth = UiTheme.dp(context, if (isSensitive) 180 else 260)
            maxLines = 1
            ellipsize = TextUtils.TruncateAt.END
            contentDescription = if (isSensitive) maskedTokenDescription(item) else item
        }
        chip.addView(label)

        val closeBtn = TextView(context).apply {
            text = if (isSensitive) "Remove" else " ✕"
            textSize = 12f
            setTypeface(null, Typeface.BOLD)
            setTextColor(if (isSensitive) UiTheme.ERROR else UiTheme.ON_SECONDARY_CONTAINER)
            background = UiTheme.listItemDrawable(context, radiusDp = UiTheme.SHAPE_SM)
            gravity = Gravity.CENTER
            minHeight = UiTheme.dp(context, 48)
            minWidth = UiTheme.dp(context, if (isSensitive) 72 else 48)
            setPadding(UiTheme.dp(context, 8), 0, UiTheme.dp(context, 8), 0)
            contentDescription = if (isSensitive) "Remove ${maskedTokenDescription(item)}" else "Remove $item"
            setOnClickListener { removeItem(item) }
        }
        chip.addView(closeBtn)

        return chip
    }

    private fun maskedTokenLabel(item: String): String {
        if (item.length < 8) return "Account token (masked)"
        return "Account token ****${item.takeLast(4)}"
    }

    private fun maskedTokenDescription(item: String): String {
        if (item.length < 8) return "masked account token"
        return "account token ending in ${item.takeLast(4)}"
    }

    private fun toggleMode() {
        isJsonMode = !isJsonMode
        if (isJsonMode) {
            modeToggleButton.text = "Chips view"
            chipsContainer.visibility = GONE
            addItemInput.parent?.let { (it as View).visibility = GONE }
            jsonEditText.visibility = VISIBLE
            isUpdatingInternal = true
            jsonEditText.setText(toJsonArray().toString(2))
            isUpdatingInternal = false
        } else {
            modeToggleButton.text = "Raw JSON"
            chipsContainer.visibility = VISIBLE
            addItemInput.parent?.let { (it as View).visibility = VISIBLE }
            jsonEditText.visibility = GONE
            renderChips()
        }
    }
}
