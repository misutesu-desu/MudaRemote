"""Focused tests for headless runtime imports and credential-safe logging."""

import asyncio
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import mudae_bot
from mudae_core.bot_runtime import BotInstance
from tests.test_snipe_startup import _Bot


class _RuntimeClient(_Bot):
    def __init__(self, on_run):
        super().__init__()
        self.on_run = on_run
        self.closed = False

    async def start(self, token):
        self.on_run(self, token)

    async def close(self):
        self.closed = True

    def is_closed(self):
        return self.closed

    def run(self, token, reconnect=True, log_handler=None):
        assert reconnect is True and log_handler is None
        self.on_run(self, token)


class RuntimeIsolationTests(unittest.TestCase):
    def test_desktop_runner_disables_duplicate_discord_log_handler(self):
        client = _RuntimeClient(lambda *_args: None)
        mudae_bot._mobile_runtime_stop_event.clear()
        with patch.object(mudae_bot.commands, "Bot", return_value=client), \
             patch.object(mudae_bot, "IS_TERMUX", False):
            mudae_bot.run_bot("desktop-contract", {
                "token": "dummy-token",
                "channel_id": 1234,
                "prefix": "!",
                "mudae_prefix": "$",
                "rolling": False,
                "skip_initial_commands": True,
            })

    def test_import_is_headless_with_missing_app_directory_and_denied_writes(self):
        script = r'''
import builtins
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.getcwd())
import mudae_bot

import tempfile

app_dir = os.path.join(tempfile.gettempdir(), "mudae-headless-missing-app-dir-{}".format(os.getpid()))
assert not os.path.exists(app_dir)
mudae_bot.get_base_path = lambda: app_dir
mudae_bot.presets_path = os.path.join(app_dir, "presets.json")

def denied(*args, **kwargs):
    raise PermissionError("simulated read/write denial")

with patch.object(mudae_bot, "atomic_write_json", side_effect=denied) as writes, \
     patch.object(mudae_bot.SecretStore, "get_tokens", side_effect=denied) as reads, \
     patch.object(builtins, "open", side_effect=denied):
    import mudae_core.bot_runtime
    assert mudae_bot.presets == {}
    assert not os.path.exists(app_dir)
    writes.assert_not_called()
    reads.assert_not_called()
'''
        env = os.environ.copy()
        env.pop("TEMP", None)
        env.pop("TMP", None)
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def _run_real_runtime_setup(self, token, other_token=None):
        events = []
        entered = threading.Event()
        instance = BotInstance(
            instance_id="runtime-isolation",
            preset_name="Isolation",
            preset_data={
                "channel_id": "123456789",
                "prefix": "!",
                "mudae_prefix": "$",
                "rolling": False,
                "skip_initial_commands": True,
                "_runtime_max_retries": 1,
                "_runtime_retry_delay": 0,
            },
            credentials={"token": token},
            event_callback=events.append,
        )
        instance.preset_data["_preset_outcome_observer"] = instance._on_preset_outcome

        def on_run(client, supplied_token):
            self.assertEqual(supplied_token, token)

            def bad_observer(_outcome):
                raise RuntimeError("reload observer rejected " + token)

            client._preset_reload.observer = bad_observer
            client._preset_reload._report_outcome(17, "rejected", "contains " + token)
            entered.set()
            raise RuntimeError("client startup failed for " + token)

        client = _RuntimeClient(on_run)
        mudae_bot._mobile_runtime_stop_event.clear()
        try:
            with patch.object(mudae_bot.commands, "Bot", new=lambda *args, **kwargs: client), \
                 patch.object(mudae_bot, "IS_TERMUX", False), \
                 patch("mudae_core.config.validate_preset", return_value=[]):
                self.assertTrue(instance.start())
                self.assertTrue(entered.wait(2), "run_bot did not reach fake client boundary")
                deadline = time.monotonic() + 2
                while instance.state.value != "failed" and time.monotonic() < deadline:
                    time.sleep(0.005)
                self.assertEqual(instance.state.value, "failed")
                self.assertTrue(
                    any(event.event_type == "error" and event.data.get("retry_count") == 1
                        for event in events),
                    repr([(event.event_type, event.data) for event in events]),
                )
                self.assertTrue(instance.stop(timeout=2))
                self.assertTrue(client.closed)
        finally:
            mudae_bot._mobile_runtime_stop_event.clear()

        serialized_events = repr([(event.event_type, event.data) for event in events])
        serialized_status = repr(instance.get_status()) + repr(instance._preset_outcomes)
        self.assertNotIn(token, serialized_events)
        self.assertNotIn(token, serialized_status)
        if other_token:
            self.assertNotIn(other_token, serialized_events)
            self.assertNotIn(other_token, serialized_status)
        log_messages = [
            event.data["message"]
            for event in events
            if event.event_type == "log"
        ]
        self.assertEqual(
            log_messages,
            [
                "[REDACTED_TOKEN]",
                "Preset outcome observer error: reload observer rejected [REDACTED]",
            ],
        )
        error_messages = [
            event.data.get("message", "")
            for event in events
            if event.event_type == "error"
        ]
        self.assertEqual(
            error_messages,
            [
                "Preset outcome observer error: reload observer rejected [REDACTED]",
                "Instance crashed: client startup failed for [REDACTED]",
            ],
        )
        return events

    def test_runtime_exception_and_reload_observer_secrets_never_reach_sinks(self):
        with tempfile.TemporaryDirectory() as app_dir:
            with patch.object(mudae_bot, "get_base_path", return_value=app_dir), \
                 patch.object(mudae_bot, "atomic_write_json", side_effect=PermissionError), \
                 patch.object(mudae_bot.SecretStore, "get_tokens", side_effect=PermissionError):
                self._run_real_runtime_setup("q7")
            self.assertEqual(os.listdir(app_dir), [])

    def test_runtime_cleanup_without_python39_executor_shutdown(self):
        # Exercise the real owned-loop cleanup while simulating Python 3.8's API.
        sample_loop = asyncio.new_event_loop()
        loop_class = type(sample_loop)
        sample_loop.close()

        class LegacyLoop(loop_class):
            def __getattribute__(self, name):
                if name == "shutdown_default_executor":
                    raise AttributeError(name)
                return super().__getattribute__(name)

        with patch("mudae_core.bot_runtime.asyncio.new_event_loop", side_effect=LegacyLoop):
            self._run_real_runtime_setup("legacy-loop-token")

    def test_independent_runtime_tokens_do_not_cross_leak(self):
        with tempfile.TemporaryDirectory() as app_dir:
            with patch.object(mudae_bot, "get_base_path", return_value=app_dir):
                self._run_real_runtime_setup("alpha-9", "beta-8")
                self._run_real_runtime_setup("beta-8", "alpha-9")
            self.assertEqual(os.listdir(app_dir), [])


if __name__ == "__main__":
    unittest.main()
