package com.mudaremote.android

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

class PresetImportParserTest {

    private lateinit var schemaFields: JSONObject

    @Before
    fun setUp() {
        schemaFields = JSONObject().apply {
            put("prefix", JSONObject().put("type", "text").put("default", "/////////////"))
            put("mudae_prefix", JSONObject().put("type", "text").put("default", "$"))
            put("channel_id", JSONObject().put("type", "text").put("default", ""))
            put("roll_command", JSONObject().put("type", "text").put("default", "wa"))
            put("rolling", JSONObject().put("type", "boolean").put("default", true))
            put("min_kakera", JSONObject().put("type", "number").put("default", 100))
            put("claim_interval", JSONObject().put("type", "number").put("default", 180))
            put("roll_interval", JSONObject().put("type", "number").put("default", 60))
            put("wishlist", JSONObject().put("type", "json").put("default", JSONArray()))
        }
    }

    @Test
    fun testFlatSlashWithNestedSettingsAndCustomFieldsPreserved() {
        val flatJson = """
        {
            "prefix": "/",
            "mudae_prefix": "$",
            "channel_id": "123456789012345678",
            "roll_command": "wa",
            "rolling": true,
            "min_kakera": 250,
            "wishlist": ["Rem", "Emilia"],
            "custom_nested_setting": {
                "active": true,
                "threshold": 42
            },
            "unknown_custom_field": "preserved_value"
        }
        """.trimIndent()

        val parsed = PresetImportParser.parse(flatJson, schemaFields, "profile-2")

        assertEquals(1, parsed.size)
        assertTrue(parsed.containsKey("profile-2"))

        val data = parsed["profile-2"]!!
        assertEquals("/", data.getString("prefix"))
        assertEquals("$", data.getString("mudae_prefix"))
        assertEquals("123456789012345678", data.getString("channel_id"))
        assertEquals("wa", data.getString("roll_command"))
        assertTrue(data.getBoolean("rolling"))
        assertEquals(250, data.getInt("min_kakera"))

        val wishlist = data.getJSONArray("wishlist")
        assertEquals(2, wishlist.length())
        assertEquals("Rem", wishlist.getString(0))
        assertEquals("Emilia", wishlist.getString(1))

        val nested = data.getJSONObject("custom_nested_setting")
        assertTrue(nested.getBoolean("active"))
        assertEquals(42, nested.getInt("threshold"))

        assertEquals("preserved_value", data.getString("unknown_custom_field"))
    }

    @Test
    fun testFlatDollarWithRoundtrip() {
        val flatJson = """
        {
            "prefix": "$",
            "mudae_prefix": "$",
            "roll_command": "ha",
            "rolling": false
        }
        """.trimIndent()

        val parsed = PresetImportParser.parse(flatJson, schemaFields, "profile-roundtrip")
        assertEquals(1, parsed.size)
        val data = parsed["profile-roundtrip"]!!
        assertEquals("$", data.getString("prefix"))
        assertEquals("ha", data.getString("roll_command"))
        assertFalse(data.getBoolean("rolling"))

        // Roundtrip serialization and re-parse
        val serialized = data.toString()
        val reParsed = PresetImportParser.parse(serialized, schemaFields, "profile-reloaded")
        assertEquals(1, reParsed.size)
        val reData = reParsed["profile-reloaded"]!!
        assertEquals("$", reData.getString("prefix"))
        assertEquals("ha", reData.getString("roll_command"))
        assertFalse(reData.getBoolean("rolling"))
    }

    @Test
    fun testNamedMultiMapWithFieldNameCollisions() {
        // A named map where profiles themselves are named after schema fields like "prefix" or "rolling"
        val namedJson = """
        {
            "Main": {
                "roll_command": "wa",
                "channel_id": "111"
            },
            "prefix": {
                "roll_command": "ha",
                "channel_id": "222",
                "prefix": "!"
            },
            "rolling": {
                "roll_command": "ma",
                "channel_id": "333",
                "rolling": true
            }
        }
        """.trimIndent()

        val parsed = PresetImportParser.parse(namedJson, schemaFields, "fallback-unused")

        assertEquals(3, parsed.size)
        assertFalse(parsed.containsKey("fallback-unused"))
        assertTrue(parsed.containsKey("Main"))
        assertTrue(parsed.containsKey("prefix"))
        assertTrue(parsed.containsKey("rolling"))

        assertEquals("111", parsed["Main"]!!.getString("channel_id"))
        assertEquals("222", parsed["prefix"]!!.getString("channel_id"))
        assertEquals("!", parsed["prefix"]!!.getString("prefix"))
        assertEquals("333", parsed["rolling"]!!.getString("channel_id"))
    }

    @Test
    fun testWrappedPresetsNamedMap() {
        val wrappedJson = """
        {
            "presets": {
                "Alpha": {
                    "roll_command": "wa",
                    "channel_id": "444"
                },
                "Beta": {
                    "roll_command": "ha",
                    "channel_id": "555"
                }
            }
        }
        """.trimIndent()

        val parsed = PresetImportParser.parse(wrappedJson, schemaFields, "fallback-unused")

        assertEquals(2, parsed.size)
        assertTrue(parsed.containsKey("Alpha"))
        assertTrue(parsed.containsKey("Beta"))
        assertEquals("wa", parsed["Alpha"]!!.getString("roll_command"))
        assertEquals("444", parsed["Alpha"]!!.getString("channel_id"))
        assertEquals("ha", parsed["Beta"]!!.getString("roll_command"))
        assertEquals("555", parsed["Beta"]!!.getString("channel_id"))
    }

    @Test
    fun testMalformedLaterEntryAbortsWithoutPartialMap() {
        val malformedJson = """
        {
            "ValidOne": {
                "roll_command": "wa"
            },
            "BrokenOne": "this_is_a_scalar_not_a_json_object"
        }
        """.trimIndent()

        try {
            PresetImportParser.parse(malformedJson, schemaFields, "fallback-unused")
            fail("Expected IllegalArgumentException on malformed named map entry")
        } catch (e: IllegalArgumentException) {
            assertTrue(e.message?.contains("BrokenOne") == true)
        }
    }

    @Test
    fun testEmptyInputsReturnEmptyMap() {
        val emptyRoot = PresetImportParser.parse("{}", schemaFields, "fallback")
        assertTrue(emptyRoot.isEmpty())

        val emptyPresets = PresetImportParser.parse("""{"presets": {}}""", schemaFields, "fallback")
        assertTrue(emptyPresets.isEmpty())
    }
}
