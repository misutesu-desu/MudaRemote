"""Rate-conscious background delivery for optional Discord webhook logs."""

import queue
import threading
import time


class WebhookDispatcher:
    _queue = queue.Queue(maxsize=2000)
    _started = False
    _start_lock = threading.Lock()

    @classmethod
    def enqueue(cls, url, line):
        url = str(url or "").strip()
        if not url:
            return
        cls._ensure_started()
        try:
            cls._queue.put_nowait((url, str(line or "")))
        except queue.Full:
            # Remote logging must never block or crash the bot.
            pass

    @classmethod
    def _ensure_started(cls):
        if cls._started:
            return
        with cls._start_lock:
            if cls._started:
                return
            threading.Thread(target=cls._worker, name="MudaRemoteWebhook", daemon=True).start()
            cls._started = True

    @classmethod
    def _worker(cls):
        import requests

        pending = {}
        last_flush = time.monotonic()
        while True:
            timeout = max(0.1, 1.5 - (time.monotonic() - last_flush))
            try:
                url, line = cls._queue.get(timeout=timeout)
                pending.setdefault(url, []).append(line)
            except queue.Empty:
                pass

            now = time.monotonic()
            if not pending or (now - last_flush < 1.5 and all(
                sum(len(line) + 1 for line in lines) < 1500
                for lines in pending.values()
            )):
                continue

            batches, pending = pending, {}
            last_flush = now
            for url, lines in batches.items():
                payload_text = "\n".join(lines)
                while payload_text:
                    chunk = payload_text[:1800]
                    payload_text = payload_text[1800:]
                    try:
                        requests.post(
                            url,
                            json={"content": "```text\n{}\n```".format(chunk)},
                            timeout=(3.05, 6.0),
                        )
                    except Exception:
                        # Webhook failures remain isolated from game automation.
                        break
