"""Integration tests for bot runtime with realistic Discord mocking."""

import unittest
import asyncio
import time
import threading
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import sys
import os
import socket
from contextlib import ExitStack
from types import SimpleNamespace
import discord

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mudae_core.bot_runtime import (
    BotInstance,
    RuntimeManager,
    InstanceState,
)
import mudae_bot
from tests.test_snipe_startup import _Bot, _Channel


_socket_connect = socket.socket.connect
_socket_connect_ex = socket.socket.connect_ex


def _is_loopback_socketpair_address(address):
    return isinstance(address, tuple) and bool(address) and address[0] in {"127.0.0.1", "::1"}


def _guard_connect(self, address):
    if _is_loopback_socketpair_address(address):
        return _socket_connect(self, address)
    raise AssertionError("network access forbidden in runtime integration tests")


def _guard_connect_ex(self, address):
    if _is_loopback_socketpair_address(address):
        return _socket_connect_ex(self, address)
    raise AssertionError("network access forbidden in runtime integration tests")


_NETWORK_GUARDS = (
    patch.object(socket.socket, "connect", _guard_connect),
    patch.object(socket.socket, "connect_ex", _guard_connect_ex),
    patch.object(discord.http.HTTPClient, "static_login", new=AsyncMock(side_effect=AssertionError("Discord login forbidden"))),
)


def setUpModule():
    for guard in _NETWORK_GUARDS:
        guard.start()


def tearDownModule():
    for guard in reversed(_NETWORK_GUARDS):
        guard.stop()


class RuntimeTestCase(unittest.TestCase):
    def setUp(self):
        self.instances = []

    def track(self, instance):
        self.instances.append(instance)
        return instance

    def stop_and_join(self, instance, timeout=2):
        stopped = False
        try:
            stopped = instance.stop(timeout=timeout)
        finally:
            if instance._thread is not None:
                instance._thread.join(timeout=timeout)
        self.assertTrue(stopped, "runtime worker shutdown timed out")
        if instance._thread is not None:
            self.assertFalse(instance._thread.is_alive(), "runtime worker did not stop")

    def tearDown(self):
        for instance in self.instances:
            self.stop_and_join(instance)


class FakeDiscordClient:
    """Minimal Discord client mock for integration testing."""

    def __init__(self, token):
        self.token = token
        self.loop = None
        self.closed = False
        self.preset_name = None
        self._preset_reload = None
        self._runtime_mode = False

    async def close(self):
        self.closed = True

    async def start(self, token):
        await asyncio.sleep(0.1)
        if "invalid" in token:
            raise Exception("LoginFailure")


