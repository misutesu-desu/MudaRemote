package com.mudaremote.android

import org.json.JSONArray
import org.json.JSONObject

/**
 * The schema key «visible_when»: one condition {"field": "x", "equals": v} or a JSON array of them
 * (all must hold). «equals» is one value (a choice string, or true/false for a switch) or an array of
 * values (any of). Pure logic only, so it can be unit-tested without Android classes.
 */
object VisibleWhen {
    /** True when the field has no condition, or every condition holds for [currentValue]. */
    fun isVisible(condition: Any?, currentValue: (String) -> Any?): Boolean = when (condition) {
        null, JSONObject.NULL -> true
        is JSONObject -> single(condition, currentValue)
        is JSONArray -> (0 until condition.length()).all { isVisible(condition.opt(it), currentValue) }
        else -> true
    }

    /** The field keys the condition reads (to know which edits must refresh the screen). */
    fun controllers(condition: Any?): Set<String> = when (condition) {
        is JSONObject -> condition.optString("field", "").let { if (it.isEmpty()) emptySet() else setOf(it) }
        is JSONArray -> (0 until condition.length()).flatMap { controllers(condition.opt(it)) }.toSet()
        else -> emptySet()
    }

    private fun single(condition: JSONObject, currentValue: (String) -> Any?): Boolean {
        val field = condition.optString("field", "")
        if (field.isEmpty() || !condition.has("equals")) return true
        val wanted = condition.opt("equals")
        val actual = currentValue(field)
        return if (wanted is JSONArray) (0 until wanted.length()).any { matches(wanted.opt(it), actual) }
        else matches(wanted, actual)
    }

    private fun matches(wanted: Any?, actual: Any?): Boolean = when {
        wanted is Boolean -> when (actual) {
            is Boolean -> actual == wanted
            is String -> actual.trim().lowercase() == wanted.toString()
            else -> false
        }
        wanted is Number && actual is Number -> wanted.toDouble() == actual.toDouble()
        else -> wanted?.toString() == actual?.toString()
    }
}
