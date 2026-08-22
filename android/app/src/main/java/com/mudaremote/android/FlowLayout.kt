package com.mudaremote.android

import android.content.Context
import android.view.View
import android.view.ViewGroup

/**
 * Minimal flow layout that wraps children onto new lines when the row runs out
 * of width. Used for button/toolbars so nothing is ever clipped or pushed off
 * screen on narrow displays. No external dependencies.
 */
class FlowLayout(context: Context) : ViewGroup(context) {
    private val horizontalGap = UiTheme.dp(context, 6)
    private val verticalGap = UiTheme.dp(context, 6)

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val widthSize = MeasureSpec.getSize(widthMeasureSpec) - paddingLeft - paddingRight
        var width = 0
        var height = paddingTop + paddingBottom
        var lineWidth = 0
        var lineHeight = 0

        for (i in 0 until childCount) {
            val child = getChildAt(i)
            if (child.visibility == GONE) continue
            measureChild(child, widthMeasureSpec, heightMeasureSpec)
            val childWidth = child.measuredWidth
            val childHeight = child.measuredHeight

            if (lineWidth + childWidth > widthSize && lineWidth > 0) {
                width = maxOf(width, lineWidth)
                height += lineHeight + verticalGap
                lineWidth = childWidth
                lineHeight = childHeight
            } else {
                lineWidth += childWidth + if (lineWidth > 0) horizontalGap else 0
                lineHeight = maxOf(lineHeight, childHeight)
            }
        }
        width = maxOf(width, lineWidth) + paddingLeft + paddingRight
        height += lineHeight

        setMeasuredDimension(
            resolveSize(width, widthMeasureSpec),
            resolveSize(height, heightMeasureSpec)
        )
    }

    override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
        val widthSize = r - l - paddingLeft - paddingRight
        var x = paddingLeft
        var y = paddingTop
        var lineHeight = 0

        for (i in 0 until childCount) {
            val child = getChildAt(i)
            if (child.visibility == GONE) continue
            val childWidth = child.measuredWidth
            val childHeight = child.measuredHeight

            if (x + childWidth > paddingLeft + widthSize && x > paddingLeft) {
                x = paddingLeft
                y += lineHeight + verticalGap
                lineHeight = 0
            }

            child.layout(x, y, x + childWidth, y + childHeight)
            x += childWidth + horizontalGap
            lineHeight = maxOf(lineHeight, childHeight)
        }
    }

    companion object {
        fun wrapIn(context: Context, child: View): FlowLayout {
            return FlowLayout(context).apply { addView(child) }
        }
    }
}