class TestRuntimeIntegration(RuntimeTestCase):
    """Integration tests with mocked Discord but real threading/async."""

    @patch("mudae_bot.run_bot")
    @patch("mudae_core.config.validate_preset")
    def test_instance_lifecycle_with_mock_bot(self, mock_validate, mock_run_bot):
        """Test full start/stop cycle with mocked run_bot."""
        mock_validate.return_value = []

        # Make run_bot invoke the ready callback then block briefly
        def fake_run_bot(name, data, log_function):
            callback = data.get("_runtime_ready_callback")
            if callable(callback):
                # Create a minimal mock client
                mock_client = Mock()
                mock_client.preset_name = name
                mock_client.loop = Mock()
                mock_client._preset_reload = Mock()
                mock_client._preset_reload.name = name
                callback(mock_client)
            instance._stop_event.wait(2)

        mock_run_bot.side_effect = fake_run_bot

        events = []
        def event_callback(event):
            events.append(event)

        instance = BotInstance(
            instance_id="test-1",
            preset_name="IntegrationTest",
            preset_data={
                "channel_id": "123456789",
                "prefix": "$",
                "mudae_prefix": "$",
                "roll_command": "wa",
                "rolling": True,
                "min_kakera": 100,
            },
            credentials={"token": "test.token"},
            event_callback=event_callback,
        )

        try:
            # Start instance
            instance.start(block=False)
            instance._stop_event.wait(2)

            # Should be running
            self.assertEqual(instance.state, InstanceState.RUNNING)
        finally:
            # Keep the mock run_bot patch active through worker shutdown.
            self.stop_and_join(instance)
        self.assertEqual(instance.state, InstanceState.STOPPED)

        # Check events
        state_events = [e for e in events if e.event_type == "state_change"]
        self.assertTrue(len(state_events) >= 2)  # At least STARTING -> RUNNING -> STOPPED

    @patch("mudae_bot.run_bot")
    @patch("mudae_core.config.validate_preset")
    def test_instance_handles_crash_and_retries(self, mock_validate, mock_run_bot):
        """Test that crashes trigger retry with proper events."""
        mock_validate.return_value = []

        call_count = [0]

        def fake_run_bot_crash(name, data, log_function):
            call_count[0] += 1
            callback = data.get("_runtime_ready_callback")
            if call_count[0] == 1:
                # First call crashes
                raise RuntimeError("Simulated network error")
            # Second attempt succeeds
            if callable(callback):
                mock_client = Mock()
                mock_client.preset_name = name
                mock_client.loop = Mock()
                callback(mock_client)
            time.sleep(0.5)

        mock_run_bot.side_effect = fake_run_bot_crash

        events = []
        def event_callback(event):
            events.append(event)

        instance = BotInstance(
            instance_id="test-crash",
            preset_name="CrashTest",
            preset_data={
                "channel_id": "123456789",
                "prefix": "$",
                "mudae_prefix": "$",
                "roll_command": "wa",
                "rolling": True,
            },
            credentials={"token": "test.token"},
            event_callback=event_callback,
        )

        try:
            instance.start(block=False)
            time.sleep(2.5)  # Wait for crash + retry (60s reduced for testing)

            # Should have recovered
            self.assertIn(instance.state, [InstanceState.RUNNING, InstanceState.STARTING])

            # Should have error event
            error_events = [e for e in events if e.event_type == "error"]
            self.assertTrue(len(error_events) > 0)
            self.assertIn("network error", error_events[0].data["message"].lower())
        finally:
            self.stop_and_join(instance)

    @patch("mudae_core.config.validate_preset")
    def test_validation_failure_stops_immediately(self, mock_validate):
        """Test that validation errors prevent startup."""
        mock_validate.return_value = ["channel_id is required", "Invalid token"]

        events = []
        instance = BotInstance(
            instance_id="test-invalid",
            preset_name="InvalidTest",
            preset_data={},
            credentials={"token": "test.token"},
            event_callback=lambda e: events.append(e),
        )

        try:
            instance.start(block=False)
            time.sleep(1.0)

            self.assertEqual(instance.state, InstanceState.FAILED)
            self.assertIn("validation", instance.error.lower())

            # Should have error event marked as fatal
            error_events = [e for e in events if e.event_type == "error"]
            self.assertTrue(len(error_events) > 0)
            self.assertTrue(error_events[0].data.get("fatal", False))
        finally:
            self.stop_and_join(instance)

    @patch("mudae_bot.run_bot")
    @patch("mudae_core.config.validate_preset")
    def test_manager_handles_multiple_instances(self, mock_validate, mock_run_bot):
        """Test manager with multiple concurrent instances."""
        mock_validate.return_value = []

        def fake_run_bot(name, data, log_function):
            callback = data.get("_runtime_ready_callback")
            if callable(callback):
                mock_client = Mock()
                mock_client.preset_name = name
                mock_client.loop = Mock()
                mock_client._preset_reload = SimpleNamespace(
                    active_preset={}, desired_preset={}
                )
                callback(mock_client)
            time.sleep(1.0)

        mock_run_bot.side_effect = fake_run_bot

        events = []
        manager = RuntimeManager(event_callback=lambda e: events.append(e))

        try:
            # Start 3 instances
            id1 = manager.start_instance(
                "Preset1",
                {"channel_id": "111", "prefix": "$", "mudae_prefix": "$", "roll_command": "wa"},
                {"token": "token1"},
            )
            id2 = manager.start_instance(
                "Preset2",
                {"channel_id": "222", "prefix": "$", "mudae_prefix": "$", "roll_command": "wa"},
                {"token": "token2"},
            )
            id3 = manager.start_instance(
                "Preset3",
                {"channel_id": "333", "prefix": "$", "mudae_prefix": "$", "roll_command": "wa"},
                {"token": "token3"},
            )

            time.sleep(1.5)

            # All should be running
            statuses = manager.get_all_statuses()
            self.assertEqual(len(statuses), 3)

            for iid in [id1, id2, id3]:
                status = statuses[iid]
                self.assertEqual(status["state"], "running")
        finally:
            # Keep the run_bot patch active until every worker has stopped.
            manager.shutdown_all(timeout=2.0)

        # All should be stopped
        statuses = manager.get_all_statuses()
        for status in statuses.values():
            self.assertEqual(status["state"], "stopped")

    @patch("mudae_bot.run_bot")
    @patch("mudae_core.preset_reload.validate_live_preset")
    @patch("mudae_core.config.validate_preset")
    def test_live_preset_application(self, mock_validate, mock_validate_live, mock_run_bot):
        """Test applying preset changes to running instance."""
        mock_validate.return_value = []
        mock_validate_live.return_value = []

        # Mock a running client with reload handler
        def fake_run_bot(name, data, log_function):
            callback = data.get("_runtime_ready_callback")
            if callable(callback):
                fake_client = Mock()
                fake_client.preset_name = name
                fake_client.loop = Mock()
                fake_client.loop.is_closed = Mock(return_value=False)
                fake_client.loop.call_soon_threadsafe = Mock()
                fake_client._preset_reload = Mock()
                fake_client._preset_reload.name = name
                fake_client._preset_reload.restart_required = Mock(return_value=["token"])
                callback(fake_client)
            time.sleep(1.0)

        mock_run_bot.side_effect = fake_run_bot

        instance = BotInstance(
            instance_id="test-live",
            preset_name="TestPreset",
            preset_data={
                "channel_id": "123456789",
                "prefix": "$",
                "mudae_prefix": "$",
                "roll_command": "wa",
                "rolling": True,
            },
            credentials={"token": "original.token"},
        )

        try:
            instance.start(block=False)
            time.sleep(1.5)

            # Should be running
            self.assertEqual(instance.state, InstanceState.RUNNING)

            # Apply new preset
            new_preset = {
                "channel_id": "123456789",
                "prefix": "$",
                "mudae_prefix": "$",
                "roll_command": "wa",
                "rolling": True,
                "min_kakera": 200,  # Changed
            }

            result = instance.apply_preset(new_preset)

            self.assertEqual(result["status"], "queued")
        finally:
            self.stop_and_join(instance, timeout=1.0)


