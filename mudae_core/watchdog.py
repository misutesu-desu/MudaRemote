"""Connection watchdog for a runtime instance.

A Discord client can end up half dead: the gateway socket was closed by Discord, nothing reads it any
more, the library never reconnects and the process keeps running with no error at all. The bot then sits
"online" while it neither rolls nor claims. The library's own reconnect logic and the bot's health task
live on the same event loop that got stuck, so neither can notice.

This watchdog runs on its own thread and only reads state, so it does not depend on that loop:

  * gateway silence: no frame (heartbeat ack or dispatch) for ``stale_after`` seconds, or no keep-alive
    handler at all for that long;
  * a blocked loop: a callback posted to the loop is not executed within ``stale_after`` seconds.

On a trip it first asks the instance for a clean reconnect (``soft_restart``). If the instance is not
healthy again within ``recover_timeout`` it calls ``fatal`` (the worker process exits and the Cloud
restarts the instance); hosts that cannot exit, such as the desktop app, keep retrying the soft restart.
"""

import threading
import time

DEFAULT_INTERVAL = 15.0
DEFAULT_STALE_AFTER = 120.0      # heartbeat is ~41 s and the library gives up at 60 s, so this is generous
DEFAULT_RECOVER_TIMEOUT = 120.0
CONFIRMATIONS = 2                # consecutive bad checks before acting


class ConnectionWatchdog:
    def __init__(self, instance, *, interval=DEFAULT_INTERVAL, stale_after=DEFAULT_STALE_AFTER,
                 recover_timeout=DEFAULT_RECOVER_TIMEOUT, fatal=None, clock=time.monotonic,
                 perf=time.perf_counter):
        self.instance = instance
        self.interval = interval
        self.stale_after = stale_after
        self.recover_timeout = recover_timeout
        self.fatal = fatal
        self._clock = clock
        self._perf = perf
        self._stop = threading.Event()
        self._thread = None
        self._reset()

    def _reset(self):
        self._client = None
        self._no_keepalive_since = None
        self._probe_sent = None
        self._probe_done = threading.Event()
        self._bad = 0

    # ---- lifecycle -------------------------------------------------------------------------
    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"Watchdog-{self.instance.instance_id}",
                                        daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.wait(self.interval):
            try:
                self.check()
            except Exception:
                pass                        # a watchdog must never take the instance down by itself

    # ---- one check -------------------------------------------------------------------------
    def problem(self):
        """Why the connection looks dead right now, or None. Only reads state."""
        client, loop = self.instance.watch_target()
        if client is None or loop is None:
            self._reset()                   # nothing running yet: a fresh client gets a fresh start
            return None
        if client is not self._client:
            self._reset()
            self._client = client
        now = self._clock()

        if loop.is_closed():
            return "the event loop is closed"
        if self._probe_sent is not None and not self._probe_done.is_set():
            if now - self._probe_sent > self.stale_after:
                return "the event loop is blocked"
        else:
            self._probe_done = done = threading.Event()
            self._probe_sent = now
            try:
                loop.call_soon_threadsafe(done.set)
            except RuntimeError:
                return "the event loop is closed"

        ws = getattr(client, "ws", None)
        keepalive = getattr(ws, "_keep_alive", None) if ws is not None else None
        last_recv = getattr(keepalive, "_last_recv", None)
        if isinstance(last_recv, (int, float)):
            self._no_keepalive_since = None
            silent = self._perf() - last_recv
            if silent > self.stale_after:
                return f"no word from Discord for {int(silent)}s"
            return None
        if self._no_keepalive_since is None:
            self._no_keepalive_since = now
        if now - self._no_keepalive_since > self.stale_after:
            return "the Discord gateway is not connected"
        return None

    def check(self):
        if self.instance.stopping():
            return
        reason = self.problem()
        if reason is None:
            self._bad = 0
            return
        self._bad += 1
        if self._bad < CONFIRMATIONS:
            return
        self._recover(reason)

    # ---- recovery --------------------------------------------------------------------------
    def _recover(self, reason):
        old = self._client
        self.instance.watchdog_event("watchdog_reconnect", reason, "soft")
        self.instance.soft_restart()
        deadline = self._clock() + self.recover_timeout
        while self._clock() < deadline:
            if self._stop.wait(2.0) or self.instance.stopping():
                return
            client, _ = self.instance.watch_target()
            if client is not None and client is not old and self.instance.is_running():
                self._reset()
                self.instance.watchdog_event("watchdog_recovered", "Connection restored", "soft")
                return
        self._bad = 0
        self.instance.watchdog_event("watchdog_restart", reason, "hard")
        if self.fatal is not None:
            self.fatal(reason)
        # no way to exit (desktop): the next checks retry the soft restart
