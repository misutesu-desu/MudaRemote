package com.mudaremote.android

import org.json.JSONObject

object PresetImportParser {

    /**
     * Parse preset JSON text into a validated map of profile names to preset data.
     *
     * Unwraps a top-level "presets" object as an explicit named map. Otherwise, treats
     * the root as a flat single preset if any known schema field contains a non-JSONObject
     * value, or as a named map if all root entries are JSONObjects.
     */
    fun parse(
        text: String,
        schemaFields: JSONObject,
        singleProfileName: String
    ): LinkedHashMap<String, JSONObject> {
        val root = JSONObject(text)
        val target = if (root.opt("presets") is JSONObject) {
            root.getJSONObject("presets")
        } else {
            null
        }

        if (target != null) {
            return validateNamedMap(target)
        }

        val isFlat = schemaFields.keys().asSequence().any { key ->
            root.has(key) && root.opt(key) !is JSONObject
        }

        if (isFlat) {
            return linkedMapOf(singleProfileName to root)
        }

        return validateNamedMap(root)
    }

    private fun validateNamedMap(mapObj: JSONObject): LinkedHashMap<String, JSONObject> {
        val result = linkedMapOf<String, JSONObject>()
        mapObj.keys().asSequence().forEach { name ->
            val value = mapObj.opt(name) as? JSONObject
                ?: throw IllegalArgumentException("Value for profile '$name' is not a preset object")
            result[name] = value
        }
        return result
    }
}
