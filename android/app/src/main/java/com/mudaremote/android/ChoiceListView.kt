package com.mudaremote.android

import android.content.Context
import android.graphics.Color
import android.transition.ChangeBounds
import android.transition.TransitionManager
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView

/**
 * One choice field as a collapsible single-select list. Collapsed it is a single row: the field title
 * with the current choice under it, and a chevron at the end. A tap opens the options inline (one row
 * each, the chosen one tinted with a check mark); picking one closes the list again.
 * The stored value is the option's key, exactly as the old radio buttons stored it.
 */
class ChoiceListView(
    context: Context,
    private val title: String,
    private val options: LinkedHashMap<String, String>,
    initial: String?,
    private val onChosen: (String) -> Unit
) : LinearLayout(context) {

    /** The chosen option key, or null when the stored value is not one of the options (it is then left as stored). */
    var selected: String? = initial?.takeIf { options.containsKey(it) }
        private set

    private val storedFallback: String? = initial
    private val currentText: TextView
    private val chevron: TextView
    private val header: LinearLayout
    private val list: LinearLayout
    private var open = false

    init {
        orientation = VERTICAL
        background = UiTheme.cardDrawable(context, UiTheme.SURFACE_CONTAINER_HIGH, Color.TRANSPARENT, UiTheme.SHAPE_LG, 0f)
        tag = "choice_list"

        header = LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            minimumHeight = UiTheme.dp(context, 56)
            background = UiTheme.listItemDrawable(context, Color.TRANSPARENT, UiTheme.SHAPE_LG)
            setPaddingRelative(UiTheme.dp(context, 16), UiTheme.dp(context, 10), UiTheme.dp(context, 8), UiTheme.dp(context, 10))
            isClickable = true
            isFocusable = true
        }
        val texts = LinearLayout(context).apply { orientation = VERTICAL }
        texts.addView(TextView(context).apply {
            text = title
            UiTheme.styleLabel(this)
            maxLines = Int.MAX_VALUE
        })
        currentText = TextView(context).apply {
            textSize = UiTheme.TYPE_BODY
            setTextColor(UiTheme.PRIMARY)
            setPaddingRelative(0, UiTheme.dp(context, 2), 0, 0)
        }
        texts.addView(currentText)
        header.addView(texts, LayoutParams(0, -2, 1f))
        chevron = TextView(context).apply {
            textSize = 14f
            setTextColor(UiTheme.ON_SURFACE_VARIANT)
            gravity = Gravity.CENTER
            minWidth = UiTheme.dp(context, 40)
            minHeight = UiTheme.dp(context, 48)
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }
        header.addView(chevron)
        header.setOnClickListener { setOpen(!open, animate = true) }
        addView(header, LayoutParams(-1, -2))

        list = LinearLayout(context).apply {
            orientation = VERTICAL
            visibility = View.GONE
            setPaddingRelative(UiTheme.dp(context, 8), 0, UiTheme.dp(context, 8), UiTheme.dp(context, 8))
        }
        addView(list, LayoutParams(-1, -2))
        rebuildOptions()
        refreshHeader()
    }

    private fun rebuildOptions() {
        list.removeAllViews()
        options.forEach { (key, label) ->
            val chosen = key == selected
            val row = LinearLayout(context).apply {
                orientation = HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                minimumHeight = UiTheme.dp(context, 48)
                background = UiTheme.listItemDrawable(
                    context, if (chosen) UiTheme.SECONDARY_CONTAINER else Color.TRANSPARENT, UiTheme.SHAPE_MD
                )
                setPaddingRelative(UiTheme.dp(context, 12), UiTheme.dp(context, 8), UiTheme.dp(context, 8), UiTheme.dp(context, 8))
                isClickable = true
                isFocusable = true
                tag = "choice_option_$key"
                contentDescription = label + if (chosen) ", selected" else ""
            }
            row.addView(TextView(context).apply {
                text = label
                textSize = UiTheme.TYPE_BODY
                setTextColor(if (chosen) UiTheme.ON_SECONDARY_CONTAINER else UiTheme.TEXT_PRIMARY)
                if (chosen) typeface = UiTheme.MEDIUM
                maxLines = Int.MAX_VALUE
                ellipsize = null
            }, LayoutParams(0, -2, 1f))
            row.addView(TextView(context).apply {
                text = if (chosen) "✓" else ""
                textSize = 16f
                setTextColor(UiTheme.ON_SECONDARY_CONTAINER)
                gravity = Gravity.CENTER
                minWidth = UiTheme.dp(context, 32)
                importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
            })
            row.setOnClickListener { choose(key) }
            list.addView(row, LayoutParams(-1, -2).apply { topMargin = UiTheme.dp(context, 4) })
        }
    }

    private fun choose(key: String) {
        val changed = key != selected
        selected = key
        rebuildOptions()
        refreshHeader()
        setOpen(false, animate = true)
        if (changed) onChosen(key)
    }

    private fun setOpen(value: Boolean, animate: Boolean) {
        if (animate) {
            TransitionManager.beginDelayedTransition(
                this, ChangeBounds().setDuration(180).setInterpolator(android.view.animation.DecelerateInterpolator())
            )
        }
        open = value
        list.visibility = if (open) View.VISIBLE else View.GONE
        refreshHeader()
    }

    private fun refreshHeader() {
        val label = selected?.let { options[it] } ?: storedFallback?.takeIf { it.isNotEmpty() } ?: "Not chosen"
        currentText.text = label
        chevron.text = if (open) "▲" else "▼"
        header.contentDescription = "$title, $label, " + if (open) "expanded" else "collapsed"
    }
}
