import asyncio
import datetime
from types import SimpleNamespace
import unittest

from mudae_core.runtime import (
    CommandPacer,
    PendingMkRollOperation,
    RollActionTiming,
    RollCommandCorrelation,
    active_stagger_seconds,
    can_resume_claim_interrupted_rolls,
    daily_rolls_decision,
    humanized_claim_refresh_deadline,
    interaction_command_name,
    mudae_command_ack_matches,
    next_daily_rolls_wake_deadline,
    normalized_mudae_command_matches,
    pause_interruptible_sleep,
    prepare_active_presets,
    roll_replenishment_cycle_key,
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


class _Future:
    def __init__(self):
        self.value = "pending"

    def done(self):
        return self.value != "pending"

    def set_result(self, value):
        self.value = value


class RuntimeStaggerTests(unittest.TestCase):
    def test_slash_command_name_is_normalized_across_metadata_shapes(self):
        self.assertEqual(interaction_command_name(SimpleNamespace(name="/MK")), "mk")
        self.assertEqual(interaction_command_name(SimpleNamespace(data={"name": "wa"})), "wa")

    def test_pending_text_mk_requires_the_exact_automated_command(self):
        now = datetime.datetime(2026, 8, 26, 10, tzinfo=datetime.timezone.utc)
        operation = PendingMkRollOperation(1, 10, 20, now)
        operation.mark_sent({"mode": "text", "message_id": 100, "sent_at_utc": now})

        common = dict(
            channel_id=10, message_id=101, created_at_utc=now + datetime.timedelta(seconds=1),
            owner_id=20, command_name="mk", source_mode="text",
        )
        self.assertTrue(operation.matches(**common, source_message_id=100))
        self.assertFalse(operation.matches(**common, source_message_id=99))
        self.assertFalse(operation.matches(**{**common, "command_name": "wa"}, source_message_id=100))

    def test_pending_slash_mk_rejects_unrelated_manual_roll_and_times_out(self):
        now = datetime.datetime(2026, 8, 26, 10, tzinfo=datetime.timezone.utc)
        operation = PendingMkRollOperation(1, 10, 20, now)
        operation.mark_sent({"mode": "slash", "nonce": "abc", "sent_at_utc": now})

        self.assertTrue(operation.matches(
            channel_id=10, message_id=200, created_at_utc=now + datetime.timedelta(seconds=1),
            owner_id=20, command_name="mk", source_mode="slash",
        ))
        self.assertFalse(operation.matches(
            channel_id=10, message_id=201, created_at_utc=now + datetime.timedelta(seconds=1),
            owner_id=20, command_name="wa", source_mode="slash",
        ))
        self.assertFalse(operation.matches(
            channel_id=10, message_id=202, created_at_utc=now + datetime.timedelta(seconds=46),
            owner_id=20, command_name="mk", source_mode="slash",
        ))
        operation.processed_message_id = 200
        self.assertFalse(operation.matches(
            channel_id=10, message_id=200, created_at_utc=now + datetime.timedelta(seconds=1),
            owner_id=20, command_name="mk", source_mode="slash",
        ))

    def test_roll_action_delay_is_drawn_once_and_reused_for_the_cycle(self):
        timing = RollActionTiming()
        now = datetime.datetime(2026, 8, 26, 10, tzinfo=datetime.timezone.utc)
        draws = []

        def draw(start, end):
            draws.append((start, end))
            return 120

        first = timing.schedule(
            cycle_key="cycle-1", now_utc=now, humanization_enabled=True,
            window_minutes=10, random_source=draw,
        )
        repeated = timing.schedule(
            cycle_key="cycle-1", now_utc=now + datetime.timedelta(seconds=30),
            humanization_enabled=True, window_minutes=10, random_source=draw,
        )

        self.assertEqual(first, now + datetime.timedelta(seconds=120))
        self.assertEqual(repeated, first)
        self.assertEqual(len(draws), 1)
        timing.schedule(
            cycle_key="cycle-2", now_utc=now + datetime.timedelta(hours=1),
            humanization_enabled=True, window_minutes=10, random_source=draw,
        )
        self.assertEqual(len(draws), 2)


class RollCommandCorrelationBehaviorTests(unittest.IsolatedAsyncioTestCase):
    def make_operation(self, generation=1):
        now = datetime.datetime.now(datetime.timezone.utc)
        return PendingMkRollOperation(
            generation=generation,
            channel_id=10,
            expected_user_id=20,
            registered_at_utc=now,
            future=asyncio.get_running_loop().create_future(),
        )

    async def test_slash_response_can_arrive_before_send_returns(self):
        tracker = RollCommandCorrelation()
        operation = self.make_operation()
        request_started = asyncio.Event()
        release_request = asyncio.Event()
        calls = []

        async def send_slash():
            token = tracker.prearm(
                channel_id=10, owner_id=20, owner_name="self", command_name="mk",
                mode="slash", operation=operation,
            )
            request_started.set()
            await release_request.wait()
            tracker.finalize(token, {"mode": "slash", "nonce": "abc"}, operation)

        async def handle(**kwargs):
            calls.append(kwargs)

        send_task = asyncio.create_task(send_slash())
        await request_started.wait()
        handled = await tracker.route_pending_mk_response(
            operation=operation, channel_id=10, message_id=200,
            created_at_utc=datetime.datetime.now(datetime.timezone.utc),
            interaction_owner_id=20, interaction_command_name="mk", handler=handle,
        )
        self.assertTrue(handled)
        self.assertEqual(calls, [{"is_mk_roll": True}])
        self.assertFalse(send_task.done())
        release_request.set()
        await send_task

    async def test_text_response_waits_at_send_receipt_boundary(self):
        tracker = RollCommandCorrelation()
        operation = self.make_operation()
        token = tracker.prearm(
            channel_id=10, owner_id=20, owner_name="self", command_name="mk",
            mode="text", operation=operation,
        )
        handler_called = asyncio.Event()

        async def handle(**kwargs):
            self.assertTrue(kwargs["is_mk_roll"])
            handler_called.set()

        response_task = asyncio.create_task(tracker.route_pending_mk_response(
            operation=operation, channel_id=10, message_id=101,
            created_at_utc=datetime.datetime.now(datetime.timezone.utc),
            handler=handle,
        ))
        await asyncio.sleep(0)
        self.assertFalse(handler_called.is_set())
        tracker.finalize(token, {
            "mode": "text", "message_id": 100,
            "sent_at_utc": datetime.datetime.now(datetime.timezone.utc),
        }, operation)
        self.assertTrue(await response_task)
        self.assertTrue(handler_called.is_set())

    async def test_text_mk_survives_more_than_twelve_unrelated_messages(self):
        tracker = RollCommandCorrelation()
        operation = self.make_operation()
        sent_at = datetime.datetime.now(datetime.timezone.utc)
        token = tracker.prearm(
            channel_id=10, owner_id=20, owner_name="self", command_name="mk",
            mode="text", operation=operation, registered_at_utc=sent_at,
        )
        tracker.finalize(token, {
            "mode": "text", "message_id": 100, "sent_at_utc": sent_at,
        }, operation)
        unrelated_message_ids = list(range(101, 114))
        calls = []

        async def handle(**kwargs):
            calls.append(kwargs)

        handled = await tracker.route_pending_mk_response(
            operation=operation, channel_id=10,
            message_id=unrelated_message_ids[-1] + 1,
            created_at_utc=sent_at + datetime.timedelta(seconds=2), handler=handle,
        )
        self.assertTrue(handled)
        self.assertEqual(calls, [{"is_mk_roll": True}])

    async def test_unrelated_manual_self_roll_is_not_stolen_by_pending_mk(self):
        tracker = RollCommandCorrelation()
        operation = self.make_operation()
        sent_at = datetime.datetime.now(datetime.timezone.utc)
        token = tracker.prearm(
            channel_id=10, owner_id=20, owner_name="self", command_name="mk",
            mode="text", operation=operation, registered_at_utc=sent_at,
        )
        tracker.finalize(token, {
            "mode": "text", "message_id": 100, "sent_at_utc": sent_at,
        }, operation)
        tracker.observe_text_command(
            channel_id=10, owner_id=20, owner_name="self", command_name="wa",
            message_id=101, sent_at_utc=sent_at + datetime.timedelta(seconds=1),
        )
        mk_calls = []

        async def handle(**kwargs):
            mk_calls.append(kwargs)

        handled = await tracker.route_pending_mk_response(
            operation=operation, channel_id=10, message_id=102,
            created_at_utc=sent_at + datetime.timedelta(seconds=2), handler=handle,
        )
        self.assertFalse(handled)
        self.assertEqual(mk_calls, [])
        manual_origin = tracker.latest_text_origin(
            channel_id=10, message_id=102,
            created_at_utc=sent_at + datetime.timedelta(seconds=2),
        )
        self.assertEqual(manual_origin.command_name, "wa")
        tracker.consume_text_origin(manual_origin, 102)
        self.assertTrue(await tracker.route_pending_mk_response(
            operation=operation, channel_id=10, message_id=103,
            created_at_utc=sent_at + datetime.timedelta(seconds=3), handler=handle,
        ))
        self.assertEqual(mk_calls, [{"is_mk_roll": True}])

    async def test_correlated_mk_is_processed_exactly_once_as_mk(self):
        tracker = RollCommandCorrelation()
        operation = self.make_operation()
        sent_at = datetime.datetime.now(datetime.timezone.utc)
        token = tracker.prearm(
            channel_id=10, owner_id=20, owner_name="self", command_name="mk",
            mode="text", operation=operation, registered_at_utc=sent_at,
        )
        tracker.finalize(token, {
            "mode": "text", "message_id": 100, "sent_at_utc": sent_at,
        }, operation)
        calls = []

        async def handle(**kwargs):
            calls.append(kwargs)

        first = await tracker.route_pending_mk_response(
            operation=operation, channel_id=10, message_id=101,
            created_at_utc=sent_at + datetime.timedelta(seconds=1), handler=handle,
        )
        duplicate = await tracker.route_pending_mk_response(
            operation=operation, channel_id=10, message_id=101,
            created_at_utc=sent_at + datetime.timedelta(seconds=1), handler=handle,
        )
        self.assertTrue(first)
        self.assertTrue(duplicate)
        self.assertEqual(calls, [{"is_mk_roll": True}])

    async def test_correlated_mk_cannot_fall_through_to_normal_self(self):
        tracker = RollCommandCorrelation()
        operation = self.make_operation()
        sent_at = datetime.datetime.now(datetime.timezone.utc)
        token = tracker.prearm(
            channel_id=10, owner_id=20, owner_name="self", command_name="mk",
            mode="text", operation=operation, registered_at_utc=sent_at,
        )
        tracker.finalize(token, {
            "mode": "text", "message_id": 100, "sent_at_utc": sent_at,
        }, operation)
        paths = []

        async def handle(**kwargs):
            paths.append("mk" if kwargs["is_mk_roll"] else "normal")

        handled = await tracker.route_pending_mk_response(
            operation=operation, channel_id=10, message_id=101,
            created_at_utc=sent_at + datetime.timedelta(seconds=1), handler=handle,
        )
        if not handled:
            paths.append("normal")
        self.assertEqual(paths, ["mk"])

    async def test_command_correlation_ledger_is_bounded(self):
        tracker = RollCommandCorrelation(max_entries=8, ttl_seconds=45)
        sent_at = datetime.datetime.now(datetime.timezone.utc)
        for index in range(20):
            tracker.observe_text_command(
                channel_id=10, owner_id=20, owner_name="self", command_name="wa",
                message_id=100 + index,
                sent_at_utc=sent_at + datetime.timedelta(milliseconds=index),
            )
        self.assertEqual(len(tracker._entries), 8)

    def test_roll_action_delay_off_zero_window_stagger_and_clamp(self):
        now = datetime.datetime(2026, 8, 26, 10, tzinfo=datetime.timezone.utc)
        immediate = RollActionTiming().schedule(
            cycle_key=1, now_utc=now, humanization_enabled=False, window_minutes=40,
        )
        zero_window = RollActionTiming().schedule(
            cycle_key=1, now_utc=now, humanization_enabled=True, window_minutes=0,
        )
        staggered = RollActionTiming().schedule(
            cycle_key=1, now_utc=now, persistent_stagger_seconds=40,
        )
        clamped = RollActionTiming().schedule(
            cycle_key=1, now_utc=now, latest_action_at_utc=now + datetime.timedelta(seconds=10),
            humanization_enabled=True, window_minutes=40,
            random_source=lambda _start, _end: 300,
        )

        self.assertEqual(immediate, now)
        self.assertEqual(zero_window, now)
        self.assertEqual(staggered, now + datetime.timedelta(seconds=40))
        self.assertEqual(clamped, now + datetime.timedelta(seconds=10))

    def test_roll_cycle_key_tolerates_minute_rounding_but_changes_next_hour(self):
        first = datetime.datetime(2026, 8, 26, 11, 0, 20, tzinfo=datetime.timezone.utc)
        repeated = first + datetime.timedelta(seconds=40)
        next_cycle = first + datetime.timedelta(hours=1)
        self.assertEqual(roll_replenishment_cycle_key(first), roll_replenishment_cycle_key(repeated))
        self.assertNotEqual(roll_replenishment_cycle_key(first), roll_replenishment_cycle_key(next_cycle))

    def test_mudae_command_ack_requires_matching_message_bot_and_checkmark(self):
        payload = SimpleNamespace(
            message_id=123,
            user_id=456,
            emoji=SimpleNamespace(name="✅"),
        )

        self.assertTrue(mudae_command_ack_matches(payload, 123, 456))
        self.assertFalse(mudae_command_ack_matches(payload, 999, 456))
        self.assertFalse(mudae_command_ack_matches(payload, 123, 999))
        payload.emoji.name = "❌"
        self.assertFalse(mudae_command_ack_matches(payload, 123, 456))

    def test_manual_rt_command_match_is_exact_and_normalized(self):
        self.assertTrue(normalized_mudae_command_matches("  $RT  ", "$", "rt"))
        self.assertFalse(normalized_mudae_command_matches("$rt now", "$", "rt"))
        self.assertFalse(normalized_mudae_command_matches("$ru", "$", "rt"))

    def test_daily_rolls_waits_for_claim_reset_inside_eligible_roll_interval(self):
        now = datetime.datetime(2026, 8, 25, 12, tzinfo=datetime.timezone.utc)
        claim_reset = now + datetime.timedelta(minutes=20)
        decision = daily_rolls_decision(
            enabled=True, only_claim_hour=True, claim_right_available=False,
            key_mode=False, auto_rolls_in_key_mode=False,
            next_claim_reset_at_utc=claim_reset,
            roll_reset_at_utc=now + datetime.timedelta(minutes=50),
            used_this_interval=False, limit_reached=False, ack_retry_ready=True,
            now_utc=now,
        )
        self.assertEqual(decision, "wait-claim-reset")
        self.assertEqual(next_daily_rolls_wake_deadline(decision, claim_reset), claim_reset)

    def test_daily_rolls_executes_when_claim_is_ready_in_claim_hour(self):
        now = datetime.datetime(2026, 8, 25, 12, tzinfo=datetime.timezone.utc)
        self.assertEqual(daily_rolls_decision(
            enabled=True, only_claim_hour=True, claim_right_available=True,
            key_mode=False, auto_rolls_in_key_mode=False,
            next_claim_reset_at_utc=now + datetime.timedelta(minutes=20),
            roll_reset_at_utc=now + datetime.timedelta(minutes=50),
            used_this_interval=False, limit_reached=False, ack_retry_ready=True,
            now_utc=now,
        ), "execute")
        # After the reset, $tu may have already replaced the old deadline with
        # the next claim cycle.  The selected roll interval remains eligible.
        self.assertEqual(daily_rolls_decision(
            enabled=True, only_claim_hour=True, claim_right_available=True,
            key_mode=False, auto_rolls_in_key_mode=False,
            next_claim_reset_at_utc=now + datetime.timedelta(hours=3),
            roll_reset_at_utc=now + datetime.timedelta(minutes=30),
            used_this_interval=False, limit_reached=False, ack_retry_ready=True,
            claim_hour_active=True, now_utc=now,
        ), "execute")

    def test_daily_rolls_rejects_claim_reset_after_roll_interval_and_preserves_bypasses(self):
        now = datetime.datetime(2026, 8, 25, 12, tzinfo=datetime.timezone.utc)
        common = dict(
            enabled=True, only_claim_hour=True, claim_right_available=False,
            key_mode=False, auto_rolls_in_key_mode=False,
            next_claim_reset_at_utc=now + datetime.timedelta(minutes=50),
            roll_reset_at_utc=now + datetime.timedelta(minutes=20),
            used_this_interval=False, limit_reached=False, ack_retry_ready=True,
            now_utc=now,
        )
        self.assertEqual(daily_rolls_decision(**common), "outside-claim-hour")
        self.assertEqual(daily_rolls_decision(
            **{**common, "only_claim_hour": False, "claim_right_available": True}
        ), "execute")
        self.assertEqual(daily_rolls_decision(
            **{**common, "key_mode": True, "auto_rolls_in_key_mode": True,
               "next_claim_reset_at_utc": now + datetime.timedelta(minutes=10),
               "roll_reset_at_utc": now + datetime.timedelta(minutes=20)}
        ), "execute")

    def test_snipe_claim_refresh_uses_one_delay_inside_humanization_window(self):
        reset_at = datetime.datetime(2026, 8, 4, 12, tzinfo=datetime.timezone.utc)
        deadline = humanized_claim_refresh_deadline(
            reset_at,
            humanization_enabled=True,
            window_minutes=40,
            jitter=lambda start, end: (start + end) / 4,
        )
        self.assertEqual(deadline, reset_at + datetime.timedelta(minutes=10))

    def test_snipe_claim_refresh_stays_exact_when_humanization_is_disabled(self):
        reset_at = datetime.datetime(2026, 8, 4, 12, tzinfo=datetime.timezone.utc)
        self.assertEqual(
            humanized_claim_refresh_deadline(reset_at, False, 40),
            reset_at,
        )

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

    def test_one_preset_expands_multiple_secure_tokens(self):
        prepared = prepare_active_presets(
            ["main"],
            {"main": {"token": "legacy-first", "tokens": ["first", "second"]}},
        )

        self.assertEqual([name for name, _ in prepared], ["main", "main #2"])
        self.assertEqual([data["token"] for _, data in prepared], ["first", "second"])
        self.assertEqual(
            [data["persistent_stagger_seconds"] for _, data in prepared],
            [0.0, 20.0],
        )

    def test_empty_new_token_list_falls_back_to_legacy_token(self):
        prepared = prepare_active_presets(
            ["legacy"],
            {"legacy": {"token": "old-token", "tokens": []}},
        )
        self.assertEqual(prepared[0][1]["token"], "old-token")


class RuntimeStateTests(unittest.TestCase):
    def test_pause_clears_pending_mk_without_leaving_a_cancelled_wait(self):
        future = _Future()
        pending = PendingMkRollOperation(
            generation=1,
            channel_id=10,
            expected_user_id=20,
            registered_at_utc=datetime.datetime.now(datetime.timezone.utc),
            future=future,
        )
        client = SimpleNamespace(
            is_paused=False,
            is_actively_rolling=False,
            pending_claim=None,
            _pending_mk_roll=pending,
            _pause_generation=0,
            _runtime_state_event=_Event(),
            _immediate_check_event=_Event(),
            loop=_Loop(),
        )
        initialize_status_tracking(client)

        set_client_paused(client, True)

        self.assertIsNone(client._pending_mk_roll)
        self.assertIsNone(future.value)
        self.assertEqual(status_dirty_fields(client), {"rolls"})

    def test_key_mode_resumes_locally_known_rolls_after_claim_interrupt(self):
        client = SimpleNamespace(
            rolling_enabled=True,
            is_paused=False,
            key_limit_hit=False,
            pending_claim=None,
            rolls_left=7,
            key_mode=True,
            claim_right_available=False,
            rt_available=False,
        )
        self.assertTrue(can_resume_claim_interrupted_rolls(client))

    def test_unresolved_claim_does_not_resume_locally_known_rolls(self):
        client = SimpleNamespace(
            rolling_enabled=True,
            is_paused=False,
            key_limit_hit=False,
            pending_claim={"message_id": 1},
            rolls_left=7,
            key_mode=True,
            claim_right_available=False,
            rt_available=False,
        )
        self.assertFalse(can_resume_claim_interrupted_rolls(client))

    def test_non_key_mode_requires_an_available_claim_path_to_resume(self):
        client = SimpleNamespace(
            rolling_enabled=True,
            is_paused=False,
            key_limit_hit=False,
            pending_claim=None,
            rolls_left=7,
            key_mode=False,
            claim_right_available=False,
            rt_available=False,
        )
        self.assertFalse(can_resume_claim_interrupted_rolls(client))
        client.claim_right_available = True
        self.assertTrue(can_resume_claim_interrupted_rolls(client))

    def test_timing_mode_allows_resuming_rolls_before_claim_reset(self):
        client = SimpleNamespace(
            rolling_enabled=True,
            is_paused=False,
            key_limit_hit=False,
            pending_claim=None,
            rolls_left=10,
            key_mode=False,
            claim_right_available=False,
            rt_available=False,
            is_timing_mode_active=True,
        )
        self.assertTrue(can_resume_claim_interrupted_rolls(client))

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

    async def test_command_pacer_returns_nonempty_action_result(self):
        async def wait(_delay):
            return True

        expected = object()

        async def action():
            return expected

        pacer = CommandPacer(0, 0)

        self.assertIs(await pacer.run(action, wait), expected)


if __name__ == "__main__":
    unittest.main()
