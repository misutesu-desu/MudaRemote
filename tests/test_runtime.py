import asyncio
from types import SimpleNamespace
import unittest

from mudae_core.runtime import (
    CommandPacer,
    active_stagger_seconds,
    pause_interruptible_sleep,
    prepare_active_presets,
    set_client_paused,
    split_command_batches,
)
from mudae_core.status import initialize_status_tracking, status_dirty_fields


class _Loop:
    def __init__(self):
        self.calls = []

    def is_running(self):
        return True

    def call_soon_threadsafe(self, callback, *args):
        self.calls.append((callback, args))
        callback(*args)


class _Event:
    def __init__(self):
        self.was_set = False

    def set(self):
        self.was_set = True


class RuntimeStaggerTests(unittest.TestCase):
    def test_command_quantities_are_split_into_ten_item_batches(self):
        self.assertEqual(split_command_batches(0), [])
        self.assertEqual(split_command_batches(10), [10])
        self.assertEqual(split_command_batches(11), [10, 1])
        self.assertEqual(split_command_batches(25), [10, 10, 5])

    def test_stagger_uses_only_selected_runnable_presets_in_launch_order(self):
        presets = {
            "closed": {"token": ""},
            "second": {"token": "token-2"},
            "unused": {"token": "token-unused"},
            "fifth": {"token": "token-5"},
        }

        prepared = prepare_active_presets(
            ["closed", "second", "missing", "fifth"],
            presets,
        )

        self.assertEqual([name for name, _ in prepared], ["second", "fifth"])
        self.assertEqual(
            [data["persistent_stagger_seconds"] for _, data in prepared],
            [0.0, 20.0],
        )
        self.assertNotIn("persistent_stagger_seconds", presets["second"])

    def test_stagger_can_continue_after_already_running_presets(self):
        prepared = prepare_active_presets(
            ["new"],
            {"new": {"token": "token"}},
            start_index=2,
        )

        self.assertEqual(active_stagger_seconds(2), 40.0)
        self.assertEqual(prepared[0][1]["persistent_stagger_seconds"], 40.0)


class RuntimeStateTests(unittest.TestCase):
    def test_idle_pause_is_propagated_without_forcing_status_refresh(self):
        state_event = _Event()
        immediate_event = _Event()
        client = SimpleNamespace(
            is_paused=False,
            desync_detected=False,
            _pause_generation=0,
            _runtime_state_event=state_event,
            _immediate_check_event=immediate_event,
            loop=_Loop(),
        )
        initialize_status_tracking(client)
        set_client_paused(client, True)
        self.assertTrue(client.is_paused)
        self.assertFalse(client.desync_detected)
        self.assertEqual(client._pause_generation, 1)
        self.assertTrue(state_event.was_set)
        self.assertTrue(immediate_event.was_set)

    def test_pause_during_roll_marks_only_roll_state_dirty(self):
        client = SimpleNamespace(
            is_paused=False,
            is_actively_rolling=True,
            is_claiming=False,
            _pause_generation=0,
            _runtime_state_event=_Event(),
            _immediate_check_event=_Event(),
            loop=_Loop(),
        )
        initialize_status_tracking(client)
        set_client_paused(client, True)
        self.assertEqual(status_dirty_fields(client), {"rolls"})

    def test_pause_with_pending_claim_marks_only_claim_state_dirty(self):
        client = SimpleNamespace(
            is_paused=False,
            is_actively_rolling=False,
            pending_claim={"message_id": 1},
            _pause_generation=0,
            _runtime_state_event=_Event(),
            _immediate_check_event=_Event(),
            loop=_Loop(),
        )
        initialize_status_tracking(client)
        set_client_paused(client, True)
        self.assertEqual(status_dirty_fields(client), {"claim"})


class RuntimeAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = SimpleNamespace(
            is_paused=False,
            desync_detected=False,
            _pause_generation=0,
            _runtime_state_event=asyncio.Event(),
            _immediate_check_event=asyncio.Event(),
            loop=asyncio.get_running_loop(),
        )
        initialize_status_tracking(self.client)

    async def test_active_delay_aborts_when_pause_is_requested(self):
        task = asyncio.create_task(pause_interruptible_sleep(self.client, 5, abort_on_pause=True))
        await asyncio.sleep(0)
        set_client_paused(self.client, True)
        self.assertFalse(await asyncio.wait_for(task, timeout=1))

    async def test_regular_delay_waits_for_resume_without_restarting_full_duration(self):
        task = asyncio.create_task(pause_interruptible_sleep(self.client, 0.05))
        await asyncio.sleep(0.01)
        set_client_paused(self.client, True)
        await asyncio.sleep(0.06)
        self.assertFalse(task.done())
        set_client_paused(self.client, False)
        self.assertTrue(await asyncio.wait_for(task, timeout=1))

    async def test_command_pacer_serializes_commands_with_configured_gap(self):
        now = [0.0]
        waits = []
        actions = []

        async def wait(delay):
            waits.append(delay)
            now[0] += delay
            await asyncio.sleep(0)
            return True

        async def action(name):
            actions.append(name)
            await asyncio.sleep(0)

        pacer = CommandPacer(0.6, 0.8, clock=lambda: now[0], jitter=lambda _a, _b: 0.7)
        await asyncio.gather(
            pacer.run(lambda: action("first"), wait),
            pacer.run(lambda: action("second"), wait),
        )

        self.assertEqual(actions, ["first", "second"])
        self.assertEqual(waits, [0.7])

    async def test_command_pacer_does_not_send_when_wait_is_interrupted(self):
        now = [0.0]
        actions = []

        async def wait(_delay):
            return False

        async def action(name):
            actions.append(name)

        pacer = CommandPacer(0.6, 0.8, clock=lambda: now[0], jitter=lambda _a, _b: 0.7)
        self.assertTrue(await pacer.run(lambda: action("first"), wait))
        self.assertFalse(await pacer.run(lambda: action("second"), wait))
        self.assertEqual(actions, ["first"])


if __name__ == "__main__":
    unittest.main()
