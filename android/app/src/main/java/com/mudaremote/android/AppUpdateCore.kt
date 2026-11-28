package com.mudaremote.android

import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.net.URL
import java.security.MessageDigest
import java.util.Locale

/**
 * The pure rules of the in-app updater (no Android classes, so JVM unit tests can run them):
 * version comparison, picking the release and its APK, the checksum, the notes text, the
 * skip choice, the 12-hour gate and which cached files are stale.
 *
 * The only source is the owner's fork: its releases API and its release downloads.
 */
object AppUpdateCore {
    const val REPO = "YoRu72/MudaPersonalFork"
    const val RELEASES_API_URL = "https://api.github.com/repos/$REPO/releases?per_page=30"
    const val RELEASES_PAGE_URL = "https://github.com/$REPO/releases"
    private const val DOWNLOAD_PREFIX = "https://github.com/$REPO/releases/download/"

    const val CHECK_INTERVAL_MS = 12L * 60L * 60L * 1000L
    const val PARTIAL_MAX_AGE_MS = 7L * 24L * 60L * 60L * 1000L
    const val NOTES_MAX_CHARS = 4000

    class Asset(val name: String, val url: String, val size: Long, val digest: String?)

    class ReleaseInfo(
        val tag: String,
        val version: String,
        val notes: String,
        val publishedAt: String,
        val prerelease: Boolean,
        val apk: Asset,
        val sha256Asset: Asset?,
    )

    /** The checksum the release states; [conflict] when its two sources disagree. */
    class ExpectedHash(val hex: String?, val conflict: Boolean)

    // ---------------------------------------------------------------- versions

    private class ParsedVersion(val core: List<Int>, val pre: List<String>)

    private val DIGITS = Regex("^[0-9]+$")

    private fun parseVersion(raw: String): ParsedVersion? {
        var s = raw.trim()
        if (s.startsWith("v") || s.startsWith("V")) s = s.substring(1)
        val plus = s.indexOf('+')
        if (plus >= 0) s = s.substring(0, plus)
        val dash = s.indexOf('-')
        val corePart = if (dash >= 0) s.substring(0, dash) else s
        val prePart = if (dash >= 0) s.substring(dash + 1) else ""
        if (corePart.isEmpty()) return null
        val nums = ArrayList<Int>()
        for (piece in corePart.split('.')) {
            if (!DIGITS.matches(piece)) return null
            val n = piece.toIntOrNull() ?: return null
            nums.add(n)
        }
        val pre = if (prePart.isEmpty()) emptyList() else prePart.split('.')
        return ParsedVersion(nums, pre)
    }

    /** True when the text is a version this updater can order (digits and dots, optional -suffix). */
    fun isValidVersion(raw: String): Boolean = parseVersion(raw) != null

    /**
     * Numeric comparison: 6.0.10 is above 6.0.9; a missing part counts as 0; a suffix such as
     * -beta.1 sorts below the same number without it. Unparsable text sorts lowest.
     */
    fun compareVersions(a: String, b: String): Int {
        val pa = parseVersion(a)
        val pb = parseVersion(b)
        if (pa == null && pb == null) return 0
        if (pa == null) return -1
        if (pb == null) return 1
        val n = maxOf(pa.core.size, pb.core.size)
        for (i in 0 until n) {
            val x = if (i < pa.core.size) pa.core[i] else 0
            val y = if (i < pb.core.size) pb.core[i] else 0
            if (x != y) return if (x > y) 1 else -1
        }
        if (pa.pre.isEmpty() && pb.pre.isEmpty()) return 0
        if (pa.pre.isEmpty()) return 1
        if (pb.pre.isEmpty()) return -1
        val m = maxOf(pa.pre.size, pb.pre.size)
        for (i in 0 until m) {
            if (i >= pa.pre.size) return -1
            if (i >= pb.pre.size) return 1
            val x = pa.pre[i]
            val y = pb.pre[i]
            val xn = DIGITS.matches(x)
            val yn = DIGITS.matches(y)
            val c = when {
                xn && yn -> (x.toLongOrNull() ?: 0L).compareTo(y.toLongOrNull() ?: 0L)
                xn -> -1
                yn -> 1
                else -> x.compareTo(y)
            }
            if (c != 0) return if (c > 0) 1 else -1
        }
        return 0
    }

