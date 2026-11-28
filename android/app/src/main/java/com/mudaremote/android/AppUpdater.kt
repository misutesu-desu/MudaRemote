package com.mudaremote.android

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import androidx.core.content.FileProvider
import java.io.File
import java.io.IOException
import java.net.ConnectException
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URL
import java.net.UnknownHostException
import java.security.MessageDigest
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.atomic.AtomicBoolean

/**
 * The app's own updater. It looks only at the releases of the owner's fork on GitHub,
 * downloads `MudaFork-<version>.apk` to the app cache ([RangeDownloader]: several connections,
 * resume of half-done chunks, retry with back-off, one connection when the server cannot cut the
 * file), checks its
 * size, its SHA-256 (when the release states one), its package name and its signing
 * certificate, and then hands it to Android's installer.
 *
 * It keeps its state in the process, so a rotated or re-opened screen shows the same dialog
 * again ([AppUpdateUi] draws it from [snapshot]).
 */
object AppUpdater {
    enum class Phase { IDLE, OFFER, DOWNLOADING, VERIFYING, READY, NEEDS_PERMISSION, INSTALLER_OPENED, FAILED }

    class Snapshot(
        val phase: Phase,
        val release: AppUpdateCore.ReleaseInfo?,
        val done: Long,
        val total: Long,
        val message: String,
        val speed: Long = 0L,  // bytes per second while downloading, 0 when not known
    )

    enum class FailKind { OFFLINE, RATE_LIMITED, ERROR }

    sealed class CheckResult {
        object UpToDate : CheckResult()
        object Busy : CheckResult()
        class Available(val release: AppUpdateCore.ReleaseInfo) : CheckResult()
        class Skipped(val release: AppUpdateCore.ReleaseInfo) : CheckResult()
        class Failed(val kind: FailKind, val detail: String) : CheckResult()
    }

    enum class InstallStart { STARTED, NEEDS_PERMISSION, FAILED }

    const val PREFS = "mudaremote_prefs"
    const val PREF_AUTO = "pref_app_update_auto"
    const val PREF_BETA = "pref_app_update_beta"
    private const val PREF_LAST_CHECK = "app_update_last_check"
    private const val PREF_SKIPPED = "app_update_skipped_version"
    private const val PREF_LAST_SEEN = "app_update_last_seen_version"
    private const val MAX_ATTEMPTS = 3
    private const val MAX_JSON_BYTES = 2 * 1024 * 1024

    private class FatalDownloadException(message: String) : Exception(message)
    private class CancelledException : Exception()
    private class HttpResult(val code: Int, val body: String, val rateRemaining: String?)

    private val main = Handler(Looper.getMainLooper())
    private val cancelFlag = AtomicBoolean(false)

    @Volatile
    var snapshot: Snapshot = Snapshot(Phase.IDLE, null, 0L, 0L, "")
        private set

    /** Called on the main thread whenever [snapshot] changes. */
    @Volatile
    var listener: ((Snapshot) -> Unit)? = null

    @Volatile
    private var worker: Thread? = null

    @Volatile
    private var checking = false

    // ---------------------------------------------------------------- small helpers

    fun prefs(context: Context): SharedPreferences =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun autoCheckEnabled(context: Context): Boolean = prefs(context).getBoolean(PREF_AUTO, true)
    fun betaEnabled(context: Context): Boolean = prefs(context).getBoolean(PREF_BETA, false)
    fun lastCheckMs(context: Context): Long = prefs(context).getLong(PREF_LAST_CHECK, 0L)

    fun installedVersion(context: Context): String = try {
        context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: "0"
    } catch (e: Exception) {
        "0"
    }

    fun skipVersion(context: Context, version: String) {
        prefs(context).edit().putString(PREF_SKIPPED, version).apply()
        system(context, "Update $version skipped.")
    }

    fun isBusy(): Boolean = snapshot.phase == Phase.DOWNLOADING || snapshot.phase == Phase.VERIFYING

    private fun set(phase: Phase, release: AppUpdateCore.ReleaseInfo?, done: Long = 0L, total: Long = 0L, message: String = "", speed: Long = 0L) {
        val snap = Snapshot(phase, release, done, total, message, speed)
        snapshot = snap
        main.post { listener?.invoke(snap) }
    }

    /** Back to nothing pending (the dialog was closed with Later or Close). */
    fun dismiss() {
        if (isBusy()) return
        set(Phase.IDLE, null)
    }

