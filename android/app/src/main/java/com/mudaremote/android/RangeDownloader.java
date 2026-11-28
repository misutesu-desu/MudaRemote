package com.mudaremote.android;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.RandomAccessFile;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.BitSet;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Fetches one file over several connections at once, the way download managers do: the file is cut
 * into chunks of one to eight megabytes and each connection takes the next chunk still to do, so a
 * slow connection holds up only its own chunk. A server that gives one connection only a few hundred
 * kilobytes a second (per-connection limits, latency) gives its full speed this way.
 *
 * <ul>
 * <li>A first one-byte range request learns the size, whether the server can cut the file, and where
 * the redirects end (the signed storage address is then asked directly).</li>
 * <li>A server that cannot cut the file (no ranges, size unknown) is read over one connection.</li>
 * <li>Progress is kept in a small state file beside the partial file (size, the server's ETag or
 * date, the chunks done, how far each begun chunk got). A later run goes on from it only when the size
 * is the same and the ETag (or date) is the same; anything else starts again.</li>
 * <li>Each chunk is tried again after a pause that grows (longer when the server says 429/503);
 * an attempt that brought bytes does not count against the tries.</li>
 * <li>Every address, also after each redirect, goes through {@link UrlCheck}.</li>
 * </ul>
 *
 * Plain Java (java.net only), so its pure parts run in JVM unit tests.
 */
public final class RangeDownloader {
    private RangeDownloader() {}

    /** Opens a connection to the address (timeouts, user agent). Redirects are followed here, not there. */
    public interface Opener { HttpURLConnection open(URL url) throws IOException; }

    /** Says whether an address may be contacted at all (checked on every hop of every redirect). */
    public interface UrlCheck { boolean trusted(String url); }

    /** Progress, from any thread: bytes done, total (-1 unknown), bytes per second (smoothed). */
    public interface Listener { void onProgress(long done, long total, long bytesPerSecond); }

    /** An address that failed the {@link UrlCheck}. */
    public static final class Refused extends IOException {
        public Refused() { super("The download address is not allowed."); }
    }

    /** An answer with an unwanted HTTP status. */
    public static final class Status extends IOException {
        public final int code;
        public Status(int code) { super("HTTP " + code); this.code = code; }
    }

    /** The download was cancelled by the caller (the partial file and its state are kept). */
    public static final class Cancelled extends IOException {
        public Cancelled() { super("cancelled"); }
    }

    /** What was learnt while downloading. */
    public static final class Result {
        public volatile long total = -1L;
        public volatile boolean ranged;
        public volatile boolean resumed;
        public volatile int connections = 1;
    }

    public static final int MAX_CONNECTIONS = 4;
    public static final int RETRIES = 5;
    static final long MIN_PER_CONNECTION = 512L * 1024L;
    static final long MIN_CHUNK = 1L << 20;
    static final long MAX_CHUNK = 8L << 20;
    private static final int MAX_REDIRECTS = 10;
    private static final long SAVE_EVERY_MS = 1500L;
    private static final long REPORT_EVERY_MS = 250L;
    private static final long ZERO_TAIL = 4096L;

    // ------------------------------------------------------------------ pure parts (unit tested)

    /** How many connections a file of this size is worth: one per 512 KB, at most [max], at least one. */
    public static int connectionsFor(long total, int max) {
        if (total <= 0L) return 1;
        long n = Math.min((long) Math.max(1, max), total / MIN_PER_CONNECTION);
        return (int) Math.max(1L, n);
    }

    /** About a quarter of each connection's share, between 1 and 8 MB. */
    public static long chunkSizeFor(long total, int connections) {
        long share = total / Math.max(1, connections * 4);
        return Math.max(MIN_CHUNK, Math.min(MAX_CHUNK, share));
    }

    public static int chunkCount(long total, long chunk) {
        if (total <= 0L || chunk <= 0L) return 0;
        return (int) ((total + chunk - 1L) / chunk);
    }