    /** Only a strictly higher version is an update; the same or a lower one never is. */
    fun isNewer(candidate: String, installed: String): Boolean {
        if (parseVersion(candidate) == null || parseVersion(installed) == null) return false
        return compareVersions(candidate, installed) > 0
    }

    fun apkNameFor(version: String): String = "MudaFork-$version.apk"

    // ---------------------------------------------------------------- releases

    /** Only the fork's own GitHub hosts are ever contacted (and redirects stay on GitHub). */
    fun isTrustedUrl(url: String): Boolean {
        return try {
            val u = URL(url)
            val host = u.host.lowercase(Locale.US)
            u.protocol == "https" &&
                (host == "github.com" || host == "api.github.com" || host.endsWith(".githubusercontent.com"))
        } catch (e: Exception) {
            false
        }
    }

    private val SAFE_VERSION = Regex("^[0-9A-Za-z._+-]+$")

    private fun assetOf(releaseAssets: JSONArray?, wanted: String): Asset? {
        if (releaseAssets == null) return null
        for (i in 0 until releaseAssets.length()) {
            val a = releaseAssets.optJSONObject(i) ?: continue
            if (a.optString("name", "") != wanted) continue
            if (!a.isNull("state") && a.optString("state", "uploaded") != "uploaded") continue
            val url = a.optString("browser_download_url", "")
            if (!url.startsWith(DOWNLOAD_PREFIX)) continue
            val digest = if (a.isNull("digest")) null else a.optString("digest", "")
            return Asset(wanted, url, a.optLong("size", 0L), digest)
        }
        return null
    }

    private fun releaseFrom(o: JSONObject, includePre: Boolean): ReleaseInfo? {
        if (o.optBoolean("draft", false)) return null
        val pre = o.optBoolean("prerelease", false)
        if (pre && !includePre) return null
        val tag = o.optString("tag_name", "").trim()
        var version = tag
        if (version.startsWith("v") || version.startsWith("V")) version = version.substring(1)
        if (version.isEmpty() || !SAFE_VERSION.matches(version) || parseVersion(version) == null) return null
        val assets = o.optJSONArray("assets")
        val apk = assetOf(assets, apkNameFor(version)) ?: return null
        val sha = assetOf(assets, apkNameFor(version) + ".sha256")
        val notes = if (o.isNull("body")) "" else o.optString("body", "")
        val published = if (o.isNull("published_at")) "" else o.optString("published_at", "")
        return ReleaseInfo(tag, version, notes, published, pre, apk, sha)
    }

