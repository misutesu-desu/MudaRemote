import asyncio
import threading
import time
import unittest
from types import SimpleNamespace

from mudae_core.watchdog import ConnectionWatchdog


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class LoopThread:
    """A real event loop on its own thread, like the one a bot client runs on."""
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()

    def block(self, seconds):
        self.loop.call_soon_threadsafe(time.sleep, seconds)

    def close(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(2)
        self.loop.close()


def make_client(perf, last_recv_ago=0.0, keepalive=True):
    keep = SimpleNamespace(_last_recv=perf() - last_recv_ago) if keepalive else None
    return SimpleNamespace(ws=SimpleNamespace(_keep_alive=keep))


class FakeInstance:
    instance_id = "fake"

    def __init__(self, client, loop):
        self.client, self.loop = client, loop
        self.events, self.soft = [], 0
        self.stop_flag, self.running = False, True

    def watch_target(self):
        return self.client, self.loop

    def stopping(self):
        return self.stop_flag

    def is_running(self):
        return self.running

    def watchdog_event(self, kind, reason, stage):
        self.events.append((kind, stage))

    def soft_restart(self):
        self.soft += 1


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.perf = Clock(), Clock()
        self.looper = LoopThread()
        self.addCleanup(self.looper.close)

    def dog(self, instance, **kw):
        return ConnectionWatchdog(instance, stale_after=60, recover_timeout=20, clock=self.clock,
                                  perf=self.perf, **kw)

    def settle(self):
        time.sleep(0.05)            # let the probe callback run on the loop thread

    def test_healthy_connection_is_left_alone(self):
        inst = FakeInstance(make_client(self.perf, 5), self.looper.loop)
        dog = self.dog(inst)
        for _ in range(5):
            self.assertIsNone(dog.problem())
            self.settle()
            self.clock.now += 15
            self.perf.now += 15
            inst.client.ws._keep_alive._last_recv = self.perf()     # acks keep coming
            dog.check()
        self.assertEqual((inst.soft, inst.events), (0, []))

    def test_silent_gateway_is_repaired_only_after_it_is_confirmed(self):
        inst = FakeInstance(make_client(self.perf, 90), self.looper.loop)
        dog = self.dog(inst)
        dog.fatal = lambda reason: self.fail("a soft restart should be tried first")
        self.assertIn("no word from Discord", dog.problem())
        dog._bad = 0
        stop = threading.Event()

        def recover():                  # a new client appears and becomes healthy
            self.clock.now += 1
            inst.client = make_client(self.perf, 0)

        dog._stop = SimpleNamespace(wait=lambda t: recover() or stop.is_set(), is_set=lambda: False)
        dog.check()
        self.assertEqual(inst.soft, 0)                                # first bad check: wait for a second
        dog.check()
        self.assertEqual(inst.soft, 1)
        self.assertEqual(inst.events, [("watchdog_reconnect", "soft"), ("watchdog_recovered", "soft")])

    def test_unrecovered_client_escalates_to_fatal_once(self):
        inst = FakeInstance(make_client(self.perf, 500), self.looper.loop)
        reasons = []
        dog = self.dog(inst, fatal=reasons.append)
        dog._stop = SimpleNamespace(wait=lambda t: self.clock.__setattr__("now", self.clock.now + 10) or False)
        dog.check()
        dog.check()
        self.assertEqual(inst.soft, 1)
        self.assertEqual([stage for _, stage in inst.events], ["soft", "hard"])
        self.assertEqual(len(reasons), 1)

    def test_no_keepalive_for_too_long_counts_as_disconnected(self):
        inst = FakeInstance(make_client(self.perf, keepalive=False), self.looper.loop)
        dog = self.dog(inst)
        self.assertIsNone(dog.problem())
        self.clock.now += 61
        self.assertIn("not connected", dog.problem())

    def test_blocked_event_loop_is_detected(self):
        inst = FakeInstance(make_client(self.perf, 1), self.looper.loop)
        dog = self.dog(inst)
        self.looper.block(1.0)
        self.assertIsNone(dog.problem())                              # probe posted, not yet overdue
        self.clock.now += 61
        self.assertIn("blocked", dog.problem())

    def test_nothing_happens_while_there_is_no_client_or_while_stopping(self):
        inst = FakeInstance(None, None)
        dog = self.dog(inst)
        for _ in range(4):
            dog.check()
        inst.client, inst.loop = make_client(self.perf, 500), self.looper.loop
        inst.stop_flag = True
        for _ in range(4):
            dog.check()
        self.assertEqual((inst.soft, inst.events), (0, []))

    def test_a_fresh_client_gets_a_fresh_grace_period(self):
        inst = FakeInstance(make_client(self.perf, keepalive=False), self.looper.loop)
        dog = self.dog(inst)
        dog.problem()
        self.clock.now += 50
        inst.client = make_client(self.perf, keepalive=False)        # reconnected with a new client
        self.assertIsNone(dog.problem())
        self.clock.now += 50
        self.assertIsNone(dog.problem())


if __name__ == "__main__":
    unittest.main()