    /** First byte of chunk [index]. */
    public static long chunkStart(int index, long chunk) { return (long) index * chunk; }

    /** One past the last byte of chunk [index] (the last chunk is the short one). */
    public static long chunkEnd(int index, long chunk, long total) {
        return Math.min(total, (long) (index + 1) * chunk);
    }

    /** The total of "bytes 0-0/12345"; -1 when the header is absent or has no number after the slash. */
    public static long totalFromContentRange(String header) {
        if (header == null) return -1L;
        int slash = header.lastIndexOf('/');
        if (slash < 0) return -1L;
        try {
            long v = Long.parseLong(header.substring(slash + 1).trim());
            return v > 0L ? v : -1L;
        } catch (NumberFormatException e) {
            return -1L;
        }
    }

    /** What tells this version of the file from another: a strong ETag, else its date; "" when neither. */
    public static String validatorFrom(String etag, String lastModified) {
        if (etag != null && !etag.isEmpty() && !etag.startsWith("W/")) return etag;
        return lastModified == null ? "" : lastModified;
    }

    /** Pause before try number [attempt] (0 = the first retry): 0.4 s, 0.8 s, ... up to 8 s; three times longer for 429/503. */
    public static long backoffMillis(int attempt, int statusCode) {
        long base = Math.min(8000L, 400L * (Math.max(0, attempt) + 1L));
        return (statusCode == 429 || statusCode == 503) ? Math.min(24000L, base * 3L) : base;
    }

    /** A status worth trying again (the server or the network, not a refusal). */
    public static boolean isRetryableStatus(int code) {
        return code >= 500 || code == 429 || code == 408;
    }

    /** The progress kept between runs. Plain text: "rd1", total, validator, chunk, done chunks, begun chunks. */
    public static final class State {
        public long total;
        public long chunk;
        public String validator = "";
        public final BitSet done = new BitSet();
        /** Chunks begun but not finished: bytes from each chunk's start that are in the file already. */
        public final Map<Integer, Long> partial = new HashMap<>();

        public synchronized String serialize() {
            StringBuilder b = new StringBuilder("rd1\n").append(total).append('\n')
                    .append(validator.replace('\n', ' ')).append('\n').append(chunk).append('\n');
            for (int i = done.nextSetBit(0); i >= 0; i = done.nextSetBit(i + 1)) b.append(i).append(',');
            b.append('\n');
            for (Map.Entry<Integer, Long> e : partial.entrySet()) {
                if (e.getValue() > 0L && !done.get(e.getKey())) b.append(e.getKey()).append(':').append(e.getValue()).append(',');
            }
            return b.toString();
        }

        /** The state in [text]; null when it is not one (wrong header, missing numbers). */
        public static State parse(String text) {
            if (text == null) return null;
            try {
                String[] l = text.split("\n", -1);
                if (l.length < 5 || !"rd1".equals(l[0])) return null;
                State s = new State();
                s.total = Long.parseLong(l[1].trim());
                s.validator = l[2].trim();
                s.chunk = Long.parseLong(l[3].trim());
                for (String n : l[4].split(",")) {
                    if (!n.trim().isEmpty()) s.done.set(Integer.parseInt(n.trim()));
                }
                if (l.length > 5) {
                    for (String kv : l[5].split(",")) {
                        int c = kv.indexOf(':');
                        if (c > 0) {
                            try {
                                s.partial.put(Integer.parseInt(kv.substring(0, c).trim()), Long.parseLong(kv.substring(c + 1).trim()));
                            } catch (NumberFormatException ignored) {
                                // one damaged entry: that chunk starts from its beginning
                            }
                        }
                    }
                }
                return s.total > 0L && s.chunk > 0L ? s : null;
            } catch (RuntimeException e) {
                return null;
            }
        }

        static State read(File f) {
            if (f == null || !f.isFile()) return null;
            try {
                return parse(new String(Files.readAllBytes(f.toPath()), StandardCharsets.UTF_8));
            } catch (IOException e) {
                return null;
            }
        }

