package com.mudaremote.android

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.graphics.drawable.StateListDrawable
import android.text.Spannable
import android.text.SpannableStringBuilder
import android.text.style.ForegroundColorSpan
import android.text.style.StyleSpan

/**
 * GitHub Primer Dark design system tokens and UI helper utilities for MudaRemote.
 */
object UiTheme {
    // GitHub Dark Canvas / Surfaces
    val BG_APP = Color.parseColor("#0d1117")          // canvas.default
    val BG_SURFACE = Color.parseColor("#161b22")      // canvas.subtle / Box header
    val BG_CARD = Color.parseColor("#161b22")         // Box container
    val BG_CARD_LIGHT = Color.parseColor("#21262d")   // button.default.bg
    val BG_INPUT = Color.parseColor("#010409")        // canvas.inset
    val BG_TERMINAL = Color.parseColor("#010409")     // GitHub Actions runner dark bg

    // GitHub Borders
    val BORDER_SUBTLE = Color.parseColor("#21262d")   // border.subtle
    val BORDER_DEFAULT = Color.parseColor("#30363d")  // border.default
    val BORDER_LIGHT = Color.parseColor("#3d444d")    // border.muted
    val BORDER_FOCUS = Color.parseColor("#58a6ff")    // accent.fg

    // GitHub Accents
    val ACCENT_BLUE = Color.parseColor("#58a6ff")     // accent.fg / links
    val ACCENT_GREEN = Color.parseColor("#238636")    // btn.primary.bg
    val ACCENT_GREEN_BRIGHT = Color.parseColor("#3fb950") // success.fg / open PR
    val ACCENT_RED = Color.parseColor("#da3633")      // btn.danger.bg
    val ACCENT_RED_BRIGHT = Color.parseColor("#f85149")   // danger.fg / closed
    val ACCENT_YELLOW = Color.parseColor("#d29922")   // attention.fg
    val ACCENT_PURPLE = Color.parseColor("#8957e5")   // done.fg / merged
    val ACCENT_PINK = Color.parseColor("#f778ba")     // sponsor / claim pink
    val ACCENT_CYAN = Color.parseColor("#38bdf8")     // info / crystal cyan
    val ACCENT_ORANGE = Color.parseColor("#f0883e")   // severe / open draft

    // GitHub Text Colors
    val TEXT_PRIMARY = Color.parseColor("#e6edf3")    // fg.default
    val TEXT_SECONDARY = Color.parseColor("#8d96a0")  // fg.muted
    val TEXT_MUTED = Color.parseColor("#6e7681")      // fg.subtle
    val TEXT_WHITE = Color.parseColor("#ffffff")

    // Label / Pill backgrounds (translucent tags)
    val LABEL_BLUE_BG = Color.parseColor("#1f293d")
    val LABEL_GREEN_BG = Color.parseColor("#1a2e22")
    val LABEL_RED_BG = Color.parseColor("#331c20")
    val LABEL_PURPLE_BG = Color.parseColor("#291f3d")

    fun dp(context: Context, value: Int): Int {
        return (value * context.resources.displayMetrics.density).toInt()
    }

    fun dp(context: Context, value: Float): Int {
        return (value * context.resources.displayMetrics.density).toInt()
    }

