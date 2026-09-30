"""Real multiprocessing tests for the worker supervisor."""

import multiprocessing
import time
import unittest

from mudae_core.worker import WorkerSupervisor


_FAKE_TOKEN = "fake-token-123"


def fake_process_target(connection, events, heartbeat, dropped, instance_id):
    """Small spawn-safe runtime speaking the worker pipe protocol."""
    events.cancel_join_thread()
    running = False
    try:
        while True:
            heartbeat.value = time.monotonic()
            if not connection.poll(0.02):
                continue
            command = connection.recv()
            action = command["action"]
            preset = command.get("preset_data", {})
            if action == "shutdown":
                connection.send({"success": True, "result": {"stopped": True}})
                return
            if action == "start":
                if preset.get("fake_mode") == "crash":
                    return
                running = True
                event_count = preset.get("event_count", 1)
                for index in range(event_count):
                    try:
                        events.put_nowait({
                            "instance_id": instance_id,
                            "event_type": "fake_event",
                            "data": {"index": index, "token": command["credentials"]["token"]},
                        })
                    except Exception:
                        with dropped.get_lock():
                            dropped.value += 1
                connection.send({
                    "success": True,
                    "result": {"state": "running", "token": command["credentials"]["token"]},
                })
            elif action == "status":
                connection.send({"success": True, "result": {"state": "running" if running else "stopped"}})
            elif action == "stop":
                running = False
                connection.send({"success": True, "result": {"stopped": True}})
            elif action == "restart":
                if "restart" in preset.get("hang_actions", []):
                    time.sleep(10)
                running = True
                connection.send({"success": True, "result": {"restarted": True}})
            elif action == "preset_update":
                if "preset_update" in preset.get("hang_actions", []):
                    time.sleep(10)
                connection.send({"success": True, "result": {"status": "applied"}})
            else:
                connection.send({"success": False, "error": "unsupported"})
    except (EOFError, BrokenPipeError, OSError):
        return
    finally:
        connection.close()
        events.close()


def command(command_id, user_id="user", instance_id="instance", action="start", **extra):
    value = {
        "command_id": command_id,
        "user_id": user_id,
        "instance_id": instance_id,
        "action": action,
    }
    value.update(extra)
    return value


def start_command(command_id, user_id="user", instance_id="instance", **extra):
    payload = {
        "preset_name": "fake",
        "preset_data": {"event_count": 1},
        "credentials": {"token": _FAKE_TOKEN},
    }
    payload.update(extra)
    return command(command_id, user_id, instance_id, "start", **payload)