        synchronized void write(File f) {
            if (f == null) return;
            File tmp = new File(f.getPath() + ".tmp");
            try {
                Files.write(tmp.toPath(), serialize().getBytes(StandardCharsets.UTF_8));
                if (!tmp.renameTo(f)) {
                    f.delete();
                    tmp.renameTo(f);
                }
            } catch (IOException ignored) {
                // a state that cannot be written only costs the resume
            }
        }

        public synchronized void mark(int i) { done.set(i); partial.remove(Integer.valueOf(i)); }
        public synchronized void unmark(int i) { done.clear(i); }
        public synchronized boolean has(int i) { return done.get(i); }
        public synchronized long partialOf(int i) { Long v = partial.get(i); return v == null ? 0L : v; }
        public synchronized void setPartial(int i, long v) {
            if (v > 0L) partial.put(i, v); else partial.remove(Integer.valueOf(i));
        }
    }

    /**
     * Whether a run may go on from the recorded state: the record is there, the size is the same, the
     * partial file has exactly that size, and the server's ETag (or date) is the same one as before.
     * No validator on either side means the version cannot be told, so it starts again.
     */
    public static boolean canResume(State prev, long total, long fileLength, String validator) {
        return prev != null
                && prev.chunk > 0L
                && prev.total == total
                && fileLength == total
                && validator != null && !validator.isEmpty()
                && validator.equals(prev.validator);
    }

    /** Bytes already in the file by the state: whole chunks done plus the begun part of the others. */
    public static long bytesHave(State st, long total) {
        long have = 0L;
        int chunks = chunkCount(total, st.chunk);
        for (int i = 0; i < chunks; i++) {
            long size = chunkEnd(i, st.chunk, total) - chunkStart(i, st.chunk);
            if (st.has(i)) have += size; else have += Math.min(st.partialOf(i), size);
        }
        return have;
    }

    /** A smoothed bytes-per-second figure from byte counts sampled over time. */
    public static final class SpeedMeter {
        private long lastMs = -1L;
        private long lastBytes;
        private double speed;

        /** Feed the running byte count at [nowMs]; samples closer than half a second are skipped. */
        public synchronized void sample(long nowMs, long bytes) {
            if (lastMs < 0L) {
                lastMs = nowMs;
                lastBytes = bytes;
                return;
            }
            long dt = nowMs - lastMs;
            if (dt < 500L) return;
            double inst = (bytes - lastBytes) * 1000.0 / dt;
            speed = speed == 0.0 ? inst : speed * 0.6 + inst * 0.4;
            lastMs = nowMs;
            lastBytes = bytes;
        }

        public synchronized long bytesPerSecond() { return (long) Math.max(0.0, speed); }
    }

    // ------------------------------------------------------------------ the download

