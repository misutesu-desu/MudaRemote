package com.mudaremote.android

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.InsetDrawable
import android.graphics.drawable.RippleDrawable
import android.graphics.drawable.StateListDrawable
import android.text.Spannable
import android.text.SpannableStringBuilder
import android.text.TextUtils
import android.text.style.ForegroundColorSpan
import android.text.style.StyleSpan
import android.view.Gravity
import android.widget.Switch
import android.widget.TextView

/**
 * MudaFork's dark Material 3 Expressive theme: colour roles, shape scale, type scale and the
 * shared builders (cards, buttons, chips, fields, switches) every screen uses.
 *
 * The colour roles are the dark scheme of the owner's reader app (neutral dark surfaces with
 * the aqua accent). No yellow, amber, gold or orange is used anywhere: «warning» is tertiary.
 */
object UiTheme {
    // ------------------------------------------------------------------ colour roles (dark)
    val SURFACE = Color.parseColor("#121314")
    val SURFACE_CONTAINER_LOWEST = Color.parseColor("#0c0d0e")
    val SURFACE_CONTAINER_LOW = Color.parseColor("#1a1b1d")
    val SURFACE_CONTAINER = Color.parseColor("#1e2022")
    val SURFACE_CONTAINER_HIGH = Color.parseColor("#282a2d")
    val SURFACE_CONTAINER_HIGHEST = Color.parseColor("#323437")
    val ON_SURFACE = Color.parseColor("#e4e4e6")
    val ON_SURFACE_VARIANT = Color.parseColor("#c6c8cc")
    val ON_SURFACE_DIM = Color.parseColor("#9a9ca1")
    val OUTLINE = Color.parseColor("#8e9196")
    val OUTLINE_VARIANT = Color.parseColor("#44474c")
    val INVERSE_SURFACE = Color.parseColor("#e4e4e6")
    val INVERSE_ON_SURFACE = Color.parseColor("#2e3033")

    val PRIMARY = Color.parseColor("#8fd0f0")
    val ON_PRIMARY = Color.parseColor("#003546")
    val PRIMARY_CONTAINER = Color.parseColor("#1f4b5e")
    val ON_PRIMARY_CONTAINER = Color.parseColor("#c8ecff")
    val SECONDARY = Color.parseColor("#b4cad6")
    val ON_SECONDARY = Color.parseColor("#1f333c")
    val SECONDARY_CONTAINER = Color.parseColor("#2c3f49")
    val ON_SECONDARY_CONTAINER = Color.parseColor("#d2e6ef")
    val TERTIARY = Color.parseColor("#a6d3c4")
    val ON_TERTIARY = Color.parseColor("#0c372e")
    val TERTIARY_CONTAINER = Color.parseColor("#2f4a3a")
    val ON_TERTIARY_CONTAINER = Color.parseColor("#c7f0d7")
    val ERROR = Color.parseColor("#ffb4ab")
    val ON_ERROR = Color.parseColor("#690005")
    val ERROR_CONTAINER = Color.parseColor("#93000a")
    val ON_ERROR_CONTAINER = Color.parseColor("#ffdad6")

    // Extra hues for log kinds only (from the same reference's accent presets).
    val LOG_ROSE = Color.parseColor("#f3b3c6")
    val LOG_VIOLET = Color.parseColor("#cdbdff")

    // ------------------------------------------------------------------ shape scale (dp)
    const val SHAPE_XS = 6f
    const val SHAPE_SM = 10f
    const val SHAPE_MD = 14f
    const val SHAPE_LG = 18f
    const val SHAPE_XL = 28f
    const val SHAPE_FULL = 999f

    // ------------------------------------------------------------------ type scale (sp)
    const val TYPE_TITLE_LARGE = 22f
    const val TYPE_TITLE = 16f
    const val TYPE_SECTION = 14f
    const val TYPE_BODY = 14f
    const val TYPE_SUPPORTING = 12.5f
    const val TYPE_LABEL = 12f

