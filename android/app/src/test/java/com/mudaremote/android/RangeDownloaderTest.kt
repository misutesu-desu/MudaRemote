package com.mudaremote.android

import com.sun.net.httpserver.HttpServer
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.util.Random
import java.util.concurrent.atomic.AtomicBoolean

class RangeDownloaderTest {

    @get:Rule
    val tmp = TemporaryFolder()

    // ---------------------------------------------------------------- chunk planning

    @Test
    fun connectionsFollowTheSizeAndNeverExceedTheMaximum() {
        assertEquals(1, RangeDownloader.connectionsFor(0L, 4))
        assertEquals(1, RangeDownloader.connectionsFor(100_000L, 4))
        assertEquals(1, RangeDownloader.connectionsFor(700_000L, 4))
        assertEquals(2, RangeDownloader.connectionsFor(1_100_000L, 4))
        assertEquals(4, RangeDownloader.connectionsFor(60_000_000L, 4))
        assertEquals(1, RangeDownloader.connectionsFor(60_000_000L, 0))
    }

    @Test
    fun chunksAreAQuarterOfAConnectionsShareBetweenOneAndEightMegabytes() {
        val mb = 1L shl 20
        assertEquals(1 * mb, RangeDownloader.chunkSizeFor(3 * mb, 4))
        assertEquals(2 * mb, RangeDownloader.chunkSizeFor(32 * mb, 4))
        assertEquals(8 * mb, RangeDownloader.chunkSizeFor(400 * mb, 4))
    }

    @Test
    fun chunksCoverTheFileExactly() {
        val total = 7_300_123L
        val chunk = 2L shl 20
        val count = RangeDownloader.chunkCount(total, chunk)
        assertEquals(4, count)
        assertEquals(0L, RangeDownloader.chunkStart(0, chunk))
        var covered = 0L
        for (i in 0 until count) {
            val start = RangeDownloader.chunkStart(i, chunk)
            val end = RangeDownloader.chunkEnd(i, chunk, total)
            assertEquals(covered, start)
            assertTrue(end > start)
            covered = end
        }
        assertEquals(total, covered)
        assertEquals(0, RangeDownloader.chunkCount(0L, chunk))
    }

    @Test
    fun contentRangeTotalIsRead() {
        assertEquals(12345L, RangeDownloader.totalFromContentRange("bytes 0-0/12345"))
        assertEquals(-1L, RangeDownloader.totalFromContentRange("bytes 0-0/*"))
        assertEquals(-1L, RangeDownloader.totalFromContentRange("garbage"))
        assertEquals(-1L, RangeDownloader.totalFromContentRange(null))
    }

    @Test
    fun backOffGrowsAndIsLongerWhenTheServerIsBusy() {
        assertEquals(400L, RangeDownloader.backoffMillis(0, 0))
        assertEquals(800L, RangeDownloader.backoffMillis(1, 500))
        assertEquals(8000L, RangeDownloader.backoffMillis(40, 0))
        assertEquals(1200L, RangeDownloader.backoffMillis(0, 429))
        assertTrue(RangeDownloader.isRetryableStatus(503))
        assertTrue(RangeDownloader.isRetryableStatus(429))
        assertFalse(RangeDownloader.isRetryableStatus(404))
        assertFalse(RangeDownloader.isRetryableStatus(403))
    }

    // ---------------------------------------------------------------- resume decision

    private fun savedState(total: Long, validator: String): RangeDownloader.State {
        val st = RangeDownloader.State()
        st.total = total
        st.chunk = 1L shl 20
        st.validator = validator
        st.mark(0)
        st.setPartial(2, 500_000L)
        return st
    }

    @Test
    fun resumesOnlyWithTheSameSizeFileLengthAndValidator() {
        val st = savedState(3_000_000L, "\"abc\"")
        assertTrue(RangeDownloader.canResume(st, 3_000_000L, 3_000_000L, "\"abc\""))
        assertFalse(RangeDownloader.canResume(null, 3_000_000L, 3_000_000L, "\"abc\""))
        assertFalse(RangeDownloader.canResume(st, 3_000_001L, 3_000_001L, "\"abc\""))
        assertFalse(RangeDownloader.canResume(st, 3_000_000L, 2_999_999L, "\"abc\""))
        assertFalse(RangeDownloader.canResume(st, 3_000_000L, 3_000_000L, "\"other\""))
        assertFalse(RangeDownloader.canResume(st, 3_000_000L, 3_000_000L, ""))
        val noValidator = savedState(3_000_000L, "")
        assertFalse(RangeDownloader.canResume(noValidator, 3_000_000L, 3_000_000L, ""))
    }