    fun cardDrawable(
        context: Context,
        bgColor: Int = BG_CARD,
        borderColor: Int = BORDER_DEFAULT,
        radiusDp: Float = 8f,
        strokeWidthDp: Float = 1f
    ): GradientDrawable {
        return GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = dp(context, radiusDp).toFloat()
            setColor(bgColor)
            if (strokeWidthDp > 0) {
                setStroke(dp(context, strokeWidthDp), borderColor)
            }
        }
    }

    fun pillDrawable(
        context: Context,
        bgColor: Int,
        borderColor: Int = BORDER_DEFAULT,
        radiusDp: Float = 20f,
        strokeWidthDp: Float = 1f
    ): GradientDrawable {
        return cardDrawable(context, bgColor, borderColor, radiusDp, strokeWidthDp)
    }

    /** Pressable pill with ripple feedback for tags, tabs and small actions. */
    fun pressablePillDrawable(
        context: Context,
        bgColor: Int,
        borderColor: Int = BORDER_DEFAULT,
        radiusDp: Float = 12f,
        strokeWidthDp: Float = 1f
    ): Drawable {
        val normal = cardDrawable(context, bgColor, borderColor, radiusDp, strokeWidthDp)
        val mask = cardDrawable(context, Color.WHITE, Color.TRANSPARENT, radiusDp, 0f)
        return RippleDrawable(ColorStateList.valueOf(Color.parseColor("#33FFFFFF")), normal, mask)
    }

    fun buttonDrawable(
        context: Context,
        bgColor: Int,
        rippleColor: Int = Color.parseColor("#33FFFFFF"),
        radiusDp: Float = 6f,
        borderColor: Int = BORDER_DEFAULT,
        strokeWidthDp: Float = 1f
    ): Drawable {
        val normal = cardDrawable(context, bgColor, borderColor, radiusDp, strokeWidthDp)
        val mask = cardDrawable(context, Color.WHITE, Color.TRANSPARENT, radiusDp, 0f)
        return RippleDrawable(ColorStateList.valueOf(rippleColor), normal, mask)
    }

    fun inputDrawable(
        context: Context,
        bgColor: Int = BG_INPUT,
        borderColor: Int = BORDER_DEFAULT,
        radiusDp: Float = 6f
    ): StateListDrawable {
        val normal = cardDrawable(context, bgColor, borderColor, radiusDp, 1f)
        val focused = cardDrawable(context, bgColor, BORDER_FOCUS, radiusDp, 1.5f)
        return StateListDrawable().apply {
            addState(intArrayOf(android.R.attr.state_focused), focused)
            addState(intArrayOf(), normal)
        }
    }

    // --- Log highlighting (regexes precompiled once; refreshLogs runs at 1 Hz on large text) ---
    private val LOG_RULES: List<Pair<Regex, Int>> = listOf(
        Regex("(?i)\\[CLAIM[^\\]]*\\]|💖|💞") to ACCENT_PINK,
        Regex("(?i)\\[KAKERA[^\\]]*\\]|💎|🔷|🟩|🟨|🟧|🟥") to ACCENT_CYAN,
        Regex("(?i)\\[SPHERE[^\\]]*\\]|✨|🔮") to ACCENT_PURPLE,
        Regex("(?i)\\[INFO[^\\]]*\\]|ℹ️") to ACCENT_BLUE,
        Regex("(?i)\\[WARN(?:ING)?[^\\]]*\\]|⚠️") to ACCENT_YELLOW,
        Regex("(?i)\\[ERROR[^\\]]*\\]|❌|⛔|failed") to ACCENT_RED_BRIGHT,
        Regex("(?i)\\[UPDATER[^\\]]*\\]|🚀|🌟") to ACCENT_GREEN_BRIGHT,
        Regex("(?i)\\[CHECK[^\\]]*\\]|🔍") to Color.parseColor("#a5d6ff"),
        Regex("(?i)\\[RESET[^\\]]*\\]|⏰") to ACCENT_YELLOW,
        Regex("(?i)\\[(START|RUNNING|ONLINE)[^\\]]*\\]") to ACCENT_GREEN_BRIGHT,
    )

    fun highlightLogs(rawLogs: String): CharSequence {
        if (rawLogs.isBlank()) return rawLogs
        val builder = SpannableStringBuilder(rawLogs)

        for ((pattern, color) in LOG_RULES) {
            pattern.findAll(rawLogs).forEach { match ->
                val start = match.range.first
                val end = match.range.last + 1
                builder.setSpan(ForegroundColorSpan(color), start, end, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE)
                builder.setSpan(StyleSpan(Typeface.BOLD), start, end, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE)
            }
        }
        return builder
    }
}