    /** Medium weight for titles, labels and buttons. */
    val MEDIUM: Typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)

    // ------------------------------------------------------------------ legacy names
    // Older call sites use these names; they now point at the roles above.
    val BG_APP = SURFACE
    val BG_SURFACE = SURFACE_CONTAINER_HIGH
    val BG_CARD = SURFACE_CONTAINER_LOW
    val BG_CARD_LIGHT = SURFACE_CONTAINER_HIGH
    val BG_INPUT = SURFACE_CONTAINER_HIGH
    val BG_TERMINAL = SURFACE_CONTAINER_LOWEST

    val BORDER_SUBTLE = OUTLINE_VARIANT
    val BORDER_DEFAULT = OUTLINE_VARIANT
    val BORDER_LIGHT = OUTLINE
    val BORDER_FOCUS = PRIMARY

    val ACCENT_BLUE = PRIMARY                 // links, selection, info
    val ACCENT_GREEN = PRIMARY                // primary actions
    val ACCENT_GREEN_BRIGHT = PRIMARY         // success / running
    val ACCENT_RED = ERROR
    val ACCENT_RED_BRIGHT = ERROR
    val ACCENT_YELLOW = TERTIARY              // warning / in progress (never amber)
    val ACCENT_PURPLE = LOG_VIOLET
    val ACCENT_PINK = LOG_ROSE
    val ACCENT_CYAN = PRIMARY
    val ACCENT_ORANGE = TERTIARY

    val TEXT_PRIMARY = ON_SURFACE
    val TEXT_SECONDARY = ON_SURFACE_VARIANT
    val TEXT_MUTED = ON_SURFACE_DIM
    val TEXT_WHITE = Color.parseColor("#ffffff")

    val LABEL_BLUE_BG = PRIMARY_CONTAINER
    val LABEL_GREEN_BG = TERTIARY_CONTAINER
    val LABEL_RED_BG = withAlpha(ERROR, 0x29)
    val LABEL_PURPLE_BG = SECONDARY_CONTAINER

    fun withAlpha(color: Int, alpha: Int): Int =
        Color.argb(alpha, Color.red(color), Color.green(color), Color.blue(color))

    fun dp(context: Context, value: Int): Int {
        return (value * context.resources.displayMetrics.density).toInt()
    }

    fun dp(context: Context, value: Float): Int {
        return (value * context.resources.displayMetrics.density).toInt()
    }

    // ------------------------------------------------------------------ plain shapes

    fun cardDrawable(
        context: Context,
        bgColor: Int = BG_CARD,
        borderColor: Int = BORDER_DEFAULT,
        radiusDp: Float = SHAPE_XL,
        strokeWidthDp: Float = 0f
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

    /** A large rounded card on the app background (no outline, M3 filled card). */
    fun surfaceCard(context: Context): GradientDrawable =
        cardDrawable(context, SURFACE_CONTAINER_LOW, Color.TRANSPARENT, SHAPE_XL, 0f)

    /** A row inside a card (switch rows, status rows). */
    fun rowSurface(context: Context): GradientDrawable =
        cardDrawable(context, SURFACE_CONTAINER_HIGH, Color.TRANSPARENT, SHAPE_LG, 0f)

    /** A darker inset area inside a card (log, release notes, list editors). */
    fun insetSurface(context: Context): GradientDrawable =
        cardDrawable(context, SURFACE_CONTAINER_LOWEST, Color.TRANSPARENT, SHAPE_LG, 0f)

    fun pillDrawable(
        context: Context,
        bgColor: Int,
        borderColor: Int = BORDER_DEFAULT,
        radiusDp: Float = SHAPE_FULL,
        strokeWidthDp: Float = 0f
    ): GradientDrawable {
        return cardDrawable(context, bgColor, borderColor, radiusDp, strokeWidthDp)
    }

    /** Pressable shape with ripple (tags, tabs, small actions). */
    fun pressablePillDrawable(
        context: Context,
        bgColor: Int,
        borderColor: Int = BORDER_DEFAULT,
        radiusDp: Float = SHAPE_FULL,
        strokeWidthDp: Float = 0f
    ): Drawable {
        val normal = cardDrawable(context, bgColor, borderColor, radiusDp, strokeWidthDp)
        val mask = cardDrawable(context, Color.WHITE, Color.TRANSPARENT, radiusDp, 0f)
        return RippleDrawable(ColorStateList.valueOf(withAlpha(ON_SURFACE, 0x29)), normal, mask)
    }

    fun buttonDrawable(
        context: Context,
        bgColor: Int,
        rippleColor: Int = withAlpha(ON_SURFACE, 0x29),
        radiusDp: Float = SHAPE_FULL,
        borderColor: Int = BORDER_DEFAULT,
        strokeWidthDp: Float = 0f
    ): Drawable {
        val normal = cardDrawable(context, bgColor, borderColor, radiusDp, strokeWidthDp)
        val mask = cardDrawable(context, Color.WHITE, Color.TRANSPARENT, radiusDp, 0f)
        return RippleDrawable(ColorStateList.valueOf(rippleColor), normal, mask)
    }

    /** Transparent, rounded, pressable area for whole rows (section headers, switch rows). */
    fun listItemDrawable(context: Context, bgColor: Int = Color.TRANSPARENT, radiusDp: Float = SHAPE_LG): Drawable {
        val normal = cardDrawable(context, bgColor, Color.TRANSPARENT, radiusDp, 0f)
        val mask = cardDrawable(context, Color.WHITE, Color.TRANSPARENT, radiusDp, 0f)
        return RippleDrawable(ColorStateList.valueOf(withAlpha(ON_SURFACE, 0x1f)), normal, mask)
    }

    /**
     * Filled text field: container-high fill, no outline at rest, a 2dp primary ring when focused.
     * [borderColor] is kept for older call sites; the filled style has no resting outline.
     */
    fun inputDrawable(
        context: Context,
        bgColor: Int = SURFACE_CONTAINER_HIGH,
        @Suppress("UNUSED_PARAMETER") borderColor: Int = BORDER_DEFAULT,
        radiusDp: Float = SHAPE_LG
    ): StateListDrawable {
        val normal = cardDrawable(context, bgColor, Color.TRANSPARENT, radiusDp, 0f)
        val focused = cardDrawable(context, bgColor, PRIMARY, radiusDp, 2f)
        return StateListDrawable().apply {
            setEnterFadeDuration(120)
            setExitFadeDuration(120)
            addState(intArrayOf(android.R.attr.state_focused), focused)
            addState(intArrayOf(), normal)
        }
    }

    // ------------------------------------------------------------------ buttons

    enum class ButtonStyle { FILLED, TONAL, OUTLINED, TEXT, DANGER }

    /**
     * M3 Expressive button background: a pill at rest that morphs to a rounded square while pressed,
     * with a ripple on top.
     */
    fun expressiveButtonDrawable(context: Context, fill: Int, stroke: Int, rippleColor: Int): Drawable {
        val strokeDp = if (stroke != Color.TRANSPARENT) 1f else 0f
        fun shape(radius: Float, color: Int, strokeColor: Int, width: Float) =
            cardDrawable(context, color, strokeColor, radius, width)
        val content = StateListDrawable().apply {
            setEnterFadeDuration(110)
            setExitFadeDuration(220)
            addState(intArrayOf(-android.R.attr.state_enabled), shape(SHAPE_FULL, withAlpha(ON_SURFACE, if (fill == Color.TRANSPARENT) 0 else 0x1f), withAlpha(ON_SURFACE, if (strokeDp > 0f) 0x1f else 0), strokeDp))
            addState(intArrayOf(android.R.attr.state_pressed), shape(SHAPE_MD, fill, stroke, strokeDp))
            addState(intArrayOf(), shape(SHAPE_FULL, fill, stroke, strokeDp))
        }
        val mask = StateListDrawable().apply {
            addState(intArrayOf(android.R.attr.state_pressed), shape(SHAPE_MD, Color.WHITE, Color.TRANSPARENT, 0f))
            addState(intArrayOf(), shape(SHAPE_FULL, Color.WHITE, Color.TRANSPARENT, 0f))
        }
        return RippleDrawable(ColorStateList.valueOf(rippleColor), content, mask)
    }

    /**
     * Styles any TextView as an M3 button: pill shape with pressed morph, label-large type,
     * at least a 48dp touch target, two lines at most with an ellipsis instead of overflow.
     */
    fun styleButton(view: TextView, style: ButtonStyle, compact: Boolean = false) {
        val c = view.context
        val (fill, stroke, textColor) = when (style) {
            ButtonStyle.FILLED -> Triple(PRIMARY, Color.TRANSPARENT, ON_PRIMARY)
            ButtonStyle.TONAL -> Triple(SECONDARY_CONTAINER, Color.TRANSPARENT, ON_SECONDARY_CONTAINER)
            ButtonStyle.OUTLINED -> Triple(Color.TRANSPARENT, OUTLINE_VARIANT, ON_SURFACE)
            ButtonStyle.TEXT -> Triple(Color.TRANSPARENT, Color.TRANSPARENT, PRIMARY)
            ButtonStyle.DANGER -> Triple(Color.TRANSPARENT, ERROR, ERROR)
        }
        view.background = expressiveButtonDrawable(c, fill, stroke, withAlpha(textColor, 0x29))
        view.setTextColor(
            ColorStateList(
                arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf()),
                intArrayOf(withAlpha(ON_SURFACE, 0x61), textColor)
            )
        )
        view.typeface = MEDIUM
        view.textSize = if (compact) 13f else 14f
        view.setAllCaps(false)
        view.gravity = Gravity.CENTER
        view.maxLines = 2
        view.ellipsize = TextUtils.TruncateAt.END
        view.minHeight = dp(c, 48)
        view.minimumHeight = dp(c, 48)
        val h = dp(c, if (compact) 16 else 24)
        val v = dp(c, if (compact) 8 else 10)
        view.setPaddingRelative(h, v, h, v)
        view.isClickable = true
        view.isFocusable = true
    }

    // ------------------------------------------------------------------ chips

    /** Filter chip: rounded at rest, a full pill in the secondary container when selected. */
    fun styleChip(view: TextView, selected: Boolean) {
        val c = view.context
        view.background = if (selected) {
            pressablePillDrawable(c, SECONDARY_CONTAINER, Color.TRANSPARENT, SHAPE_FULL, 0f)
        } else {
            pressablePillDrawable(c, SURFACE_CONTAINER_HIGH, Color.TRANSPARENT, SHAPE_SM, 0f)
        }
        view.setTextColor(if (selected) ON_SECONDARY_CONTAINER else ON_SURFACE_VARIANT)
        view.typeface = if (selected) Typeface.create("sans-serif-medium", Typeface.BOLD) else MEDIUM
        view.textSize = 13f
        view.setAllCaps(false)
        view.gravity = Gravity.CENTER
        view.maxLines = 1
        view.ellipsize = TextUtils.TruncateAt.END
        view.minHeight = dp(c, 48)
        view.minimumHeight = dp(c, 48)
        view.setPaddingRelative(dp(c, 16), dp(c, 6), dp(c, 16), dp(c, 6))
    }

    // ------------------------------------------------------------------ switches

    private fun switchThumbState(context: Context, diameterDp: Int, color: Int): Drawable {
        val size = dp(context, diameterDp)
        val oval = GradientDrawable().apply {
            shape = GradientDrawable.OVAL
            setColor(color)
            setSize(size, size)
        }
        val insetH = (dp(context, 28) - size) / 2
        val insetV = (dp(context, 32) - size) / 2
        return InsetDrawable(oval, insetH, insetV, insetH, insetV)
    }

    private fun switchTrackState(context: Context, fill: Int, stroke: Int): Drawable =
        GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = dp(context, 16).toFloat()
            setColor(fill)
            if (stroke != Color.TRANSPARENT) setStroke(dp(context, 2), stroke)
            setSize(dp(context, 56), dp(context, 32))
        }

    /**
     * M3 switch on the framework Switch: a 32dp-tall track, a small outlined handle when off and a
     * large on-primary handle when on (bigger again while pressed). Clears any old tint lists.
     */
    fun styleSwitch(sw: Switch) {
        val c = sw.context
        val enabled = android.R.attr.state_enabled
        val checked = android.R.attr.state_checked
        val pressed = android.R.attr.state_pressed
        sw.thumbTintList = null
        sw.trackTintList = null
        sw.thumbDrawable = StateListDrawable().apply {
            setEnterFadeDuration(90)
            setExitFadeDuration(90)
            addState(intArrayOf(-enabled, checked), switchThumbState(c, 24, withAlpha(SURFACE, 0xff)))
            addState(intArrayOf(-enabled), switchThumbState(c, 16, withAlpha(ON_SURFACE, 0x61)))
            addState(intArrayOf(checked, pressed), switchThumbState(c, 28, ON_PRIMARY_CONTAINER))
            addState(intArrayOf(checked), switchThumbState(c, 24, ON_PRIMARY))
            addState(intArrayOf(pressed), switchThumbState(c, 28, ON_SURFACE_VARIANT))
            addState(intArrayOf(), switchThumbState(c, 16, OUTLINE))
        }
        sw.trackDrawable = StateListDrawable().apply {
            setEnterFadeDuration(120)
            setExitFadeDuration(120)
            addState(intArrayOf(-enabled, checked), switchTrackState(c, withAlpha(ON_SURFACE, 0x1f), Color.TRANSPARENT))
            addState(intArrayOf(-enabled), switchTrackState(c, withAlpha(SURFACE_CONTAINER_HIGHEST, 0x1f), withAlpha(ON_SURFACE, 0x1f)))
            addState(intArrayOf(checked), switchTrackState(c, PRIMARY, Color.TRANSPARENT))
            addState(intArrayOf(), switchTrackState(c, SURFACE_CONTAINER_HIGHEST, OUTLINE))
        }
        sw.switchMinWidth = 0
        sw.showText = false
        sw.minHeight = dp(c, 48)
        sw.minimumHeight = dp(c, 48)
    }

    // ------------------------------------------------------------------ type helpers

    /** Card / screen title (sentence case). */
    fun styleTitle(view: TextView, large: Boolean = false) {
        view.textSize = if (large) TYPE_TITLE_LARGE else TYPE_TITLE
        view.typeface = MEDIUM
        view.setTextColor(ON_SURFACE)
    }

    /** A setting's or row's label. */
    fun styleLabel(view: TextView) {
        view.textSize = TYPE_SECTION
        view.typeface = MEDIUM
        view.setTextColor(ON_SURFACE)
    }

    /** One-line descriptions under titles and labels. */
    fun styleSupporting(view: TextView) {
        view.textSize = TYPE_SUPPORTING
        view.typeface = Typeface.DEFAULT
        view.setTextColor(ON_SURFACE_VARIANT)
        view.setLineSpacing(0f, 1.15f)
    }

    /** Small status chip (not pressable): text tinted with the role colour on a soft container. */
    fun styleStatusChip(view: TextView, color: Int) {
        val c = view.context
        view.background = pillDrawable(c, withAlpha(color, 0x24), Color.TRANSPARENT, SHAPE_FULL, 0f)
        view.setTextColor(color)
        view.typeface = MEDIUM
        view.textSize = TYPE_LABEL
        view.maxLines = 1
        view.ellipsize = TextUtils.TruncateAt.END
        view.setPaddingRelative(dp(c, 12), dp(c, 6), dp(c, 12), dp(c, 6))
    }

    // ------------------------------------------------------------------ log highlighting
    // Regexes precompiled once; the log refresh builds these spans off the main thread.
    private val LOG_RULES: List<Pair<Regex, Int>> = listOf(
        Regex("(?i)\\[CLAIM[^\\]]*\\]|\\| CLAIM \\||💖|💞") to LOG_ROSE,
        Regex("(?i)\\[KAKERA[^\\]]*\\]|\\| (?:KAKERA|GIVE) \\||💎|🔷|🟩|🟨|🟧|🟥") to PRIMARY,
        Regex("(?i)\\[SPHERE[^\\]]*\\]|\\| (?:SPHERE|PERK) \\||✨|🔮") to LOG_VIOLET,
        Regex("(?i)\\[INFO[^\\]]*\\]|\\| (?:ROLL|STATUS|SYSTEM|SIDE|SETUP) \\||ℹ️") to SECONDARY,
        Regex("(?i)\\[WARN(?:ING)?[^\\]]*\\]|\\| WARN \\||⚠️") to TERTIARY,
        Regex("(?i)\\[ERROR[^\\]]*\\]|\\| ERROR \\||❌|⛔|failed") to ERROR,
        Regex("(?i)\\[UPDATER[^\\]]*\\]|🚀|🌟") to PRIMARY,
        Regex("(?i)\\[CHECK[^\\]]*\\]|🔍") to SECONDARY,
        Regex("(?i)\\[RESET[^\\]]*\\]|⏰") to TERTIARY,
        Regex("(?i)\\[(START|RUNNING|ONLINE)[^\\]]*\\]") to PRIMARY,
    )

    /** Pure function (no views): safe to call on a background thread. */
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