    /**
     * Downloads [url] into [out] (a ".part" file the caller renames when the call returns). [stateFile]
     * keeps the progress between runs. Throws {@link Refused}, {@link Status}, {@link Cancelled} or another
     * IOException; on any of them the partial file and the state are left for the next run (the caller
     * deletes them when it wants a fresh start).
     */
    public static Result fetch(String url, File out, File stateFile, int maxConnections, Opener opener,
                               UrlCheck check, AtomicBoolean cancelled, Listener listener) throws IOException {
        final Result res = new Result();
        final AtomicLong got = new AtomicLong(0L);
        final SpeedMeter meter = new SpeedMeter();
        final Reporter reporter = new Reporter(res, got, meter, listener, cancelled);

        // One byte first: the size, the ranges, the validator, and where the redirects end.
        URL[] at = { new URL(url) };
        HttpURLConnection probe = follow(new URL(url), opener, check, "bytes=0-0", at);
        int code = probe.getResponseCode();
        String contentRange = probe.getHeaderField("Content-Range");
        long total = code == 206 ? totalFromContentRange(contentRange) : -1L;
        res.ranged = code == 206 && total > 0L;
        if (code == 200) {
            // The server ignored the range and sends the whole file: read it from this answer.
            res.total = parseLength(probe.getHeaderField("Content-Length"));
            discardState(stateFile);
            readWhole(probe, out, res, got, reporter, cancelled);
            return res;
        }
        if (!res.ranged) {
            probe.disconnect();
            if (code >= 400 && code != 416) throw new Status(code);
            HttpURLConnection c = follow(new URL(url), opener, check, null, null);
            int rc = c.getResponseCode();
            if (rc >= 400) {
                c.disconnect();
                throw new Status(rc);
            }
            res.total = parseLength(c.getHeaderField("Content-Length"));
            discardState(stateFile);
            readWhole(c, out, res, got, reporter, cancelled);
            return res;
        }
        res.total = total;
        final String validator = validatorFrom(probe.getHeaderField("ETag"), probe.getHeaderField("Last-Modified"));
        drain(probe);
        final URL direct = at[0];
        final int n = connectionsFor(total, maxConnections);
        res.connections = n;

        State prev = out.isFile() ? State.read(stateFile) : null;
        final State st;
        if (canResume(prev, total, out.length(), validator)) {
            localCheck(prev, out);
            st = prev;
            res.resumed = true;
        } else {
            st = new State();
            st.total = total;
            st.chunk = chunkSizeFor(total, n);
            st.validator = validator;
            try (RandomAccessFile raf = new RandomAccessFile(out, "rw")) {
                raf.setLength(0L);
                raf.setLength(total);
            }
        }
        final long chunk = st.chunk;
        final int chunks = chunkCount(total, chunk);
        got.set(bytesHave(st, total));
        st.write(stateFile);
        reporter.tick(true);

        final AtomicInteger next = new AtomicInteger(0);
        final AtomicReference<IOException> fail = new AtomicReference<>();
        final long[] lastSave = { System.currentTimeMillis() };
        final URL original = new URL(url);
        Thread[] workers = new Thread[n];
        for (int w = 0; w < n; w++) {
            workers[w] = new Thread(() -> {
                try (RandomAccessFile raf = new RandomAccessFile(out, "rw")) {
                    while (fail.get() == null && !cancelled.get()) {
                        int idx = next.getAndIncrement();
                        while (idx < chunks && st.has(idx)) idx = next.getAndIncrement();
                        if (idx >= chunks) break;
                        fetchChunk(idx, chunk, total, st, raf, direct, original, opener, check, cancelled, got,
                                reporter, stateFile, lastSave);
                    }
                } catch (IOException e) {
                    fail.compareAndSet(null, e);
                } catch (RuntimeException e) {
                    fail.compareAndSet(null, new IOException(e.getClass().getSimpleName()));
                }
            }, "range-download-" + w);
            workers[w].start();
        }
        try {
            for (Thread t : workers) t.join();
        } catch (InterruptedException e) {
            cancelled.set(true);
            Thread.currentThread().interrupt();
        }
        st.write(stateFile);
        if (cancelled.get()) throw new Cancelled();
        if (fail.get() != null) throw fail.get();
        for (int i = 0; i < chunks; i++) {
            if (!st.has(i)) throw new IOException("incomplete (chunk " + i + " of " + chunks + ")");
        }
        if (out.length() != total) throw new IOException("incomplete (" + out.length() + " of " + total + ")");
        reporter.tick(true);
        discardState(stateFile);
        return res;
    }