    @Test
    fun validatorIsAStrongEtagElseTheDate() {
        assertEquals("\"abc\"", RangeDownloader.validatorFrom("\"abc\"", "Mon, 01 Jan 2026 00:00:00 GMT"))
        assertEquals("Mon, 01 Jan 2026 00:00:00 GMT", RangeDownloader.validatorFrom("W/\"weak\"", "Mon, 01 Jan 2026 00:00:00 GMT"))
        assertEquals("Mon, 01 Jan 2026 00:00:00 GMT", RangeDownloader.validatorFrom(null, "Mon, 01 Jan 2026 00:00:00 GMT"))
        assertEquals("", RangeDownloader.validatorFrom(null, null))
    }

    @Test
    fun theStateSurvivesBeingWrittenAndRead() {
        val st = savedState(3_000_000L, "\"abc\"")
        val back = RangeDownloader.State.parse(st.serialize())
        assertNotNull(back)
        back!!
        assertEquals(3_000_000L, back.total)
        assertEquals("\"abc\"", back.validator)
        assertTrue(back.has(0))
        assertFalse(back.has(1))
        assertEquals(500_000L, back.partialOf(2))
        assertEquals(0L, back.partialOf(1))
    }

    @Test
    fun aDamagedStateIsRefused() {
        assertNull(RangeDownloader.State.parse(null))
        assertNull(RangeDownloader.State.parse(""))
        assertNull(RangeDownloader.State.parse("rd2\n10\nv\n5\n\n"))
        assertNull(RangeDownloader.State.parse("rd1\nabc\nv\n5\n\n"))
        assertNull(RangeDownloader.State.parse("rd1\n0\nv\n5\n\n"))
    }

    @Test
    fun bytesAlreadyHeldAreCountedFromChunksAndPartials() {
        val st = savedState(3_000_000L, "v")
        // chunk 0 whole (1 MiB) + 500 000 bytes of chunk 2
        assertEquals((1L shl 20) + 500_000L, RangeDownloader.bytesHave(st, 3_000_000L))
    }

    @Test
    fun speedIsSmoothedAndIgnoresSamplesCloserThanHalfASecond() {
        val m = RangeDownloader.SpeedMeter()
        m.sample(0L, 0L)
        m.sample(100L, 999_999L)
        assertEquals(0L, m.bytesPerSecond())
        m.sample(1000L, 1_000_000L)
        assertEquals(1_000_000L, m.bytesPerSecond())
        m.sample(2000L, 1_000_000L)
        assertTrue(Math.abs(m.bytesPerSecond() - 600_000L) <= 1L)
    }

    @Test
    fun speedAndCacheNamesInTheUpdaterCore() {
        assertEquals("", AppUpdateCore.formatSpeed(0L))
        assertEquals("85 KB/s", AppUpdateCore.formatSpeed(85L * 1024L))
        assertEquals("1.5 MB/s", AppUpdateCore.formatSpeed(1_572_864L))
        val now = 100L * 24L * 3_600_000L
        assertTrue(AppUpdateCore.isStaleCacheFile("MudaFork-6.0.0.apk.part.state", now, now, "6.0.0"))
        assertTrue(AppUpdateCore.isStaleCacheFile("MudaFork-6.0.0.apk.part.state.tmp", now, now, "6.0.0"))
        assertFalse(AppUpdateCore.isStaleCacheFile("MudaFork-6.0.1.apk.part.state", now, now, "6.0.0"))
        assertEquals("6.0.1", AppUpdateCore.versionOfCacheFile("MudaFork-6.0.1.apk.part.state"))
    }

    // ---------------------------------------------------------------- the whole run against a local server

