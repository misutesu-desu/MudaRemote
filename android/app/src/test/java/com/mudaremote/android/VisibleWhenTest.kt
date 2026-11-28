package com.mudaremote.android

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VisibleWhenTest {
    private fun cond(field: String, equals: Any) = JSONObject().put("field", field).put("equals", equals)

    @Test
    fun noConditionIsVisible() {
        assertTrue(VisibleWhen.isVisible(null) { null })
        assertTrue(VisibleWhen.isVisible(JSONObject.NULL) { null })
    }

    @Test
    fun choiceEquality() {
        val values = mapOf<String, Any?>("harem_give_trigger" to "pages")
        assertTrue(VisibleWhen.isVisible(cond("harem_give_trigger", "pages")) { values[it] })
        assertFalse(VisibleWhen.isVisible(cond("harem_give_trigger", "value")) { values[it] })
    }

    @Test
    fun switchEquality() {
        assertTrue(VisibleWhen.isVisible(cond("auto_give_harem", true)) { true })
        assertFalse(VisibleWhen.isVisible(cond("auto_give_harem", true)) { false })
        assertFalse(VisibleWhen.isVisible(cond("auto_give_harem", true)) { null })
        assertTrue(VisibleWhen.isVisible(cond("auto_give_harem", true)) { "true" })
    }

    @Test
    fun anyOfAndAllOf() {
        val any = cond("loot_mode", JSONArray().put("kl").put("scrap"))
        assertTrue(VisibleWhen.isVisible(any) { "scrap" })
        assertFalse(VisibleWhen.isVisible(any) { "off" })
        val all = JSONArray().put(cond("auto_give_harem", true)).put(cond("harem_give_trigger", "pages"))
        val values = mapOf<String, Any?>("auto_give_harem" to true, "harem_give_trigger" to "pages")
        assertTrue(VisibleWhen.isVisible(all) { values[it] })
        assertFalse(VisibleWhen.isVisible(all) { if (it == "auto_give_harem") false else "pages" })
    }

    @Test
    fun controllersListEveryField() {
        val all = JSONArray().put(cond("a", true)).put(cond("b", "x"))
        assertEquals(setOf("a", "b"), VisibleWhen.controllers(all))
        assertEquals(setOf("a"), VisibleWhen.controllers(cond("a", true)))
        assertEquals(emptySet<String>(), VisibleWhen.controllers(null))
    }
}