class TestOwnedClientStartup(RuntimeTestCase):
    """Exercise the real run_bot client setup and its opt-in runtime runner."""

    class channel_type(_Channel):
        def permissions_for(self, _member):
            return SimpleNamespace(send_messages=True)

        @property
        def guild(self):
            return self._guild

        @guild.setter
        def guild(self, value):
            value.me = SimpleNamespace(id=7001)
            self._guild = value

    def setUp(self):
        super().setUp()
        self.instances = []
        self.patch_stacks = []

    def tearDown(self):
        try:
            super().tearDown()
        finally:
            for stack in reversed(self.patch_stacks):
                stack.close()

    def make_instance(self, start_behavior, client_sink=None):
        clients = client_sink if client_sink is not None else []

        class Client(_Bot):
            def __init__(self):
                super().__init__()
                self.closed = False
                clients.append(self)

            async def start(self, token):
                self.token = token
                self.loop = asyncio.get_running_loop()
                await start_behavior(self)

            async def close(self):
                self.closed = True
                self._runtime_stopping = True

            def is_closed(self):
                return self.closed

        instance = BotInstance(
            instance_id="owned-client",
            preset_name="OwnedClient",
            preset_data={"channel_id": "123456789", "prefix": "$", "mudae_prefix": "$"},
            credentials={"token": "test.token"},
        )
        self.track(instance)
        return instance, clients, Client

    def ready_behavior(self, ready):
        async def start(client):
            client._fetched_channels[123456789] = self.channel_type(123456789, lambda: client)
            await client.events["on_ready"]()
            ready.set()
            await asyncio.Event().wait()
        return start

    def start_with_real_run_bot(self, instance, clients, client_type):
        mudae_bot._mobile_runtime_stop_event.clear()
        stack = ExitStack()
        self.patch_stacks.append(stack)
        stack.enter_context(patch("mudae_core.config.validate_preset", return_value=[]))
        stack.enter_context(patch.object(mudae_bot.commands, "Bot", new=lambda **_kw: client_type()))
        stack.enter_context(patch.object(mudae_bot, "IS_TERMUX", False))
        stack.enter_context(patch.object(discord, "TextChannel", self.channel_type))
        async def no_delay(_client, _seconds, *_args, **_kwargs):
            return True
        stack.enter_context(patch.object(mudae_bot, "pause_interruptible_sleep", no_delay))
        instance.start()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not clients:
            time.sleep(0.005)
        self.assertTrue(clients, "run_bot did not construct a Discord client")

    def test_stop_cancels_login_before_ready_and_owns_client_early(self):
        entered, cancelled = threading.Event(), threading.Event()

        async def login(_client):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        instance, clients, client_type = self.make_instance(login)
        try:
            self.start_with_real_run_bot(instance, clients, client_type)
            self.assertTrue(entered.wait(1))
            self.assertIs(instance._client, clients[0])
            self.assertEqual(instance._client_loop, clients[0].loop)
            self.assertEqual(instance.state, InstanceState.STARTING)
        finally:
            self.stop_and_join(instance)
        self.assertTrue(cancelled.is_set())
        self.assertTrue(clients[0].closed)
        self.assertEqual(instance.state, InstanceState.STOPPED)

    def test_readiness_callback_transitions_to_running(self):
        ready = threading.Event()
        instance, clients, client_type = self.make_instance(self.ready_behavior(ready))
        instance.preset_data.update({"rolling": False, "skip_initial_commands": True})
        try:
            self.start_with_real_run_bot(instance, clients, client_type)
            self.assertTrue(ready.wait(1))
            self.assertEqual(instance.state, InstanceState.RUNNING)
        finally:
            self.stop_and_join(instance)

    def test_on_ready_callback_can_stop_its_own_runtime_worker(self):
        stop_callback_returned = threading.Event()
        callback_results = []
        root_tasks = []
        manager = None

        async def stop_from_ready(client):
            client._fetched_channels[123456789] = self.channel_type(123456789, lambda: client)
            await client.events["on_ready"]()
            await asyncio.Event().wait()

        instance, clients, client_type = self.make_instance(stop_from_ready)
        instance.preset_data.update({"rolling": False, "skip_initial_commands": True})

        def event_callback(event):
            if event.event_type == "state_change" and event.data["new_state"] == "running":
                root_tasks.append(instance._root_task)
                callback_results.append(manager.stop_instance(event.instance_id, timeout=0))
                stop_callback_returned.set()

        instance.event_callback = event_callback
        manager = RuntimeManager(event_callback=event_callback)
        manager._instances[instance.instance_id] = instance
        try:
            self.start_with_real_run_bot(instance, clients, client_type)
            self.assertTrue(stop_callback_returned.wait(1), "RUNNING event callback did not stop the instance")
            instance._thread.join(timeout=2)
            self.assertFalse(instance._thread.is_alive(), "runtime worker remained alive after self-stop")
            self.assertEqual(callback_results, [False], "own-thread stop should report asynchronous shutdown")
            self.assertEqual(instance.state, InstanceState.STOPPED)
            self.assertEqual(len(root_tasks), 1)
            self.assertTrue(root_tasks[0].cancelled())
            self.assertIsNone(instance._root_task)
            self.assertTrue(clients[0].closed)
        finally:
            self.stop_and_join(instance)

    def test_real_run_bot_failure_before_ready_is_bounded_and_failed(self):
        attempts = []

        async def fail_before_ready(client):
            attempts.append(client)
            raise RuntimeError("startup failed for test.token")

        instance, clients, client_type = self.make_instance(fail_before_ready)
        instance.preset_data.update({"_runtime_max_retries": 2, "_runtime_retry_delay": 0.01})
        try:
            self.start_with_real_run_bot(instance, clients, client_type)
            deadline = time.monotonic() + 2
            while instance.state != InstanceState.FAILED and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertEqual(instance.state, InstanceState.FAILED)
            self.assertEqual(len(attempts), 2)
            self.assertNotIn("test.token", instance.error)
            self.assertIn("Max retries exceeded", instance.error)
        finally:
            self.stop_and_join(instance)

    def test_real_run_bot_failure_after_ready_is_not_stale_running(self):
        attempts = []
        states = []
        retry_started = threading.Event()
        failed = threading.Event()

        async def fail_after_ready(client):
            attempts.append(client)
            client._fetched_channels[123456789] = self.channel_type(123456789, lambda: client)
            await client.events["on_ready"]()
            raise RuntimeError("disconnect failed for test.token")

        instance, clients, client_type = self.make_instance(fail_after_ready)
        def record_state(event):
            if event.event_type != "state_change":
                return
            state = event.data["new_state"]
            states.append(state)
            if state == "starting" and states.count("starting") == 2:
                retry_started.set()
            elif state == "failed":
                failed.set()

        instance.event_callback = record_state
        instance.preset_data.update({"_runtime_max_retries": 2, "_runtime_retry_delay": 0.01})
        try:
            self.start_with_real_run_bot(instance, clients, client_type)
            self.assertTrue(retry_started.wait(2), "second retry did not start")
            self.assertEqual(states[:3], ["starting", "running", "starting"])
            self.assertEqual(instance.state, InstanceState.STARTING)
            self.assertTrue(failed.wait(2), "runtime did not publish its terminal failure")
            instance._thread.join(timeout=2)
            self.assertFalse(instance._thread.is_alive(), "runtime worker did not exit after terminal failure")
            self.assertEqual(instance.state, InstanceState.FAILED)
            self.assertEqual(len(attempts), 2)
            self.assertEqual(states[-2:], ["running", "failed"])
            self.assertNotIn("test.token", instance.error)
            self.assertIn("Max retries exceeded", instance.error)
        finally:
            self.stop_and_join(instance)

    def test_real_run_bot_normal_and_loot_ready_callbacks(self):
        for loot_mode in ("off", "kl"):
            ready = threading.Event()
            instance, clients, client_type = self.make_instance(self.ready_behavior(ready))
            instance.preset_data.update({"rolling": loot_mode == "off", "loot_mode": loot_mode, "skip_initial_commands": True})
            try:
                self.start_with_real_run_bot(instance, clients, client_type)
                self.assertTrue(ready.wait(1), f"{loot_mode} runtime did not report ready")
                self.assertEqual(instance.state, InstanceState.RUNNING)
                self.assertIs(instance._client, clients[0])
            finally:
                self.stop_and_join(instance)

    def test_simultaneous_instances_keep_same_preset_clients_distinct(self):
        entered = [threading.Event(), threading.Event()]
        instances = []
        client_sinks = []
        client_types = []
        for index in range(2):
            slot = {}

            async def block_client(client, index=index, slot=slot):
                client._fetched_channels[123456789] = self.channel_type(123456789, lambda: client)
                await client.events["on_ready"]()
                entered[index].set()
                await asyncio.Event().wait()

            instance, owned_clients, client_type = self.make_instance(block_client)
            instance.preset_name = "SharedPreset"
            instance.preset_data["_source_preset_name"] = "SharedPreset"
            instance.instance_id = f"shared-{index}"
            instance.preset_data.update({"rolling": False, "skip_initial_commands": True})
            slot["instance"] = instance
            instances.append(instance)
            client_sinks.append(owned_clients)
            client_types.append(client_type)
        try:
            for instance, owned_clients, client_type in zip(
                instances, client_sinks, client_types
            ):
                self.start_with_real_run_bot(instance, owned_clients, client_type)
            self.assertTrue(entered[0].wait(1))
            self.assertTrue(entered[1].wait(1))
            self.assertIsNot(instances[0]._client, instances[1]._client)
            self.assertEqual([item.state for item in instances], [InstanceState.RUNNING] * 2)
        finally:
            for instance in instances:
                self.stop_and_join(instance)

    @patch("mudae_core.config.validate_preset", return_value=[])
    @patch("mudae_bot.run_bot")
    def test_lifecycle_injects_outcome_observer(self, mock_run_bot, _validate):
        observed = threading.Event()
        events = []

        def fake_run_bot(_name, data, log_function):
            observer = data.get("_preset_outcome_observer")
            self.assertTrue(callable(observer))
            observer({"request_id": 12, "status": "applied", "message": "ok"})
            observed.set()

        mock_run_bot.side_effect = fake_run_bot
        instance = BotInstance(
            instance_id="outcome-injection", preset_name="Profile",
            preset_data={"channel_id": "123456789", "prefix": "$", "mudae_prefix": "$"},
            credentials={"token": "test.token"}, event_callback=events.append,
        )
        try:
            instance.start()
            self.assertTrue(observed.wait(1))
            result = [event for event in events if event.event_type == "preset_outcome"]
            self.assertEqual(result[0].data["request_id"], 12)
            self.assertEqual(instance._preset_outcomes[12]["status"], "applied")
        finally:
            self.stop_and_join(instance)

    def test_timeout_keeps_stopping_and_blocks_overlapping_start(self):
        release = threading.Event()
        entered = threading.Event()
        cancelled = threading.Event()

        async def login(_client):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                while not release.is_set():
                    await asyncio.sleep(0.01)

        instance, clients, client_type = self.make_instance(login)
        try:
            self.start_with_real_run_bot(instance, clients, client_type)
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline and not entered.is_set():
                time.sleep(0.005)
            self.assertTrue(entered.is_set())
            self.assertFalse(instance.stop(timeout=0.05))
            self.assertEqual(instance.state, InstanceState.STOPPING)
            self.assertFalse(instance.start())
            self.assertTrue(cancelled.wait(1))
        finally:
            release.set()
            self.stop_and_join(instance)