    private class Local(val data: ByteArray, val ranges: Boolean) {
        val server: HttpServer = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)

        init {
            server.createContext("/go") { ex ->
                ex.responseHeaders.add("Location", "/file")
                ex.sendResponseHeaders(302, -1)
                ex.close()
            }
            server.createContext("/file") { ex ->
                val range = ex.requestHeaders.getFirst("Range")
                ex.responseHeaders.add("ETag", "\"v1\"")
                if (range != null && ranges) {
                    val parts = range.removePrefix("bytes=").split("-")
                    val from = parts[0].toLong()
                    val to = minOf(data.size - 1L, parts[1].toLong())
                    ex.responseHeaders.add("Content-Range", "bytes $from-$to/${data.size}")
                    ex.sendResponseHeaders(206, to - from + 1)
                    ex.responseBody.use { it.write(data, from.toInt(), (to - from + 1).toInt()) }
                } else {
                    ex.sendResponseHeaders(200, data.size.toLong())
                    ex.responseBody.use { it.write(data) }
                }
            }
            server.start()
        }

        val url: String get() = "http://127.0.0.1:${server.address.port}/go"
        fun stop() = server.stop(0)
    }

    private val opener = RangeDownloader.Opener { url -> url.openConnection() as HttpURLConnection }
    private val localOnly = RangeDownloader.UrlCheck { it.startsWith("http://127.0.0.1") }

    private fun sample(size: Int): ByteArray = ByteArray(size).also { Random(7).nextBytes(it) }

    @Test
    fun aRangedServerIsReadOverSeveralConnectionsAndTheFileIsExact() {
        val data = sample(4_300_123)
        val server = Local(data, ranges = true)
        try {
            val out = File(tmp.root, "a.part")
            val state = File(tmp.root, "a.part.state")
            val result = RangeDownloader.fetch(server.url, out, state, 4, opener, localOnly, AtomicBoolean(false), null)
            assertTrue(result.ranged)
            assertTrue(result.connections > 1)
            assertEquals(data.size.toLong(), result.total)
            assertArrayEquals(data, out.readBytes())
            assertFalse(state.exists())
        } finally {
            server.stop()
        }
    }

    @Test
    fun aServerWithoutRangesIsReadOverOneConnection() {
        val data = sample(1_500_000)
        val server = Local(data, ranges = false)
        try {
            val out = File(tmp.root, "b.part")
            val result = RangeDownloader.fetch(server.url, out, File(tmp.root, "b.part.state"), 4, opener, localOnly, AtomicBoolean(false), null)
            assertFalse(result.ranged)
            assertEquals(1, result.connections)
            assertArrayEquals(data, out.readBytes())
        } finally {
            server.stop()
        }
    }

    @Test
    fun anAddressOutsideTheCheckIsRefusedBeforeAnyRequest() {
        val server = Local(sample(1000), ranges = true)
        try {
            val refused = RangeDownloader.UrlCheck { false }
            try {
                RangeDownloader.fetch(server.url, File(tmp.root, "c.part"), File(tmp.root, "c.part.state"), 4, opener, refused, AtomicBoolean(false), null)
                throw AssertionError("should have been refused")
            } catch (e: RangeDownloader.Refused) {
                // expected
            }
        } finally {
            server.stop()
        }
    }

    @Test
    fun aCancelledDownloadKeepsItsStateAndTheNextRunGoesOn() {
        val data = sample(4_300_123)
        val server = Local(data, ranges = true)
        try {
            val out = File(tmp.root, "d.part")
            val state = File(tmp.root, "d.part.state")
            val cancel = AtomicBoolean(true)  // cancelled from the start: nothing is fetched, the record is kept
            try {
                RangeDownloader.fetch(server.url, out, state, 4, opener, localOnly, cancel, null)
                throw AssertionError("should have been cancelled")
            } catch (e: RangeDownloader.Cancelled) {
                // expected
            }
            assertTrue(state.exists())
            val result = RangeDownloader.fetch(server.url, out, state, 4, opener, localOnly, AtomicBoolean(false), null)
            assertTrue(result.resumed)
            assertArrayEquals(data, out.readBytes())
        } finally {
            server.stop()
        }
    }
}