    private static void fetchChunk(int idx, long chunk, long total, State st, RandomAccessFile raf, URL direct,
                                   URL original, Opener opener, UrlCheck check, AtomicBoolean cancelled,
                                   AtomicLong got, Reporter reporter, File stateFile, long[] lastSave)
            throws IOException {
        final long start = chunkStart(idx, chunk);
        final long end = chunkEnd(idx, chunk, total);  // exclusive
        long pos = start + Math.min(st.partialOf(idx), end - start - 1L);
        int attempt = 0;
        while (pos < end) {
            if (cancelled.get()) throw new Cancelled();
            // The signed address may have run out: after two failures the first address again, redirects and all.
            URL u = attempt >= 2 ? original : direct;
            HttpURLConnection c = null;
            long wrote = 0L;
            int statusSeen = 0;
            final long tryFrom = pos;
            try {
                c = follow(u, opener, check, "bytes=" + pos + "-" + (end - 1L), null);
                int rc = c.getResponseCode();
                statusSeen = rc;
                if (rc != 206) throw new Status(rc);
                try (InputStream in = c.getInputStream()) {
                    byte[] buf = new byte[64 * 1024];
                    while (pos + wrote < end) {
                        if (cancelled.get()) throw new Cancelled();
                        int want = (int) Math.min(buf.length, end - (pos + wrote));
                        int r = in.read(buf, 0, want);
                        if (r <= 0) break;
                        raf.seek(pos + wrote);
                        raf.write(buf, 0, r);
                        wrote += r;
                        got.addAndGet(r);
                        st.setPartial(idx, pos + wrote - start);
                        long now = System.currentTimeMillis();
                        synchronized (lastSave) {
                            if (now - lastSave[0] > 3000L) {
                                lastSave[0] = now;
                                st.write(stateFile);
                            }
                        }
                        reporter.tick(false);
                    }
                }
                pos += wrote;
                wrote = 0L;  // counted: the handler below must not add it again
                if (pos < end) throw new IOException("Connection closed early");
            } catch (Cancelled e) {
                pos += wrote;
                st.setPartial(idx, pos - start);
                throw e;
            } catch (Refused e) {
                throw e;
            } catch (IOException e) {
                // What came before the break is in the file already: the next try goes on from there.
                pos += wrote;
                st.setPartial(idx, pos - start);
                boolean moved = pos > tryFrom;
                if (e instanceof Status) {
                    statusSeen = ((Status) e).code;
                    if (!isRetryableStatus(statusSeen)) throw e;
                }
                if (moved) {
                    attempt = 0;  // a weak link that drops every few hundred KB still gets there
                } else {
                    attempt++;
                    if (attempt > RETRIES) throw e;
                }
                sleepOrCancel(moved ? 250L : backoffMillis(attempt - 1, statusSeen), cancelled);
                continue;
            } finally {
                if (c != null) c.disconnect();
            }
            attempt = 0;
        }
        st.mark(idx);
        long now = System.currentTimeMillis();
        synchronized (lastSave) {
            if (now - lastSave[0] > SAVE_EVERY_MS) {
                lastSave[0] = now;
                st.write(stateFile);
            }
        }
    }

    private static void sleepOrCancel(long millis, AtomicBoolean cancelled) throws IOException {
        long waited = 0L;
        while (waited < millis) {
            if (cancelled.get()) throw new Cancelled();
            try {
                Thread.sleep(Math.min(250L, millis - waited));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new Cancelled();
            }
            waited += 250L;
        }
    }

    /** One connection, the whole file (no ranges, or the answer to the first request was the file). */
    private static void readWhole(HttpURLConnection c, File out, Result res, AtomicLong got, Reporter reporter,
                                  AtomicBoolean cancelled) throws IOException {
        res.connections = 1;
        got.set(0L);
        reporter.tick(true);
        try (InputStream in = c.getInputStream(); RandomAccessFile raf = new RandomAccessFile(out, "rw")) {
            raf.setLength(0L);
            byte[] buf = new byte[64 * 1024];
            long written = 0L;
            while (true) {
                if (cancelled.get()) throw new Cancelled();
                int r = in.read(buf);
                if (r < 0) break;
                raf.write(buf, 0, r);
                written += r;
                got.addAndGet(r);
                reporter.tick(false);
            }
            if (res.total >= 0L && written != res.total) throw new IOException("Incomplete download");
            if (res.total < 0L) res.total = written;
        } finally {
            c.disconnect();
        }
        reporter.tick(true);
    }