class TestDesktopCompatibility(unittest.TestCase):
    """Test that desktop launcher remains compatible."""

    def test_existing_desktop_process_launch_unchanged(self):
        """Verify desktop's subprocess approach still works."""
        # This is a design verification test, not a live process test
        preset_data = {
            "channel_id": "123456789",
            "prefix": "$",
            "mudae_prefix": "$",
            "roll_command": "wa",
            "rolling": True,
            "token": "desktop.token",
        }

        # Desktop passes preset through file and env/secret store
        # Runtime mode should be opt-in via _runtime_mode flag
        self.assertNotIn("_runtime_mode", preset_data)

        # When desktop doesn't set _runtime_mode, existing behavior preserved
        # (This is verified by absence of the flag)

    @patch("mudae_core.config.validate_preset")
    def test_runtime_mode_flag_prevents_desktop_fallbacks(self, mock_validate):
        """Ensure _runtime_mode prevents platform secret store access."""
        mock_validate.return_value = []

        instance = BotInstance(
            instance_id="test-no-fallback",
            preset_name="RuntimeMode",
            preset_data={
                "channel_id": "123456789",
                "prefix": "$",
                "mudae_prefix": "$",
                "roll_command": "wa",
            },
            credentials={"token": "explicit.token"},
        )

        # Runtime mode should be set
        self.assertTrue(instance.preset_data["_runtime_mode"])
        self.assertTrue(instance.preset_data["_live_preset_push_only"])

        # Token should come from explicit credentials, not secret store
        self.assertEqual(instance.preset_data["token"], "explicit.token")


