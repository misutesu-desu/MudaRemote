from collections import deque
from concurrent.futures import Future
import threading
import unittest
from unittest.mock import Mock

from mudae_core.cloud_protocol import PROTOCOL_VERSION
from mudae_core.cloud_worker import CloudError, CloudWorker, RequestsTransport


def command(number, instance="one"):
    return {"command_id": str(number), "user_id": "user", "instance_id": instance,
            "action": "start", "preset_name": "preset", "preset_data": {},
            "credentials": {"token": "secret"}}


class TransportTests(unittest.TestCase):
    def test_url_validation(self):
        for url in ("http://example.com", "https://a:b@example.com", "https://example.com?",
                    "https://example.com#", "https://example.com/x?q=x", "https://",
                    "https://example.com\\other", "https://example.com\n"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                RequestsTransport(url, "token", "worker")

    def test_contract(self):
        session = Mock()
        session.post.return_value.status_code = 200
        session.post.return_value.json.return_value = {"commands": [command(1)]}
        transport = RequestsTransport("https://example.com/api/", "token", "worker", session=session,
                                      boot_id="boot", worker_version="1.2.3")
        self.assertEqual(transport.poll(), [command(1)])
        identity = {"worker_id": "worker", "boot_id": "boot", "worker_version": "1.2.3",
                    "protocol_version": PROTOCOL_VERSION}
        session.post.assert_called_with(
            "https://example.com/api/poll", json=identity,
            headers={"Authorization": "Bearer token"}, timeout=(5.0, 30.0), allow_redirects=False)
        transport.report([{"record_id": "stable"}])
        self.assertEqual(session.post.call_args.kwargs["json"],
                         dict(identity, records=[{"record_id": "stable"}]))
        for status in (302, 401, 500):
            session.post.return_value.status_code = status
            with self.assertRaises(CloudError):
                transport.report([])

    def test_invalid_poll(self):
        session = Mock()
        session.post.return_value.status_code = 200
        transport = RequestsTransport("https://example.com", "token", "worker", session=session)
        for payload in ({}, [], {"commands": [{}]}, {"commands": [command(i) for i in range(33)]}):
            session.post.return_value.json.return_value = payload
            with self.assertRaises(CloudError):
                transport.poll()


class WorkerTests(unittest.TestCase):
    def make_worker(self, **kwargs):
        supervisor = Mock()
        supervisor.drain_records = Mock(spec=lambda *, limit: [], return_value=[])
        supervisor.health.return_value = {"healthy": True}
        supervisor.execute.return_value = {"success": True}
        transport = Mock()
        transport.poll.return_value = []
        worker = CloudWorker(supervisor, transport, **kwargs)
        self.addCleanup(worker.close)
        return worker, supervisor, transport

    def test_report_retry_preserves_ids_and_backpressure(self):
        worker, _, transport = self.make_worker(max_commands=2, max_inflight=1, max_records=4)
        worker.next_health = float("inf")
        for i in range(3):
            worker._record("event", {"n": i})
        original = list(worker.records)
        transport.report.side_effect = RuntimeError("secret")
        worker.tick()
        transport.poll.assert_not_called()
        self.assertEqual(list(worker.records), original)
        transport.report.side_effect = None
        worker.next_report = 0
        worker.tick()
        self.assertEqual(transport.report.call_args.args[0], original)
        self.assertFalse(worker.records)

    def test_instances_are_serial_and_poll_is_nonblocking(self):
        worker, supervisor, transport = self.make_worker(max_workers=2, max_inflight=2)
        release = threading.Event()
        started = threading.Event()
        self.addCleanup(release.set)
        def execute(item):
            started.set()
            release.wait(2)
            return {"success": True}
        supervisor.execute.side_effect = execute
        transport.poll.return_value = [command(1), command(2), command(3, "two")]
        worker.tick()
        self.assertTrue(started.wait(1))
        self.assertEqual(len(worker.futures), 2)
        self.assertEqual([item["command_id"] for item in worker.commands], ["2"])
        self.assertEqual(len(worker.busy), 2)
        release.set()

    def test_busy_instance_keeps_fifo_when_other_instance_fills_capacity(self):
        worker, supervisor, _ = self.make_worker(max_workers=2, max_inflight=2)
        submitted = []

        def submit(execute, item):
            future = Future()
            submitted.append(item["command_id"])
            self.addCleanup(lambda: future.set_result({"success": True})
                            if not future.done() else None)
            return future

        worker.executor.submit = Mock(side_effect=submit)
        worker.commands.append(command("A1"))
        worker._dispatch()
        first = next(iter(worker.futures))
        worker.commands.extend([command("A2"), command("B1", "two"), command("A3")])
        worker._dispatch()
        self.assertEqual(submitted, ["A1", "B1"])
        self.assertEqual([item["command_id"] for item in worker.commands], ["A2", "A3"])
        worker._dispatch()
        self.assertEqual([item["command_id"] for item in worker.commands], ["A2", "A3"])
        first.set_result({"success": True})
        worker._collect()
        worker._dispatch()
        self.assertEqual(submitted, ["A1", "B1", "A2"])
        second = next(future for future, item in worker.futures.items()
                      if item["command_id"] == "A2")
        second.set_result({"success": True})
        worker._collect()
        worker._dispatch()
        self.assertEqual(submitted, ["A1", "B1", "A2", "A3"])

    def test_execution_error_is_sanitized(self):
        worker, supervisor, transport = self.make_worker()
        supervisor.execute.side_effect = RuntimeError("credentials-secret")
        transport.poll.return_value = [command(1)]
        worker.tick()
        for future in worker.futures:
            try:
                future.result(timeout=1)
            except RuntimeError:
                pass
        worker._collect()
        result = [r for r in worker.records if r["type"] == "command_result"][0]
        self.assertEqual(result["data"], {"success": False, "error": "execution_failed"})
        self.assertNotIn("credentials-secret", str(result))

    def test_poll_backoff_and_health(self):
        now = [10.0]
        worker, supervisor, transport = self.make_worker(clock=lambda: now[0])
        transport.poll.side_effect = RuntimeError("secret")
        worker.tick()
        worker.tick()
        self.assertEqual(transport.poll.call_count, 1)
        self.assertEqual(supervisor.health.call_count, 1)
        now[0] += 1
        worker.tick()
        self.assertEqual(transport.poll.call_count, 2)
        self.assertEqual(worker.next_poll, 13.0)

    def test_shutdown_reports_queued_commands(self):
        worker, supervisor, transport = self.make_worker()
        worker.commands.append(command(1))
        worker.close()
        records = transport.report.call_args.args[0]
        self.assertEqual(records[0]["data"]["error"], "worker_stopped")
        supervisor.close.assert_called_once()
        transport.close.assert_called_once()

    def test_telemetry_backpressure_drains_only_available_capacity(self):
        worker, supervisor, transport = self.make_worker(
            max_commands=2, max_inflight=1, max_records=4)
        pending = deque({"event": i} for i in range(6))
        supervisor.drain_records.side_effect = lambda *, limit: [
            pending.popleft() for _ in range(min(limit, len(pending)))]
        future = Future()
        self.addCleanup(lambda: future.set_result({"success": True})
                        if not future.done() else None)
        worker.futures[future] = command(1)
        worker.busy.add(("user", "one"))
        worker.commands.append(command(2))
        worker._record("event", {"event": "existing"})
        transport.report.side_effect = RuntimeError("offline")
        worker.tick()
        supervisor.drain_records.assert_called_once_with(limit=1)
        self.assertEqual(len(pending), 5)
        self.assertEqual(len(worker.records), 2)
        self.assertFalse(worker.stop_event.is_set())
        supervisor.health.assert_not_called()
        worker.tick()
        supervisor.drain_records.assert_called_once_with(limit=1)
        transport.poll.assert_not_called()
        transport.report.side_effect = None
        worker.next_report = 0
        worker.tick()
        supervisor.drain_records.assert_called_with(limit=2)
        self.assertEqual(len(pending), 3)
        self.assertEqual(len(worker.records), 2)
        self.assertFalse(worker.closed)
        supervisor.drain_records.side_effect = None

    def test_oversized_telemetry_fails_without_growing_buffer(self):
        worker, supervisor, _ = self.make_worker(max_commands=1, max_inflight=1, max_records=3)
        supervisor.drain_records.return_value = [{"event": i} for i in range(4)]
        with self.assertRaises(CloudError):
            worker.tick()
        self.assertEqual(len(worker.records), 0)
        supervisor.drain_records = Mock(spec=lambda *, limit: [], return_value=[])

    def test_failed_shutdown_reports_failure(self):
        worker, _, transport = self.make_worker(shutdown_attempts=1)
        worker._record("event", {})
        transport.report.side_effect = RuntimeError("secret")
        with self.assertRaises(CloudError):
            worker.close()
        self.assertTrue(worker.records)
        transport.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
