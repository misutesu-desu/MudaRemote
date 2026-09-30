"""Tests for cloud-capable bot runtime with instance isolation and lifecycle management."""

import unittest
import time
import threading
import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch, MagicMock
from mudae_core.bot_runtime import (
    BotInstance,
    RuntimeManager,
    InstanceState,
    InstanceEvent,
)


class TestInstanceEvent(unittest.TestCase):
    """Test InstanceEvent data structure."""

    def test_event_to_dict(self):
        from datetime import datetime
        event = InstanceEvent(
            instance_id="test-1",
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
            event_type="state_change",
            data={"old_state": "stopped", "new_state": "running"},
        )
        result = event.to_dict()
        self.assertEqual(result["instance_id"], "test-1")
        self.assertEqual(result["event_type"], "state_change")
        self.assertEqual(result["data"]["old_state"], "stopped")
        self.assertIn("2026-01-01", result["timestamp"])


class TestBotInstance(unittest.TestCase):
    """Test BotInstance lifecycle and control."""

    def setUp(self):
        self.preset_data = {
            "channel_id": "123456789",
            "prefix": "$",
            "mudae_prefix": "$",
            "roll_command": "wa",
            "rolling": True,
            "min_kakera": 100,
        }
        self.credentials = {"token": "fake.token.for.testing"}
        self.events = []

        def event_callback(event):
            self.events.append(event)

        self.event_callback = event_callback

    def test_instance_initialization(self):
        instance = BotInstance(
            instance_id="test-1",
            preset_name="TestPreset",
            preset_data=self.preset_data,
            credentials=self.credentials,
            event_callback=self.event_callback,
        )
        self.assertEqual(instance.instance_id, "test-1")
        self.assertEqual(instance.preset_name, "TestPreset")
        self.assertEqual(instance.state, InstanceState.STOPPED)
        self.assertIsNone(instance.error)
        self.assertEqual(instance.restart_required, [])
        # Credentials merged into preset_data
        self.assertEqual(instance.preset_data["token"], "fake.token.for.testing")
        self.assertTrue(instance.preset_data["_runtime_mode"])

    def test_multi_token_credentials(self):
        """Test that RuntimeManager can expand multiple tokens."""
        credentials = {"tokens": ["token1", "token2", "token3"]}

        manager = RuntimeManager()

        with patch.object(BotInstance, "start"):
            instance_ids = manager.start_instances_from_preset(
                preset_name="Multi",
                preset_data=self.preset_data,
                credentials=credentials,
            )

        self.assertEqual(len(instance_ids), 3)
        # Verify instances were created
        self.assertEqual(len(manager.list_instances()), 3)

    def test_runtime_logs_emit_redacted_events_without_persistent_logging(self):
        token = self.credentials["token"]
        print_log = Mock()

        def run_bot(name, data, log_function):
            log_function(f"Authentication failed for {token}", name, "INFO")

        instance = BotInstance(
            instance_id="test-log",
            preset_name="TestPreset",
            preset_data=self.preset_data,
            credentials=self.credentials,
            event_callback=self.event_callback,
        )
        with patch.dict(sys.modules, {"mudae_bot": SimpleNamespace(run_bot=run_bot, print_log=print_log)}), \
             patch("mudae_core.config.validate_preset", return_value=[]):
            self.assertTrue(instance.start())
            deadline = time.monotonic() + 2
            while not any(event.event_type == "log" for event in self.events) and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(instance.stop(2))

        log_events = [event for event in self.events if event.event_type == "log"]
        self.assertEqual(len(log_events), 1)
        self.assertEqual(log_events[0].data["message"], "Authentication failed for [REDACTED]")
        print_log.assert_not_called()

    def test_state_transitions_emit_events(self):
        instance = BotInstance(
            instance_id="test-1",
            preset_name="TestPreset",
            preset_data=self.preset_data,
            credentials=self.credentials,
            event_callback=self.event_callback,
        )
        instance._set_state(InstanceState.STARTING)
        instance._set_state(InstanceState.RUNNING)
        instance._set_state(InstanceState.STOPPED)

        self.assertEqual(len(self.events), 3)
        self.assertEqual(self.events[0].event_type, "state_change")
        self.assertEqual(self.events[0].data["new_state"], "starting")
        self.assertEqual(self.events[1].data["new_state"], "running")
        self.assertEqual(self.events[2].data["new_state"], "stopped")

    def test_failed_state_captures_error(self):
        instance = BotInstance(
            instance_id="test-1",
            preset_name="TestPreset",
            preset_data=self.preset_data,
            credentials=self.credentials,
            event_callback=self.event_callback,
        )
        instance._set_state(InstanceState.FAILED, "Connection timeout")

        self.assertEqual(instance.state, InstanceState.FAILED)
        self.assertEqual(instance.error, "Connection timeout")
        self.assertEqual(self.events[0].data["error"], "Connection timeout")

    def test_callback_exception_does_not_crash_instance(self):
        def bad_callback(event):
            raise ValueError("Callback failed")

        instance = BotInstance(
            instance_id="test-1",
            preset_name="TestPreset",
            preset_data=self.preset_data,
            credentials=self.credentials,
            event_callback=bad_callback,
        )
        # Should not raise
        instance._set_state(InstanceState.RUNNING)
        self.assertEqual(instance.state, InstanceState.RUNNING)

    def test_get_status_snapshot(self):
        instance = BotInstance(
            instance_id="test-1",
            preset_name="TestPreset",
            preset_data=self.preset_data,
            credentials=self.credentials,
            event_callback=None,
        )
        instance._set_state(InstanceState.RUNNING)

        status = instance.get_status()
        self.assertEqual(status["instance_id"], "test-1")
        self.assertEqual(status["preset_name"], "TestPreset")
        self.assertEqual(status["state"], "running")
        self.assertIsNone(status["error"])
        self.assertEqual(status["restart_required"], [])

    def test_preset_outcome_is_stored_emitted_and_redacted(self):
        instance = BotInstance(
            instance_id="test-outcome", preset_name="TestPreset",
            preset_data=self.preset_data, credentials=self.credentials,
            event_callback=self.event_callback,
        )
        instance._on_preset_outcome({
            "request_id": 4, "status": "applied", "message": "applied fake.token.for.testing",
            "changed_keys": ["min_kakera"],
        })
        self.assertEqual(instance._preset_outcomes[4]["status"], "applied")
        self.assertNotIn("fake.token.for.testing", str(instance._preset_outcomes[4]))
        self.assertEqual(self.events[-1].event_type, "preset_outcome")
        self.assertNotIn("fake.token.for.testing", str(self.events[-1].data))

    @patch("mudae_core.config.validate_preset")
    def test_validation_failure_prevents_start(self, mock_validate):
        mock_validate.return_value = ["channel_id is required"]

        instance = BotInstance(
            instance_id="test-1",
            preset_name="TestPreset",
            preset_data=self.preset_data,
            credentials=self.credentials,
            event_callback=self.event_callback,
        )

        instance.start(block=False)
        time.sleep(1.0)  # Wait for thread to initialize and validate

        self.assertEqual(instance.state, InstanceState.FAILED)
        self.assertIn("validation failed", instance.error.lower())

    def test_apply_preset_when_not_running(self):
        instance = BotInstance(
            instance_id="test-1",
            preset_name="TestPreset",
            preset_data=self.preset_data,
            credentials=self.credentials,
            event_callback=None,
        )

        new_preset = dict(self.preset_data)
        new_preset["min_kakera"] = 200

        result = instance.apply_preset(new_preset)
        self.assertEqual(result["status"], "inactive")
        self.assertEqual(result["restart_required"], [])

    @patch("mudae_core.preset_reload.validate_live_preset")
    def test_apply_preset_validation_error(self, mock_validate):
        mock_validate.return_value = ["Invalid min_kakera"]

        instance = BotInstance(
            instance_id="test-1",
            preset_name="TestPreset",
            preset_data=self.preset_data,
            credentials=self.credentials,
            event_callback=None,
        )

        new_preset = dict(self.preset_data)
        result = instance.apply_preset(new_preset)

        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["errors"], ["Invalid min_kakera"])

    def test_stop_when_already_stopped(self):
        instance = BotInstance(
            instance_id="test-1",
            preset_name="TestPreset",
            preset_data=self.preset_data,
            credentials=self.credentials,
            event_callback=None,
        )

        result = instance.stop(timeout=1.0)
        self.assertTrue(result)
        self.assertEqual(instance.state, InstanceState.STOPPED)

    def test_callbacks_can_query_and_stop_reentrantly(self):
        seen = []
        instance = BotInstance("reentrant", "Test", self.preset_data, self.credentials)
        def callback(event):
            seen.append((event.data["new_state"], instance.get_status()["state"]))
            if event.data["new_state"] == "stopping":
                self.assertTrue(instance.stop(0))
        instance.event_callback = callback
        instance._set_state(InstanceState.RUNNING)
        self.assertTrue(instance.stop(0))
        self.assertEqual(seen[-2:], [("stopping", "stopping"), ("stopped", "stopped")])

    def test_loop_shutdown_awaits_spawned_tasks_before_worker_exit(self):
        from mudae_core import bot_runtime
        started = threading.Event()
        cleaned = threading.Event()
        async def background():
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(.03)
                cleaned.set()
        class Client:
            loop = None
            def __init__(self):
                # asyncio keeps only weak references to tasks; a pending task with no
                # owner is garbage-collectable and would never run its cleanup.
                self.background_tasks = []
            def is_closed(self):
                return False
            async def close(self):
                pass
            async def start(self, token):
                self.background_tasks.append(asyncio.create_task(background()))
                started.set()
                await asyncio.Event().wait()
        client = Client()
        def run_bot(name, data, log_function):
            data["_runtime_execution_hook"](client, data["token"])
        instance = BotInstance("tasks", "Test", self.preset_data, self.credentials)
        with patch.dict(sys.modules, {"mudae_bot": SimpleNamespace(run_bot=run_bot, print_log=Mock())}), \
             patch("mudae_core.config.validate_preset", return_value=[]):
            self.assertTrue(instance.start())
            self.assertTrue(started.wait(2))
            self.assertTrue(instance.stop(2))
        self.assertTrue(cleaned.is_set())

    def test_public_apply_request_ids_settle_and_restart_uses_successful_config(self):
        from mudae_core.preset_reload import LivePresetReload
        instance = BotInstance("apply", "Test", self.preset_data, self.credentials)
        loop = asyncio.new_event_loop()
        ready = threading.Event()
        def runner():
            asyncio.set_event_loop(loop)
            ready.set()
            loop.run_forever()
            loop.close()
        worker = threading.Thread(target=runner)
        worker.start()
        self.assertTrue(ready.wait(2))
        client = SimpleNamespace(_live_preset_ready=True, is_claiming=True, loop=loop)
        reload = LivePresetReload(client, self.preset_data, lambda data: {"min_kakera"},
                                  Mock(), observer=instance._on_preset_outcome)
        client._preset_reload = reload
        instance._client = client
        instance._set_state(InstanceState.RUNNING)
        def on_loop(fn):
            async def invoke():
                return await fn()
            return asyncio.run_coroutine_threadsafe(invoke(), loop).result(2)
        try:
            valid = {**self.preset_data, "min_kakera": 220, "channel_id": "987654321"}
            first = instance.apply_preset(valid)["request_id"]
            on_loop(reload.poll_once)
            second = instance.apply_preset(valid)["request_id"]
            on_loop(reload.poll_once)
            self.assertEqual(instance._preset_outcomes[first]["status"], "superseded")
            client.is_claiming = False
            on_loop(reload.poll_once)
            self.assertEqual(instance._preset_outcomes[second]["status"], "restart_required")
            self.assertEqual(instance.preset_data["channel_id"], "987654321")
            self.assertEqual(instance.preset_data["token"], self.credentials["token"])
            rejected = instance.apply_preset({**valid, "min_kakera": 330})["request_id"]
            with patch("mudae_core.preset_reload.validate_live_preset", return_value=["invalid"]):
                on_loop(reload.poll_once)
            self.assertEqual(instance._preset_outcomes[rejected]["status"], "rejected")
            self.assertEqual(instance.get_status()["desired_preset"], instance.get_status()["active_preset"])
            self.assertEqual(instance.preset_data["min_kakera"], 220)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            worker.join(2)