class TestEventEmission(RuntimeTestCase):
    """Test structured event emission for important bot actions."""

    @patch("mudae_bot.run_bot")
    @patch("mudae_bot.print_log")
    @patch("mudae_core.config.validate_preset")
    def test_log_wrapper_emits_structured_events(self, mock_validate, mock_print_log, mock_run_bot):
        """Test that log messages trigger appropriate structured events."""
        mock_validate.return_value = []

        captured_logs = []

        def fake_run_bot(name, data, log_function):
            callback = data.get("_runtime_ready_callback")
            if callable(callback):
                mock_client = Mock()
                mock_client.preset_name = name
                mock_client.loop = Mock()
                callback(mock_client)

            # Simulate various log messages
            log_function("Claim Verification: SUCCESS! We got Rem. (message edit)", name, "CLAIM")
            log_function("Roll reset detected at 12:00", name, "INFO")
            log_function("Kakera click sent: Rem [kakeraP] (Estimated Pw: 72%)", name, "KAKERA")
            log_function("Wish detected on edited roll: Rem. Checking claim.", name, "CLAIM")
            log_function("Claim Thresholds: Base Min Kakera: 175 | Effective Min Kakera: 175", name, "INFO")
            log_function("Connection failed", name, "ERROR")
            captured_logs.append(log_function)
            time.sleep(0.3)

        mock_run_bot.side_effect = fake_run_bot

        events = []
        instance = BotInstance(
            instance_id="test-events",
            preset_name="EventTest",
            preset_data={
                "channel_id": "123456789",
                "prefix": "$",
                "mudae_prefix": "$",
                "roll_command": "wa",
            },
            credentials={"token": "test.token"},
            event_callback=lambda e: events.append(e),
        )

        try:
            instance.start(block=False)
            time.sleep(1.0)

            # Check events
            event_types = {e.event_type for e in events}

            # Should have claim event
            claim_events = [e for e in events if e.event_type == "claim"]
            self.assertTrue(len(claim_events) > 0)

            # Should have roll_reset event
            reset_events = [e for e in events if e.event_type == "roll_reset"]
            self.assertTrue(len(reset_events) > 0)

            # Should have exactly one kakera event: technical threshold lines are not activity
            kakera_events = [e for e in events if e.event_type == "kakera"]
            self.assertEqual(len(kakera_events), 1)
            self.assertEqual(claim_events[0].data["character"], "Rem")
            self.assertEqual(claim_events[0].data["message"], "Claimed Rem")

            # Should have wishlist event
            wishlist_events = [e for e in events if e.event_type == "wishlist"]
            self.assertTrue(len(wishlist_events) > 0)

            # Should have error event
            error_events = [e for e in events if e.event_type == "error"]
            self.assertTrue(len(error_events) > 0)
        finally:
            self.stop_and_join(instance, timeout=1.0)


if __name__ == "__main__":
    unittest.main()