    /** Done chunks whose last bytes are all zero were never really written (the app was stopped first): fetched again. */
    static void localCheck(State st, File out) {
        try (RandomAccessFile raf = new RandomAccessFile(out, "r")) {
            int chunks = chunkCount(st.total, st.chunk);
            byte[] b = new byte[(int) ZERO_TAIL];
            for (int i = st.done.nextSetBit(0); i >= 0 && i < chunks; i = st.done.nextSetBit(i + 1)) {
                long end = chunkEnd(i, st.chunk, st.total);
                long from = end - Math.min(ZERO_TAIL, end - chunkStart(i, st.chunk));
                if (allZero(raf, from, b)) st.unmark(i);
            }
            for (Map.Entry<Integer, Long> e : new java.util.ArrayList<>(st.partial.entrySet())) {
                long p = e.getValue();
                long at = chunkStart(e.getKey(), st.chunk) + p;
                if (p < ZERO_TAIL || allZero(raf, at - ZERO_TAIL, b)) st.setPartial(e.getKey(), 0L);
            }
        } catch (IOException ignored) {
            // the file cannot be read: the checks above simply do not apply
        }
    }

    private static boolean allZero(RandomAccessFile raf, long at, byte[] b) throws IOException {
        raf.seek(Math.max(0L, at));
        int r = raf.read(b);
        if (r <= 0) return true;
        for (int k = 0; k < r; k++) if (b[k] != 0) return false;
        return true;
    }

    // ------------------------------------------------------------------ connections

    /**
     * A connection to [url] with its redirects followed here, every hop checked. [at][0] receives the
     * address the redirects ended at (when the caller asks for it).
     */
    static HttpURLConnection follow(URL url, Opener opener, UrlCheck check, String range, URL[] at) throws IOException {
        for (int hop = 0; hop < MAX_REDIRECTS; hop++) {
            if (!check.trusted(url.toString())) throw new Refused();
            HttpURLConnection c = opener.open(url);
            c.setInstanceFollowRedirects(false);
            c.setRequestProperty("Accept-Encoding", "identity");
            if (range != null) c.setRequestProperty("Range", range);
            int code;
            try {
                code = c.getResponseCode();
            } catch (IOException e) {
                c.disconnect();
                throw e;
            }
            String loc = code >= 300 && code < 400 ? c.getHeaderField("Location") : null;
            if (loc == null) {
                if (at != null) at[0] = url;
                return c;
            }
            c.disconnect();
            url = new URL(url, loc);
        }
        throw new IOException("Too many redirects");
    }

    private static void drain(HttpURLConnection c) {
        try (InputStream in = c.getInputStream()) {
            byte[] b = new byte[256];
            while (in.read(b) > 0) {
                // the one byte: read to the end so the connection can be reused
            }
        } catch (Exception ignored) {
            // nothing to do
        }
    }

    private static long parseLength(String header) {
        try {
            return header == null ? -1L : Long.parseLong(header.trim());
        } catch (NumberFormatException e) {
            return -1L;
        }
    }

    private static void discardState(File stateFile) {
        if (stateFile == null) return;
        stateFile.delete();
        new File(stateFile.getPath() + ".tmp").delete();
    }

    /** Hands the progress to the listener at most four times a second and keeps the speed figure. */
    private static final class Reporter {
        private final Result res;
        private final AtomicLong got;
        private final SpeedMeter meter;
        private final Listener listener;
        private final AtomicBoolean cancelled;
        private long lastReport;

        Reporter(Result res, AtomicLong got, SpeedMeter meter, Listener listener, AtomicBoolean cancelled) {
            this.res = res;
            this.got = got;
            this.meter = meter;
            this.listener = listener;
            this.cancelled = cancelled;
        }

        synchronized void tick(boolean force) {
            long now = System.currentTimeMillis();
            long bytes = got.get();
            meter.sample(now, bytes);
            if (listener == null || cancelled.get()) return;
            if (!force && now - lastReport < REPORT_EVERY_MS) return;
            lastReport = now;
            listener.onProgress(bytes, res.total, meter.bytesPerSecond());
        }
    }
}