class TestRuntimeManager(unittest.TestCase):
    """Test RuntimeManager multi-instance coordination."""

    def setUp(self):
        self.preset_data = {
            "channel_id": "123456789",
            "prefix": "$",
            "mudae_prefix": "$",
            "roll_command": "wa",
            "rolling": True,
            "min_kakera": 100,
        }
        self.credentials = {"token": "fake.token.for.testing"}
        self.events = []

        def event_callback(event):
            self.events.append(event)

        self.manager = RuntimeManager(event_callback=event_callback)

    def tearDown(self):
        self.manager.shutdown_all(timeout=1.0)

    def test_live_worker_cannot_be_removed_replaced_or_restarted_after_timeout(self):
        instance = BotInstance("same", "Test", self.preset_data, self.credentials)
        exit_gate = threading.Event()
        worker = threading.Thread(target=exit_gate.wait)
        worker.start()
        instance._thread = worker
        instance._set_state(InstanceState.STOPPED)
        self.manager._instances["same"] = instance
        try:
            self.assertEqual(self.manager.get_status("same")["state"], "stopping")
            self.assertFalse(self.manager.remove_instance("same"))
            self.assertFalse(self.manager.restart_instance("same", timeout=.01))
            with self.assertRaises(ValueError):
                self.manager.start_instance("Test", self.preset_data, self.credentials, instance_id="same")
        finally:
            exit_gate.set()
            worker.join(2)
        instance._set_state(InstanceState.STOPPED)  # Worker normally publishes terminal state.
        self.assertTrue(self.manager.remove_instance("same"))

    def test_external_account_contract_stagger_and_snapshot_isolation(self):
        data = {**self.preset_data, "wishlist": ["Rem"], "token": "preset-secret"}
        with patch.object(BotInstance, "start"):
            ids = self.manager.start_instances_from_preset("Source #2", data,
                      {"tokens": ["first", "second"]})
        self.assertEqual(len(ids), 2)
        first, second = (self.manager._instances[i] for i in ids)
        self.assertEqual([first.preset_name, second.preset_name], ["Source #2", "Source #2 #2"])
        self.assertEqual(first.preset_data["_source_preset_name"], "Source #2")
        from mudae_core.runtime import active_stagger_seconds
        self.assertEqual(second.preset_data["persistent_stagger_seconds"], active_stagger_seconds(1))
        data["wishlist"].append("mutated")
        self.assertEqual(first.preset_data["wishlist"], ["Rem"])
        self.assertEqual(first.preset_data["token"], "first")
        for credentials in ({"tokens": ["a", "b"]}, {"token": "a", "tokens": ["b"]}):
            with self.assertRaises(ValueError):
                self.manager.start_instance("single", self.preset_data, credentials)
        for credentials in ({"tokens": ["same", "same"]},
                            {"tokens": ["one", " "]}, {"token": "one", "tokens": ["two"]}):
            with self.assertRaises(ValueError):
                self.manager.start_instances_from_preset("bad", self.preset_data, credentials)

    def test_manager_initialization(self):
        self.assertIsNotNone(self.manager)
        self.assertEqual(self.manager.list_instances(), [])

    def test_start_instance_generates_id(self):
        with patch.object(BotInstance, "start") as mock_start:
            instance_id = self.manager.start_instance(
                preset_name="Test",
                preset_data=self.preset_data,
                credentials=self.credentials,
            )
            self.assertIsNotNone(instance_id)
            self.assertIn(instance_id, self.manager.list_instances())
            mock_start.assert_called_once()

    def test_start_instance_custom_id(self):
        with patch.object(BotInstance, "start") as mock_start:
            instance_id = self.manager.start_instance(
                preset_name="Test",
                preset_data=self.preset_data,
                credentials=self.credentials,
                instance_id="custom-123",
            )
            self.assertEqual(instance_id, "custom-123")
            mock_start.assert_called_once()

    def test_delayed_start_is_reserved_from_remove_and_replacement(self):
        entered = threading.Event()
        release = threading.Event()
        result = []

        def delayed_start(instance, block=False):
            self.assertEqual(self.manager.get_status("same")["state"], "stopped")
            self.assertTrue(self.manager.stop_instance("same", timeout=0))
            self.assertFalse(self.manager.remove_instance("same"))
            entered.set()
            release.wait(2)
            return True

        with patch.object(BotInstance, "start", autospec=True, side_effect=delayed_start):
            worker = threading.Thread(target=lambda: result.append(self.manager.start_instance(
                "Test", self.preset_data, self.credentials, instance_id="same"
            )))
            worker.start()
            self.assertTrue(entered.wait(1))
            self.assertFalse(self.manager.remove_instance("same"))
            with self.assertRaises(ValueError):
                self.manager.start_instance(
                    "Replacement", self.preset_data, self.credentials, instance_id="same"
                )
            release.set()
            worker.join(2)

        self.assertFalse(worker.is_alive())
        self.assertEqual(result, ["same"])
        self.assertIn("same", self.manager.list_instances())

    def test_start_duplicate_instance_id_raises(self):
        with patch.object(BotInstance, "start"):
            self.manager.start_instance(
                preset_name="Test",
                preset_data=self.preset_data,
                credentials=self.credentials,
                instance_id="dup",
            )

            with self.assertRaises(ValueError):
                self.manager.start_instance(
                    preset_name="Test2",
                    preset_data=self.preset_data,
                    credentials=self.credentials,
                    instance_id="dup",
                )

    def test_stop_instance(self):
        with patch.object(BotInstance, "start"):
            instance_id = self.manager.start_instance(
                preset_name="Test",
                preset_data=self.preset_data,
                credentials=self.credentials,
            )

            with patch.object(BotInstance, "stop", return_value=True) as mock_stop:
                result = self.manager.stop_instance(instance_id, timeout=5.0)
                self.assertTrue(result)
                mock_stop.assert_called_once_with(5.0)

    def test_stop_nonexistent_instance_raises(self):
        with self.assertRaises(KeyError):
            self.manager.stop_instance("nonexistent")

    def test_restart_instance(self):
        with patch.object(BotInstance, "start"):
            instance_id = self.manager.start_instance(
                preset_name="Test",
                preset_data=self.preset_data,
                credentials=self.credentials,
            )

            with patch.object(BotInstance, "restart", return_value=True) as mock_restart:
                result = self.manager.restart_instance(instance_id, timeout=5.0)
                self.assertTrue(result)
                mock_restart.assert_called_once_with(5.0)

    def test_apply_preset(self):
        with patch.object(BotInstance, "start"):
            instance_id = self.manager.start_instance(
                preset_name="Test",
                preset_data=self.preset_data,
                credentials=self.credentials,
            )

            new_preset = dict(self.preset_data)
            new_preset["min_kakera"] = 200

            expected = {"status": "queued", "restart_required": [], "errors": []}
            with patch.object(BotInstance, "apply_preset", return_value=expected) as mock_apply:
                result = self.manager.apply_preset(instance_id, new_preset)
                self.assertEqual(result["status"], "queued")
                mock_apply.assert_called_once_with(new_preset)

    def test_get_status(self):
        with patch.object(BotInstance, "start"):
            instance_id = self.manager.start_instance(
                preset_name="Test",
                preset_data=self.preset_data,
                credentials=self.credentials,
            )

            expected_status = {
                "instance_id": instance_id,
                "preset_name": "Test",
                "state": "running",
                "error": None,
                "restart_required": [],
            }
            with patch.object(BotInstance, "get_status", return_value=expected_status):
                status = self.manager.get_status(instance_id)
                self.assertEqual(status["instance_id"], instance_id)
                self.assertEqual(status["state"], "running")

    def test_get_all_statuses(self):
        with patch.object(BotInstance, "start"):
            id1 = self.manager.start_instance("Test1", self.preset_data, self.credentials, instance_id="i1")
            id2 = self.manager.start_instance("Test2", self.preset_data, self.credentials, instance_id="i2")

            with patch.object(BotInstance, "get_status", side_effect=[
                {"instance_id": "i1", "preset_name": "Test1", "state": "running", "error": None, "restart_required": []},
                {"instance_id": "i2", "preset_name": "Test2", "state": "stopped", "error": None, "restart_required": []},
            ]):
                statuses = self.manager.get_all_statuses()
                self.assertEqual(len(statuses), 2)
                self.assertIn("i1", statuses)
                self.assertIn("i2", statuses)

    def test_remove_instance_when_stopped(self):
        with patch.object(BotInstance, "start"):
            instance_id = self.manager.start_instance(
                preset_name="Test",
                preset_data=self.preset_data,
                credentials=self.credentials,
            )

            # Mock instance as stopped
            instance = self.manager._instances[instance_id]
            instance._state = InstanceState.STOPPED

            result = self.manager.remove_instance(instance_id)
            self.assertTrue(result)
            self.assertNotIn(instance_id, self.manager.list_instances())

    def test_remove_instance_when_running_fails(self):
        with patch.object(BotInstance, "start"):
            instance_id = self.manager.start_instance(
                preset_name="Test",
                preset_data=self.preset_data,
                credentials=self.credentials,
            )

            # Mock instance as running
            instance = self.manager._instances[instance_id]
            instance._state = InstanceState.RUNNING

            result = self.manager.remove_instance(instance_id)
            self.assertFalse(result)
            self.assertIn(instance_id, self.manager.list_instances())

    def test_shutdown_all(self):
        with patch.object(BotInstance, "start"):
            id1 = self.manager.start_instance("Test1", self.preset_data, self.credentials)
            id2 = self.manager.start_instance("Test2", self.preset_data, self.credentials)

            with patch.object(BotInstance, "stop", return_value=True) as mock_stop:
                self.manager.shutdown_all(timeout=3.0)
                self.assertEqual(mock_stop.call_count, 2)

    def test_list_instances(self):
        with patch.object(BotInstance, "start"):
            id1 = self.manager.start_instance("Test1", self.preset_data, self.credentials, instance_id="a")
            id2 = self.manager.start_instance("Test2", self.preset_data, self.credentials, instance_id="b")

            instances = self.manager.list_instances()
            self.assertEqual(set(instances), {"a", "b"})

    def test_event_callback_propagates_to_instances(self):
        with patch.object(BotInstance, "start"):
            instance_id = self.manager.start_instance(
                preset_name="Test",
                preset_data=self.preset_data,
                credentials=self.credentials,
            )

            # Trigger event from instance
            instance = self.manager._instances[instance_id]
            instance._emit_event("test_event", {"key": "value"})

            # Check manager received it
            self.assertTrue(len(self.events) > 0)
            found = any(e.event_type == "test_event" for e in self.events)
            self.assertTrue(found)