    /**
     * The newest non-draft release of the fork that carries `MudaFork-<version>.apk`
     * (pre-releases only when [includePre]); null when the text is not a release list or
     * nothing installable is in it. Whether it is newer than the installed app is [isNewer]'s call.
     */
    fun pickNewest(json: String, includePre: Boolean): ReleaseInfo? {
        val arr = try {
            JSONArray(json)
        } catch (e: JSONException) {
            return null
        }
        var best: ReleaseInfo? = null
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            val info = releaseFrom(o, includePre) ?: continue
            val current = best
            if (current == null || compareVersions(info.version, current.version) > 0) best = info
        }
        return best
    }

    // ---------------------------------------------------------------- checksum

    private val DIGEST_FIELD = Regex("^sha256:([0-9a-fA-F]{64})$")
    private val HEX64 = Regex("(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")

    /** GitHub's `digest` field ("sha256:<hex>") as lowercase hex; null when absent or another kind. */
    fun sha256FromDigest(digest: String?): String? {
        if (digest == null) return null
        return DIGEST_FIELD.matchEntire(digest.trim())?.groupValues?.get(1)?.lowercase(Locale.US)
    }

    /** The first 64-hex word of a `.sha256` file ("<hex>  <name>"); null when there is none. */
    fun sha256FromText(text: String?): String? {
        if (text == null) return null
        return HEX64.find(text)?.value?.lowercase(Locale.US)
    }

    fun expectedSha256(apiDigest: String?, fileText: String?): ExpectedHash {
        val a = sha256FromDigest(apiDigest)
        val b = sha256FromText(fileText)
        if (a != null && b != null && a != b) return ExpectedHash(null, true)
        return ExpectedHash(a ?: b, false)
    }

    fun hex(bytes: ByteArray): String {
        val sb = StringBuilder(bytes.size * 2)
        for (b in bytes) {
            val v = b.toInt() and 0xff
            sb.append("0123456789abcdef"[v shr 4])
            sb.append("0123456789abcdef"[v and 0x0f])
        }
        return sb.toString()
    }

    fun certDigestHex(certBytes: ByteArray): String = hex(MessageDigest.getInstance("SHA-256").digest(certBytes))

    /** The downloaded APK is trusted only when it is signed by exactly the installed app's certificates. */
    fun signersMatch(installed: Set<String>, archive: Set<String>): Boolean =
        installed.isNotEmpty() && installed == archive

    // ---------------------------------------------------------------- text and choices

    /** Release notes as plain readable text: headings and bold marks dropped, bullets as dots, trimmed. */
    fun notesToText(markdown: String, maxChars: Int = NOTES_MAX_CHARS): String {
        var t = markdown.replace("\r\n", "\n").replace('\r', '\n')
        t = Regex("<!--[\\s\\S]*?-->").replace(t, "")
        val heading = Regex("^\\s{0,3}#{1,6}\\s*")
        val bullet = Regex("^(\\s*)[-*]\\s+")
        val lines = ArrayList<String>()
        for (raw in t.split('\n')) {
            var l = raw.trimEnd()
            l = heading.replace(l, "")
            l = bullet.replace(l) { m -> m.groupValues[1] + "• " }
            l = l.replace("**", "").replace("`", "")
            lines.add(l)
        }
        var out = lines.joinToString("\n")
        out = Regex("\\n{3,}").replace(out, "\n\n").trim()
        if (out.length > maxChars) {
            var cut = out.substring(0, maxChars)
            val lastBreak = cut.lastIndexOf('\n')
            if (lastBreak > maxChars / 2) cut = cut.substring(0, lastBreak)
            out = cut.trimEnd() + "\n…"
        }
        return out
    }

    fun formatMb(bytes: Long): String = String.format(Locale.US, "%.1f MB", bytes / 1048576.0)

    /** The date part of GitHub's timestamp ("2026-11-28T10:00:00Z" -> "2026-11-28"); blank when absent. */
    fun publishedDate(iso: String): String = if (iso.length >= 10) iso.substring(0, 10) else ""

    /** An automatic check offers a skipped version no more; «Check now» always does. */
    fun shouldOffer(version: String, skippedVersion: String, manual: Boolean): Boolean =
        manual || skippedVersion.trim() != version.trim()

    /** At most one automatic check per interval; a clock that went backwards counts as due. */
    fun isCheckDue(lastCheckMs: Long, nowMs: Long, intervalMs: Long = CHECK_INTERVAL_MS): Boolean =
        lastCheckMs <= 0L || nowMs < lastCheckMs || nowMs - lastCheckMs >= intervalMs

    // ---------------------------------------------------------------- cache files

    private val CACHE_FILE = Regex("^MudaFork-(.+?)\\.apk(\\.part)?$")

    /** The version in the name of one of the updater's own cache files; null for any other file. */
    fun versionOfCacheFile(name: String): String? = CACHE_FILE.matchEntire(name)?.groupValues?.get(1)

    /**
     * Which cache files to delete: those of the installed version or older (the update went
     * through), and the updater's partial or finished downloads left more than a week.
     * Files the updater did not write are never touched.
     */
    fun isStaleCacheFile(name: String, lastModifiedMs: Long, nowMs: Long, installedVersion: String): Boolean {
        val v = versionOfCacheFile(name) ?: return false
        if (parseVersion(v) == null) return false
        if (parseVersion(installedVersion) != null && compareVersions(v, installedVersion) <= 0) return true
        return nowMs - lastModifiedMs > PARTIAL_MAX_AGE_MS
    }
}