class WorkerSupervisorTest(unittest.TestCase):
    def setUp(self):
        self.supervisor = WorkerSupervisor(
            process_target=fake_process_target,
            command_timeout=1.0,
            health_timeout=1.5,
            event_capacity=16,
        )
        self.addCleanup(self.supervisor.close)

    def test_same_instance_id_isolated_by_tenant(self):
        first = self.supervisor.execute(start_command("a", user_id="tenant-a", instance_id="same"))
        second = self.supervisor.execute(start_command("b", user_id="tenant-b", instance_id="same"))
        self.assertTrue(first["success"])
        self.assertTrue(second["success"])
        self.assertEqual(len(self.supervisor.health()["instances"]), 2)

    def test_lifecycle_start_stop_restart_status_and_preset_update(self):
        self.assertTrue(self.supervisor.execute(start_command("start"))["success"])
        status = self.supervisor.execute(command("status", action="status"))
        self.assertEqual(status["result"]["state"], "running")
        updated = self.supervisor.execute(command(
            "update", action="preset_update", preset_data={"event_count": 1}
        ))
        self.assertEqual(updated["result"]["status"], "applied")
        self.assertTrue(self.supervisor.execute(command("restart", action="restart"))["result"]["restarted"])
        self.assertTrue(self.supervisor.execute(command("stop", action="stop"))["result"]["stopped"])
        self.assertEqual(self.supervisor.execute(command("after-stop", action="status"))["result"]["state"], "stopped")

    def test_replay_is_idempotent_and_conflicts_are_rejected(self):
        request = start_command("same")
        original = self.supervisor.execute(request)
        self.assertEqual(self.supervisor.execute(request), original)
        conflict = start_command("same", instance_id="instance", preset_name="other")
        self.assertEqual(self.supervisor.execute(conflict)["error"], "command_id_conflict")

    def test_invalid_internal_preset_and_credentials_do_not_spawn(self):
        invalids = [
            start_command("bad-preset", preset_data=[]),
            start_command("private-preset", preset_data={"_internal": True}),
            start_command("token-preset", preset_data={"token": "embedded"}),
            command("bad-credentials", preset_name="fake", preset_data={}, credentials={"tokens": ["x"]}),
            command("empty-credentials", preset_name="fake", preset_data={}, credentials={"token": " "}),
        ]
        for request in invalids:
            self.assertEqual(self.supervisor.execute(request)["error"], "invalid_command")
        self.assertEqual(self.supervisor.health()["instances"], [])

    def test_abrupt_crash_is_reported_by_health(self):
        result = self.supervisor.execute(start_command("crash", preset_data={"fake_mode": "crash"}))
        self.assertEqual(result["error"], "runtime_unresponsive")
        health = self.supervisor.health()["instances"][0]
        self.assertEqual(health["health"], "failed")
        self.assertFalse(health["process_alive"])

    def test_hung_command_is_terminated(self):
        self.assertTrue(self.supervisor.execute(start_command("hang-start"))["success"])
        result = self.supervisor.execute(command(
            "hang", action="preset_update", preset_data={"hang_actions": ["preset_update"]}
        ))
        self.assertEqual(result["error"], "runtime_unresponsive")
        self.assertFalse(self.supervisor.health()["instances"][0]["process_alive"])

    def test_redaction_is_applied_to_forwarded_response_and_events(self):
        result = self.supervisor.execute(start_command("redact"))
        self.assertNotIn(_FAKE_TOKEN, str(result))
        deadline = time.time() + 1
        records = []
        while time.time() < deadline and not records:
            records = self.supervisor.drain_records()
            time.sleep(0.01)
        self.assertTrue(records)
        self.assertNotIn(_FAKE_TOKEN, str(records))
        self.assertIn("[REDACTED]", str(records))

    def test_event_records_are_bounded_and_drops_are_counted(self):
        self.supervisor.close()
        self.supervisor = WorkerSupervisor(
            process_target=fake_process_target, command_timeout=1.0,
            health_timeout=1.5, event_capacity=2,
        )
        result = self.supervisor.execute(start_command("burst", preset_data={"event_count": 50}))
        self.assertTrue(result["success"])
        time.sleep(0.1)
        self.assertLessEqual(len(self.supervisor.drain_records(3)), 3)
        self.assertGreater(self.supervisor.health()["instances"][0]["dropped_events"], 0)

    def test_start_after_stop(self):
        self.assertTrue(self.supervisor.execute(start_command("first"))["success"])
        self.assertTrue(self.supervisor.execute(command("stop", action="stop"))["result"]["stopped"])
        self.assertTrue(self.supervisor.execute(start_command("second"))["success"])

    def test_restart_after_process_crash(self):
        self.assertTrue(self.supervisor.execute(start_command("first"))["success"])
        slot = self.supervisor.slots[("user", "instance")]
        slot.process.terminate()
        slot.process.join(2)
        result = self.supervisor.execute(command("recover", action="restart"))
        self.assertTrue(result["result"]["restarted"])

    def test_close_rejects_commands(self):
        self.assertTrue(self.supervisor.execute(start_command("close-start"))["success"])
        self.supervisor.close()
        self.assertEqual(self.supervisor.execute(command("after-close", action="status"))["error"], "worker_stopped")

    def test_real_runtime_manager_subprocess_invalid_preset_fails(self):
        from mudae_core.worker import WorkerSupervisor as CurrentSupervisor
        supervisor = CurrentSupervisor(command_timeout=10, health_timeout=12)
        self.addCleanup(supervisor.close)
        result = supervisor.execute(command(
            "real-invalid", preset_name="invalid", action="start",
            preset_data={"loot_mode": "not-a-mode"},
            credentials={"token": "never-used"},
        ))
        self.assertIn(result.get("error"), (None, "runtime_unresponsive"))
        deadline = time.time() + 30
        status = None
        while time.time() < deadline:
            status = supervisor.execute(command("real-status-" + str(time.monotonic()), action="status"))
            if status.get("result", {}).get("state") == "failed":
                break
            time.sleep(0.05)
        self.assertEqual(status["result"]["state"], "failed")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    unittest.main()
