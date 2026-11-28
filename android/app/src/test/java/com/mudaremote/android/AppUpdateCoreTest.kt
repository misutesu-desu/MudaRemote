package com.mudaremote.android

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AppUpdateCoreTest {

    private val base = "https://github.com/YoRu72/MudaPersonalFork/releases/download"

    private fun asset(name: String, tag: String, size: Long = 1000L, digest: String? = null): JSONObject =
        JSONObject().apply {
            put("name", name)
            put("state", "uploaded")
            put("size", size)
            put("browser_download_url", "$base/$tag/$name")
            if (digest == null) put("digest", JSONObject.NULL) else put("digest", digest)
        }

    private fun release(
        tag: String,
        draft: Boolean = false,
        pre: Boolean = false,
        withApk: Boolean = true,
        withSha: Boolean = false,
        body: String = "Notes for $tag",
        digest: String? = null,
    ): JSONObject {
        val v = tag.removePrefix("v")
        val assets = JSONArray()
        if (withApk) assets.put(asset("MudaFork-$v.apk", tag, 4_000_000L, digest))
        if (withSha) assets.put(asset("MudaFork-$v.apk.sha256", tag, 100L))
        return JSONObject().apply {
            put("tag_name", tag)
            put("draft", draft)
            put("prerelease", pre)
            put("body", body)
            put("published_at", "2026-11-28T10:00:00Z")
            put("assets", assets)
        }
    }

    private fun list(vararg r: JSONObject): String = JSONArray().apply { r.forEach { put(it) } }.toString()

    // ---- versions

    @Test
    fun versionsCompareNumerically() {
        assertTrue(AppUpdateCore.compareVersions("6.0.10", "6.0.9") > 0)
        assertTrue(AppUpdateCore.compareVersions("6.1.0", "6.0.99") > 0)
        assertTrue(AppUpdateCore.compareVersions("v7.0.0", "6.9.9") > 0)
        assertEquals(0, AppUpdateCore.compareVersions("6.0", "6.0.0"))
        assertEquals(0, AppUpdateCore.compareVersions("v6.0.0", "6.0.0"))
    }

    @Test
    fun suffixSortsBelowTheReleaseAndInOrder() {
        assertTrue(AppUpdateCore.compareVersions("6.1.0-beta.1", "6.1.0") < 0)
        assertTrue(AppUpdateCore.compareVersions("6.1.0-beta.2", "6.1.0-beta.1") > 0)
        assertTrue(AppUpdateCore.compareVersions("6.1.0-beta.10", "6.1.0-beta.9") > 0)
        assertTrue(AppUpdateCore.compareVersions("6.1.0-beta.1", "6.0.9") > 0)
    }

    @Test
    fun neverUpdatesToTheSameOrLowerVersion() {
        assertFalse(AppUpdateCore.isNewer("6.0.0", "6.0.0"))
        assertFalse(AppUpdateCore.isNewer("5.9.9", "6.0.0"))
        assertFalse(AppUpdateCore.isNewer("6.0.0-beta.1", "6.0.0"))
        assertTrue(AppUpdateCore.isNewer("6.0.1", "6.0.0"))
        assertFalse(AppUpdateCore.isNewer("abc", "6.0.0"))
        assertFalse(AppUpdateCore.isNewer("6.0.1", "unknown"))
    }

    // ---- release and asset pick

    @Test
    fun picksTheNewestNonDraftReleaseWithItsApk() {
        val json = list(
            release("v6.0.1"),
            release("v6.0.3", draft = true),
            release("v6.0.2", withApk = false),
            release("v5.0.0"),
        )
        val r = AppUpdateCore.pickNewest(json, false)
        assertNotNull(r)
        assertEquals("6.0.1", r!!.version)
        assertEquals("MudaFork-6.0.1.apk", r.apk.name)
        assertEquals(4_000_000L, r.apk.size)
        assertNull(r.sha256Asset)
        assertEquals("2026-11-28", AppUpdateCore.publishedDate(r.publishedAt))
    }

    @Test
    fun prereleasesOnlyWithTheBetaSwitch() {
        val json = list(release("v6.1.0", pre = true), release("v6.0.1"))
        assertEquals("6.0.1", AppUpdateCore.pickNewest(json, false)!!.version)
        assertEquals("6.1.0", AppUpdateCore.pickNewest(json, true)!!.version)
    }

    @Test
    fun findsTheSha256Asset() {
        val r = AppUpdateCore.pickNewest(list(release("v6.0.1", withSha = true)), false)!!
        assertEquals("MudaFork-6.0.1.apk.sha256", r.sha256Asset!!.name)
    }

    @Test
    fun ignoresAssetsNotOnTheForksDownloadAddress() {
        val rel = release("v6.0.1")
        rel.getJSONArray("assets").getJSONObject(0)
            .put("browser_download_url", "https://github.com/someone/else/releases/download/v6.0.1/MudaFork-6.0.1.apk")
        assertNull(AppUpdateCore.pickNewest(list(rel), false))
    }

    @Test
    fun ignoresUnsafeOrUnparsableTags() {
        assertNull(AppUpdateCore.pickNewest(list(release("v../../x")), false))
        assertNull(AppUpdateCore.pickNewest(list(release("nightly")), false))
        assertNull(AppUpdateCore.pickNewest("not json", false))
        assertNull(AppUpdateCore.pickNewest("[]", false))
    }

    @Test
    fun onlyGithubHostsAreTrusted() {
        assertTrue(AppUpdateCore.isTrustedUrl("https://github.com/YoRu72/MudaPersonalFork/releases/download/v1/a.apk"))
        assertTrue(AppUpdateCore.isTrustedUrl("https://api.github.com/repos/YoRu72/MudaPersonalFork/releases"))
        assertTrue(AppUpdateCore.isTrustedUrl("https://objects.githubusercontent.com/x"))
        assertFalse(AppUpdateCore.isTrustedUrl("http://github.com/x"))
        assertFalse(AppUpdateCore.isTrustedUrl("https://evil.example.com/github.com"))
        assertFalse(AppUpdateCore.isTrustedUrl("https://github.com.evil.example/x"))
        assertFalse(AppUpdateCore.isTrustedUrl("not a url"))
        assertTrue(AppUpdateCore.RELEASES_API_URL.contains("YoRu72/MudaPersonalFork"))
    }

    // ---- checksum

    private val hexA = "a".repeat(64)
    private val hexB = "b".repeat(64)

    @Test
    fun readsTheChecksumFromGithubsDigestAndFromTheShaFile() {
        assertEquals(hexA, AppUpdateCore.sha256FromDigest("sha256:" + hexA.uppercase()))
        assertNull(AppUpdateCore.sha256FromDigest("sha1:abcd"))
        assertNull(AppUpdateCore.sha256FromDigest(null))
        assertEquals(hexB, AppUpdateCore.sha256FromText("$hexB  MudaFork-6.0.1.apk\n"))
        assertNull(AppUpdateCore.sha256FromText("no hash here"))
    }

    @Test
    fun conflictingChecksumsAreRefused() {
        val ok = AppUpdateCore.expectedSha256("sha256:$hexA", "$hexA  x.apk")
        assertEquals(hexA, ok.hex)
        assertFalse(ok.conflict)
        assertTrue(AppUpdateCore.expectedSha256("sha256:$hexA", "$hexB  x.apk").conflict)
        assertEquals(hexB, AppUpdateCore.expectedSha256(null, "$hexB  x.apk").hex)
        assertNull(AppUpdateCore.expectedSha256(null, null).hex)
    }

    @Test
    fun theDigestOfTheAssetIsRead() {
        val r = AppUpdateCore.pickNewest(list(release("v6.0.1", digest = "sha256:$hexA")), false)!!
        assertEquals(hexA, AppUpdateCore.sha256FromDigest(r.apk.digest))
    }

    @Test
    fun signersMustMatchExactly() {
        assertTrue(AppUpdateCore.signersMatch(setOf("aa"), setOf("aa")))
        assertFalse(AppUpdateCore.signersMatch(setOf("aa"), setOf("bb")))
        assertFalse(AppUpdateCore.signersMatch(setOf("aa"), setOf("aa", "bb")))
        assertFalse(AppUpdateCore.signersMatch(emptySet(), emptySet()))
        assertEquals(
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            AppUpdateCore.certDigestHex("abc".toByteArray())
        )
    }

    // ---- notes, skip, gate, cache

    @Test
    fun notesBecomePlainTrimmedText() {
        val t = AppUpdateCore.notesToText("### What's new\r\n- **Fast** setup with `x`\r\n\r\n\r\n\r\n* Logs\n<!-- hidden -->")
        assertEquals("What's new\n• Fast setup with x\n\n• Logs", t)
        val long = "line\n".repeat(2000)
        val cut = AppUpdateCore.notesToText(long, 100)
        assertTrue(cut.length <= 102)
        assertTrue(cut.endsWith("…"))
        assertEquals("", AppUpdateCore.notesToText("   "))
    }

    @Test
    fun skipHidesOnlyAutomaticOffers() {
        assertFalse(AppUpdateCore.shouldOffer("6.0.1", "6.0.1", false))
        assertTrue(AppUpdateCore.shouldOffer("6.0.1", "6.0.1", true))
        assertTrue(AppUpdateCore.shouldOffer("6.0.2", "6.0.1", false))
        assertTrue(AppUpdateCore.shouldOffer("6.0.1", "", false))
    }

    @Test
    fun checkGateIsTwelveHours() {
        val h = 3_600_000L
        assertTrue(AppUpdateCore.isCheckDue(0L, 1000L))
        assertFalse(AppUpdateCore.isCheckDue(1000L, 1000L + 11 * h))
        assertTrue(AppUpdateCore.isCheckDue(1000L, 1000L + 12 * h))
        assertTrue(AppUpdateCore.isCheckDue(5000L, 1000L))
    }

    @Test
    fun staleCacheFilesAreFound() {
        val day = 24L * 3_600_000L
        val now = 100L * day
        assertTrue(AppUpdateCore.isStaleCacheFile("MudaFork-6.0.0.apk", now, now, "6.0.0"))
        assertTrue(AppUpdateCore.isStaleCacheFile("MudaFork-5.0.0.apk.part", now, now, "6.0.0"))
        assertFalse(AppUpdateCore.isStaleCacheFile("MudaFork-6.0.1.apk.part", now - 6 * day, now, "6.0.0"))
        assertTrue(AppUpdateCore.isStaleCacheFile("MudaFork-6.0.1.apk.part", now - 8 * day, now, "6.0.0"))
        assertFalse(AppUpdateCore.isStaleCacheFile("other.txt", 0L, now, "6.0.0"))
        assertEquals("6.0.1", AppUpdateCore.versionOfCacheFile("MudaFork-6.0.1.apk.part"))
        assertNull(AppUpdateCore.versionOfCacheFile("notes.txt"))
    }

    @Test
    fun sizeIsShownInMegabytes() {
        assertEquals("4.0 MB", AppUpdateCore.formatMb(4_194_304L))
    }
}