    fun cancel() {
        cancelFlag.set(true)
    }

    private fun updatesDir(context: Context): File {
        val dir = File(context.cacheDir, "updates")
        if (!dir.isDirectory) dir.mkdirs()
        return dir
    }

    /** One SYSTEM line in the app's log (and the day's TXT copy), like the service writes them. */
    fun system(context: Context, message: String) {
        runCatching {
            val clean = message.replace(Regex("\\s*[\\r\\n]+\\s*"), " / ").replace(" | ", " / ")
            val stamp = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())
            val line = "$stamp | ANDROID | SYSTEM | Updater: $clean\n"
            File(context.filesDir, MudaRemoteService.LOG_FILE).appendText(line)
            val logsDir = File(context.filesDir, "logs")
            logsDir.mkdirs()
            File(logsDir, "ANDROID_" + stamp.substring(0, 10) + ".txt").appendText(line)
        }
    }

    /**
     * Start-up housekeeping (background): deletes the finished or partial downloads of versions
     * that are installed now, and partials older than a week; notes a version change in the log.
     */
    fun cleanup(context: Context) {
        val app = context.applicationContext
        Thread {
            runCatching {
                val installed = installedVersion(app)
                val now = System.currentTimeMillis()
                val files = updatesDir(app).listFiles() ?: emptyArray()
                for (f in files) {
                    if (f.isFile && AppUpdateCore.isStaleCacheFile(f.name, f.lastModified(), now, installed)) f.delete()
                }
                val p = prefs(app)
                val before = p.getString(PREF_LAST_SEEN, "") ?: ""
                if (before.isNotEmpty() && before != installed && AppUpdateCore.isNewer(installed, before)) {
                    system(app, "App updated from v$before to v$installed.")
                }
                if (before != installed) p.edit().putString(PREF_LAST_SEEN, installed).apply()
            }
        }.start()
    }

    // ---------------------------------------------------------------- the check

    /**
     * Asks the fork's releases whether a newer version exists. [onDone] runs on the main thread.
     * An automatic check ([manual] false) passes over a skipped version; failures are logged only
     * (the caller decides whether to say anything).
     */
    fun check(context: Context, manual: Boolean, onDone: (CheckResult) -> Unit) {
        val app = context.applicationContext
        if (checking || isBusy()) {
            main.post { onDone(CheckResult.Busy) }
            return
        }
        checking = true
        Thread {
            val result: CheckResult = try {
                runCheck(app, manual)
            } catch (e: Exception) {
                system(app, "Update check failed: ${e.javaClass.simpleName}.")
                CheckResult.Failed(FailKind.ERROR, e.message ?: e.javaClass.simpleName)
            }
            checking = false
            main.post { onDone(result) }
        }.start()
    }

    private fun runCheck(app: Context, manual: Boolean): CheckResult {
        val p = prefs(app)
        val installed = installedVersion(app)
        val includePre = p.getBoolean(PREF_BETA, false)
        val response = try {
            httpGetText(AppUpdateCore.RELEASES_API_URL, "application/vnd.github+json")
        } catch (e: UnknownHostException) {
            system(app, "Update check: no connection.")
            return CheckResult.Failed(FailKind.OFFLINE, "offline")
        } catch (e: ConnectException) {
            system(app, "Update check: no connection.")
            return CheckResult.Failed(FailKind.OFFLINE, "offline")
        } catch (e: SocketTimeoutException) {
            system(app, "Update check: timed out.")
            return CheckResult.Failed(FailKind.OFFLINE, "timeout")
        } catch (e: IOException) {
            system(app, "Update check failed: ${e.javaClass.simpleName}.")
            return CheckResult.Failed(FailKind.ERROR, e.message ?: e.javaClass.simpleName)
        }
        val limited = response.code == 429 || (response.code == 403 && response.rateRemaining == "0")
        if (limited) {
            p.edit().putLong(PREF_LAST_CHECK, System.currentTimeMillis()).apply()
            system(app, "Update check: GitHub rate limit reached; try later.")
            return CheckResult.Failed(FailKind.RATE_LIMITED, "rate limit")
        }
        if (response.code != 200) {
            system(app, "Update check failed: HTTP ${response.code}.")
            return CheckResult.Failed(FailKind.ERROR, "HTTP ${response.code}")
        }
        p.edit().putLong(PREF_LAST_CHECK, System.currentTimeMillis()).apply()
        val release = AppUpdateCore.pickNewest(response.body, includePre)
        if (release == null || !AppUpdateCore.isNewer(release.version, installed)) {
            system(app, "Update check: up to date (installed v$installed).")
            return CheckResult.UpToDate
        }
        val skipped = p.getString(PREF_SKIPPED, "") ?: ""
        if (!AppUpdateCore.shouldOffer(release.version, skipped, manual)) {
            system(app, "Update check: v${release.version} is available but was skipped.")
            return CheckResult.Skipped(release)
        }
        system(app, "Update check: v${release.version} is available (installed v$installed, ${AppUpdateCore.formatMb(release.apk.size)}).")
        if (!isBusy()) set(Phase.OFFER, release)
        return CheckResult.Available(release)
    }

    // ---------------------------------------------------------------- network

    /** Opens [url0], following redirects by hand so every hop stays on GitHub's own hosts. */
    private fun openFollowing(url0: String, rangeFrom: Long, accept: String?): HttpURLConnection {
        var url = url0
        for (hop in 0..5) {
            if (!AppUpdateCore.isTrustedUrl(url)) throw FatalDownloadException("The download address is not on GitHub.")
            val c = URL(url).openConnection() as HttpURLConnection
            c.instanceFollowRedirects = false
            c.connectTimeout = 15000
            c.readTimeout = 30000
            c.setRequestProperty("User-Agent", "MudaFork-Updater")
            c.setRequestProperty("Accept-Encoding", "identity")
            if (accept != null) c.setRequestProperty("Accept", accept)
            if (rangeFrom > 0L) c.setRequestProperty("Range", "bytes=$rangeFrom-")
            val code = c.responseCode
            if (code == 301 || code == 302 || code == 303 || code == 307 || code == 308) {
                val loc = c.getHeaderField("Location")
                c.disconnect()
                if (loc.isNullOrBlank()) throw IOException("Redirect without a location")
                url = URL(URL(url), loc).toString()
                continue
            }
            return c
        }
        throw IOException("Too many redirects")
    }

    /** Connections for the APK download: same identity and timeouts; redirects are followed (and checked) by [RangeDownloader]. */
    private val downloadOpener = RangeDownloader.Opener { url ->
        val c = url.openConnection() as HttpURLConnection
        c.instanceFollowRedirects = false
        c.connectTimeout = 15000
        c.readTimeout = 30000
        c.setRequestProperty("User-Agent", "MudaFork-Updater")
        c.setRequestProperty("Accept", "application/octet-stream")
        c
    }

    /** Every address of the download, after every redirect, must be one of GitHub's own hosts. */
    private val downloadCheck = RangeDownloader.UrlCheck { url -> AppUpdateCore.isTrustedUrl(url) }

    private fun httpGetText(url: String, accept: String): HttpResult {
        val c = openFollowing(url, 0L, accept)
        try {
            val code = c.responseCode
            val remaining = c.getHeaderField("X-RateLimit-Remaining")
            if (code != 200) return HttpResult(code, "", remaining)
            val out = java.io.ByteArrayOutputStream()
            c.inputStream.use { input ->
                val buf = ByteArray(8192)
                while (true) {
                    val n = input.read(buf)
                    if (n < 0) break
                    out.write(buf, 0, n)
                    if (out.size() > MAX_JSON_BYTES) throw IOException("Response too large")
                }
            }
            return HttpResult(code, out.toString("UTF-8"), remaining)
        } finally {
            c.disconnect()
        }
    }

    // ---------------------------------------------------------------- the download

    fun startDownload(context: Context, release: AppUpdateCore.ReleaseInfo) {
        if (worker?.isAlive == true) return
        cancelFlag.set(false)
        val app = context.applicationContext
        val t = Thread { runDownload(app, release) }
        worker = t
        t.start()
    }

    private fun fail(app: Context, release: AppUpdateCore.ReleaseInfo, message: String) {
        system(app, "Update to v${release.version} failed: $message")
        set(Phase.FAILED, release, 0L, 0L, message)
    }

    private fun runDownload(app: Context, release: AppUpdateCore.ReleaseInfo) {
        val dir = updatesDir(app)
        val finalFile = File(dir, AppUpdateCore.apkNameFor(release.version))
        val part = File(dir, finalFile.name + ".part")
        val state = File(dir, finalFile.name + ".part.state")
        val total = release.apk.size
        try {
            set(Phase.DOWNLOADING, release, 0L, total)
            // The checksum the release states: GitHub's own digest, or the .sha256 asset.
            var fileText: String? = null
            val shaAsset = release.sha256Asset
            if (shaAsset != null && AppUpdateCore.sha256FromDigest(release.apk.digest) == null) {
                fileText = fetchSmallText(shaAsset.url)
                if (AppUpdateCore.sha256FromText(fileText) == null) {
                    fail(app, release, "The release's checksum file could not be read.")
                    return
                }
            }
            val expected = AppUpdateCore.expectedSha256(release.apk.digest, fileText)
            if (expected.conflict) {
                fail(app, release, "The release's checksums disagree; the update was refused.")
                return
            }
            val alreadyHere = finalFile.isFile && (total <= 0L || finalFile.length() == total)
            if (!alreadyHere) {
                finalFile.delete()
                downloadWithRetry(app, release, part, state)
                if (!part.renameTo(finalFile)) throw IOException("Could not store the downloaded file.")
            }
            set(Phase.VERIFYING, release, total, total)
            if (total > 0L && finalFile.length() != total) {
                finalFile.delete()
                discardPartial(part, state)
                fail(app, release, "The downloaded file has the wrong size.")
                return
            }
            val wanted = expected.hex
            if (wanted != null) {
                val actual = sha256OfFile(finalFile)
                if (actual != wanted) {
                    finalFile.delete()
                    discardPartial(part, state)
                    fail(app, release, "The downloaded file is damaged (checksum mismatch). Try again.")
                    return
                }
            } else {
                system(app, "The release states no checksum; only its size was checked.")
            }
            val problem = verifyArchive(app, finalFile, release)
            if (problem != null) {
                finalFile.delete()
                fail(app, release, problem)
                return
            }
            system(app, "Update v${release.version} downloaded and verified.")
            set(Phase.READY, release, total, total)
        } catch (e: CancelledException) {
            system(app, "Update download cancelled (partial file kept).")
            set(Phase.OFFER, release)
        } catch (e: FatalDownloadException) {
            fail(app, release, e.message ?: "Download refused.")
        } catch (e: Exception) {
            val offline = e is UnknownHostException || e is ConnectException || e is SocketTimeoutException
            fail(app, release, if (offline) "No connection. Try again when you are online." else "Download failed (${e.javaClass.simpleName}).")
        }
    }

    private fun fetchSmallText(url: String): String? {
        val r = httpGetText(url, "*/*")
        return if (r.code == 200) r.body else null
    }

    /** The partial file, its progress record and the record's temporary copy. */
    private fun discardPartial(part: File, state: File) {
        part.delete()
        state.delete()
        File(state.path + ".tmp").delete()
    }

    private fun downloadWithRetry(app: Context, release: AppUpdateCore.ReleaseInfo, part: File, state: File) {
        var attempt = 0
        while (true) {
            attempt++
            try {
                downloadOnce(app, release, part, state)
                return
            } catch (e: CancelledException) {
                throw e
            } catch (e: FatalDownloadException) {
                throw e
            } catch (e: IOException) {
                if (attempt >= MAX_ATTEMPTS) throw e
                system(app, "Download interrupted; retrying ($attempt/$MAX_ATTEMPTS).")
                set(Phase.DOWNLOADING, release, snapshot.done, release.apk.size, "Connection lost; retrying ($attempt/$MAX_ATTEMPTS)...")
                var waited = 0L
                while (waited < 2000L * attempt) {
                    if (cancelFlag.get()) throw CancelledException()
                    Thread.sleep(250L)
                    waited += 250L
                }
            }
        }
    }

    /** One run of the downloader: it resumes from the progress record when the size and the ETag/date still match. */
    private fun downloadOnce(app: Context, release: AppUpdateCore.ReleaseInfo, part: File, state: File) {
        val total = release.apk.size
        val result = try {
            RangeDownloader.fetch(
                release.apk.url, part, state, RangeDownloader.MAX_CONNECTIONS, downloadOpener, downloadCheck, cancelFlag,
                RangeDownloader.Listener { done, size, speed ->
                    set(Phase.DOWNLOADING, release, done, if (size > 0L) size else total, "", speed)
                },
            )
        } catch (e: RangeDownloader.Cancelled) {
            throw CancelledException()
        } catch (e: RangeDownloader.Refused) {
            throw FatalDownloadException("The download address is not on GitHub.")
        } catch (e: RangeDownloader.Status) {
            if (e.code in 400..499 && !RangeDownloader.isRetryableStatus(e.code)) {
                throw FatalDownloadException("The download was refused (HTTP ${e.code}).")
            }
            throw e
        }
        if (result.resumed) system(app, "Download went on from the earlier partial file.")
        if (!result.ranged) system(app, "The server cannot send the file in parts; it was downloaded over one connection.")
        else system(app, "Downloaded over ${result.connections} connection(s).")
        // The size is checked against the release by the caller (a wrong size is refused there).
    }

    private fun sha256OfFile(file: File): String {
        val md = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buf = ByteArray(64 * 1024)
            while (true) {
                val n = input.read(buf)
                if (n < 0) break
                md.update(buf, 0, n)
            }
        }
        return AppUpdateCore.hex(md.digest())
    }

    // ---------------------------------------------------------------- the APK's identity

    @Suppress("DEPRECATION")
    private fun signerSet(info: PackageInfo?): Set<String> {
        if (info == null) return emptySet()
        val sigs = if (Build.VERSION.SDK_INT >= 28) {
            val si = info.signingInfo
            if (si == null) null else si.apkContentsSigners
        } else {
            info.signatures
        }
        val out = HashSet<String>()
        if (sigs != null) {
            for (s in sigs) out.add(AppUpdateCore.certDigestHex(s.toByteArray()))
        }
        return out
    }

    /** Null when the file is this app's own newer build signed by the same certificate; else the reason. */
    @Suppress("DEPRECATION")
    private fun verifyArchive(app: Context, file: File, release: AppUpdateCore.ReleaseInfo): String? {
        return try {
            val pm = app.packageManager
            val flags = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
            val archive = pm.getPackageArchiveInfo(file.absolutePath, flags)
                ?: return "The downloaded file is not a readable app package."
            if (archive.packageName != app.packageName) {
                return "The downloaded app is not MudaFork (different package name); refused."
            }
            val archiveVersion = archive.versionName ?: ""
            if (AppUpdateCore.compareVersions(archiveVersion, release.version) != 0) {
                return "The downloaded app's version does not match the release; refused."
            }
            if (!AppUpdateCore.isNewer(archiveVersion, installedVersion(app))) {
                return "The downloaded app is not newer than the installed one; refused."
            }
            val installedInfo = pm.getPackageInfo(app.packageName, flags)
            if (!AppUpdateCore.signersMatch(signerSet(installedInfo), signerSet(archive))) {
                "The downloaded app is signed with a different certificate than the installed one; refused."
            } else {
                null
            }
        } catch (e: Exception) {
            "The downloaded app could not be checked (${e.javaClass.simpleName}); refused."
        }
    }

    // ---------------------------------------------------------------- install

    fun canInstall(context: Context): Boolean = context.packageManager.canRequestPackageInstalls()

    /** Hands the verified APK to Android's installer (checked again first). */
    fun launchInstall(activity: Activity): InstallStart {
        val release = snapshot.release ?: return InstallStart.FAILED
        val app = activity.applicationContext
        val file = File(updatesDir(app), AppUpdateCore.apkNameFor(release.version))
        if (!file.isFile) {
            fail(app, release, "The downloaded file is gone. Try again.")
            return InstallStart.FAILED
        }
        if (!canInstall(app)) {
            system(app, "Installing from this app is not allowed yet; asking for the setting.")
            set(Phase.NEEDS_PERMISSION, release)
            return InstallStart.NEEDS_PERMISSION
        }
        val problem = verifyArchive(app, file, release)
        if (problem != null) {
            file.delete()
            fail(app, release, problem)
            return InstallStart.FAILED
        }
        return try {
            val uri = FileProvider.getUriForFile(app, app.packageName + ".updates", file)
            val intent = Intent(Intent.ACTION_VIEW)
                .setDataAndType(uri, "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            activity.startActivity(intent)
            system(app, "Installer opened for v${release.version}.")
            set(Phase.INSTALLER_OPENED, release)
            InstallStart.STARTED
        } catch (e: ActivityNotFoundException) {
            fail(app, release, "No installer is available on this device.")
            InstallStart.FAILED
        } catch (e: Exception) {
            fail(app, release, "Could not open the installer (${e.javaClass.simpleName}).")
            InstallStart.FAILED
        }
    }
}