class TestInstanceIsolation(unittest.TestCase):
    """Test that instances are properly isolated from each other."""

    def test_multiple_instances_independent_states(self):
        manager = RuntimeManager()

        with patch.object(BotInstance, "start"):
            id1 = manager.start_instance(
                "Test1",
                {"channel_id": "123", "prefix": "$", "mudae_prefix": "$", "roll_command": "wa"},
                {"token": "token1"},
                instance_id="i1",
            )
            id2 = manager.start_instance(
                "Test2",
                {"channel_id": "456", "prefix": "$", "mudae_prefix": "$", "roll_command": "wa"},
                {"token": "token2"},
                instance_id="i2",
            )

            # Set different states
            manager._instances["i1"]._set_state(InstanceState.RUNNING)
            manager._instances["i2"]._set_state(InstanceState.FAILED, "Connection lost")

            status1 = manager.get_status("i1")
            status2 = manager.get_status("i2")

            self.assertEqual(status1["state"], "running")
            self.assertIsNone(status1["error"])

            self.assertEqual(status2["state"], "failed")
            self.assertEqual(status2["error"], "Connection lost")

        manager.shutdown_all(timeout=1.0)

    def test_credentials_not_shared_between_instances(self):
        manager = RuntimeManager()

        with patch.object(BotInstance, "start"):
            id1 = manager.start_instance(
                "Test1",
                {"channel_id": "123", "prefix": "$", "mudae_prefix": "$", "roll_command": "wa"},
                {"token": "secret1"},
            )
            id2 = manager.start_instance(
                "Test2",
                {"channel_id": "456", "prefix": "$", "mudae_prefix": "$", "roll_command": "wa"},
                {"token": "secret2"},
            )

            instance1 = manager._instances[id1]
            instance2 = manager._instances[id2]

            self.assertEqual(instance1.preset_data["token"], "secret1")
            self.assertEqual(instance2.preset_data["token"], "secret2")
            self.assertNotEqual(instance1.credentials, instance2.credentials)

        manager.shutdown_all(timeout=1.0)


if __name__ == "__main__":
    unittest.main()
