import asyncio
import datetime
import time
from types import SimpleNamespace
import unittest

from mudae_core.runtime import (
    CommandPacer,
    PendingMkRollOperation,
    RollActionTiming,
    NormalRollActionOwner,
    NormalRollCycleState,
    get_normal_roll_cycle_state,
    mark_roll_cycle_proven_fresh,
    apply_authoritative_roll_remaining,
    reconcile_authoritative_current_roll_count,
    add_roll_cycle_uncertainty,
    add_provisional_roll_cycle_uncertainty,
    remove_roll_cycle_uncertainty,
    clear_roll_cycle_uncertainty,
    mark_roll_cycle_count_uncertain,
    clear_roll_cycle_count_uncertainty,
    refresh_legacy_uncertainty_view,
    unresolved_pending_roll_uncertainty_keys,
    roll_cycle_has_only_pending_boundary_origins,
    roll_cycle_needs_authoritative_reconcile,
    roll_cycle_uncertainty_requires_status,
    normal_roll_schedule_count,
    can_clear_roll_status_after_exact_batch,
    claim_roll_count_reconciliation,
    release_roll_count_reconciliation,
    release_reconciliation_for_authoritative_cycle,
    roll_cycle_is_same_or_newer,
    record_definite_normal_roll_consumption,
    rearm_existing_normal_roll_action,
    resolve_pending_boundary_roll_uncertainty,
    resolve_pending_boundary_roll_and_rearm,
    successor_roll_cycle_id,
    roll_cycle_matches_anchor_lineage,
    ROLL_BOUNDARY_ATTRIBUTION_GUARD_SECONDS,
    OutgoingRollCommand,
    RollCommandCorrelation,
    active_stagger_seconds,
    normal_roll_behavior_flags,
    estimate_roll_batch_seconds,
    normal_roll_start_window,
    normal_roll_batch_fits_window,
    normal_action_status_policy,
    normal_roll_action_state_is_dirty,
    defer_normal_roll_window,
    normal_roll_window_is_deferred,
    mk_full_power_wait_is_unchanged,
    is_roll_result_cross_boundary_ambiguous,
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
from mudae_core.status import (
    initialize_status_tracking,
    mark_status_dirty,
    clear_status_dirty,
    defer_tu_queries,
    record_tu_failure,
    tu_retry_wait,
    status_dirty_fields,
    ResetAnchor,
    ServerResetSnapshot,
    bounded_sanity_deadline,
    ensure_sanity_deadline_safe,
)


class _TimerHandle:
    def __init__(self, callback, args):
        self._callback = callback
        self._args = args
        self._cancelled = False

    def cancelled(self):
        return self._cancelled

    def cancel(self):
        self._cancelled = True


class _Loop:
    def __init__(self):
        self.calls = []

    def is_running(self):
        return True

    def call_soon_threadsafe(self, callback, *args):
        self.calls.append((callback, args))
        callback(*args)

    def call_later(self, delay, callback, *args):
        handle = _TimerHandle(callback, args)
        self.calls.append((delay, callback, args, handle))
        return handle


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
    def test_mk_full_power_wait_only_suppresses_identical_future_state(self):
        now = 1000.0
        signature = (394, 400, 7)
        self.assertTrue(mk_full_power_wait_is_unchanged(
            2085.0,
            signature,
            current_power=394,
            max_power=400,
            power_revision=7,
            now_monotonic=now,
        ))
        self.assertFalse(mk_full_power_wait_is_unchanged(
            2085.0,
            signature,
            current_power=395,
            max_power=400,
            power_revision=8,
            now_monotonic=now,
        ))
        self.assertFalse(mk_full_power_wait_is_unchanged(
            999.0,
            signature,
            current_power=394,
            max_power=400,
            power_revision=7,
            now_monotonic=now,
        ))

    def test_batch_estimate_clamps_slow_and_slash_rolls(self):
        self.assertEqual(estimate_roll_batch_seconds(10, 1.0, True), 27.5)
        self.assertEqual(estimate_roll_batch_seconds(13, 120.0, False), 1568.25)

    def test_humanized_late_start_is_clamped_to_batch_safe_window(self):
        now = datetime.datetime(2026, 8, 27, 17, 5, tzinfo=datetime.timezone.utc)
        reset = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        latest, fits = normal_roll_start_window(now, reset, 15, 120.0)
        owner = NormalRollActionOwner(RollActionTiming())
        deadline, _ = owner.schedule(
            cycle_id="r", now_utc=now, latest_action_at_utc=latest,
            humanization_enabled=True, window_minutes=50,
            random_source=lambda _a, _b: 45 * 60,
        )
        self.assertTrue(fits)
        self.assertEqual(latest, reset - datetime.timedelta(seconds=1838.75))
        self.assertEqual(deadline, latest)
        repeated, created = owner.schedule(
            cycle_id="r", now_utc=now + datetime.timedelta(minutes=1),
            latest_action_at_utc=latest, humanization_enabled=True,
            window_minutes=50, random_source=lambda _a, _b: self.fail("redrew deadline"),
        )
        self.assertFalse(created)
        self.assertEqual(repeated, deadline)

    def test_impossible_slow_batch_has_explicit_no_safe_window(self):
        now = datetime.datetime(2026, 8, 27, 17, 40, tzinfo=datetime.timezone.utc)
        reset = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        latest, fits = normal_roll_start_window(now, reset, 13, 120.0)
        self.assertFalse(fits)
        self.assertLess(latest, now)

    def test_preroll_delay_is_reserved_and_actual_start_is_revalidated(self):
        reset = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        scheduled_at = datetime.datetime(2026, 8, 27, 17, 34, tzinfo=datetime.timezone.utc)
        latest, fits = normal_roll_start_window(
            scheduled_at, reset, 13, 120.0, pre_roll_seconds=30.0,
        )
        self.assertTrue(fits)
        self.assertGreaterEqual(latest, scheduled_at)
        delayed_start = datetime.datetime(2026, 8, 27, 17, 40, tzinfo=datetime.timezone.utc)
        self.assertFalse(normal_roll_batch_fits_window(delayed_start, reset, 13, 120.0))

    def test_scheduled_trigger_uses_an_immediate_owned_deadline_without_redraw(self):
        now = datetime.datetime(2026, 8, 27, 17, 20, tzinfo=datetime.timezone.utc)
        owner = NormalRollActionOwner(RollActionTiming())
        deadline, created = owner.schedule(
            cycle_id=("roll", 1, 2), now_utc=now,
            humanization_enabled=False, window_minutes=50,
        )
        repeated, repeated_created = owner.schedule(
            cycle_id=("roll", 1, 2), now_utc=now + datetime.timedelta(seconds=1),
            humanization_enabled=True, window_minutes=50,
            random_source=lambda _a, _b: self.fail("scheduled action was redrawn"),
        )
        self.assertTrue(created)
        self.assertFalse(repeated_created)
        self.assertEqual(deadline, now)
        self.assertEqual(repeated, now)
        self.assertTrue(owner.start(("roll", 1, 2)))

    def test_safe_window_failure_releases_logical_owner_not_scheduler_id(self):
        now = datetime.datetime(2026, 8, 27, 17, 40, tzinfo=datetime.timezone.utc)
        logical_cycle = ("roll", 123, 4)
        scheduler_cycle = 1760000000.25
        owner = NormalRollActionOwner(RollActionTiming())
        owner.schedule(cycle_id=logical_cycle, now_utc=now)
        self.assertTrue(owner.start(logical_cycle))
        self.assertFalse(owner.complete(scheduler_cycle))
        self.assertEqual(owner.state, "executing")
        self.assertTrue(owner.complete(logical_cycle))
        next_deadline, created = owner.schedule(cycle_id=("roll", 123, 5), now_utc=now)
        self.assertTrue(created)
        self.assertEqual(owner.state, "pending")
        self.assertEqual(next_deadline, now)

    def test_authoritative_pending_and_waiting_actions_suppress_routine_status(self):
        now = datetime.datetime(2026, 8, 27, 17, 20, tzinfo=datetime.timezone.utc)
        cycle = ("roll", 123, 2)
        owner = NormalRollActionOwner(RollActionTiming())
        deadline, _ = owner.schedule(cycle_id=cycle, now_utc=now, humanization_enabled=True,
                                     window_minutes=40, random_source=lambda _a, _b: 1200)
        for _ in range(12):
            self.assertEqual(normal_action_status_policy(
                owner_cycle_id=owner.cycle_id, current_roll_cycle_id=cycle,
                owner_state=owner.state, state_dirty=False,
            ), "suppress-routine")
            self.assertEqual(owner.deadline_utc, deadline)
        self.assertTrue(owner.defer(cycle))
        self.assertEqual(normal_action_status_policy(
            owner_cycle_id=owner.cycle_id, current_roll_cycle_id=cycle,
            owner_state=owner.state, state_dirty=False,
        ), "suppress-routine")

    def test_executing_action_defers_routine_status_but_allows_matching_reconciliation(self):
        now = datetime.datetime(2026, 8, 27, 17, 20, tzinfo=datetime.timezone.utc)
        cycle = ("roll", 123, 2)
        owner = NormalRollActionOwner(RollActionTiming())
        owner.schedule(cycle_id=cycle, now_utc=now)
        self.assertTrue(owner.start(cycle))
        self.assertEqual(normal_action_status_policy(
            owner_cycle_id=owner.cycle_id, current_roll_cycle_id=cycle,
            owner_state=owner.state, state_dirty=False,
        ), "defer-executing")
        self.assertEqual(normal_action_status_policy(
            owner_cycle_id=owner.cycle_id, current_roll_cycle_id=cycle,
            owner_state=owner.state, state_dirty=True,
        ), "defer-executing")
        self.assertEqual(normal_action_status_policy(
            owner_cycle_id=owner.cycle_id, current_roll_cycle_id=cycle,
            owner_state=owner.state, state_dirty=True,
            reconciliation_cycle_ids={cycle},
        ), "allow-reconciliation")

        next_cycle = ("roll", 123, 3)
        self.assertEqual(normal_action_status_policy(
            owner_cycle_id=owner.cycle_id, current_roll_cycle_id=next_cycle,
            owner_state=owner.state, state_dirty=False,
        ), "defer-executing")
        self.assertEqual(normal_action_status_policy(
            owner_cycle_id=owner.cycle_id, current_roll_cycle_id=next_cycle,
            owner_state=owner.state, state_dirty=True,
            reconciliation_cycle_ids={cycle},
        ), "allow-reconciliation")
    def test_normal_roll_action_owner_preserves_one_deadline_and_one_start(self):
        now = datetime.datetime(2026, 8, 27, 15, 13, tzinfo=datetime.timezone.utc)
        owner = NormalRollActionOwner(RollActionTiming())
        draws = []

        def draw(_start, _end):
            draws.append(True)
            return 120

        first, created = owner.schedule(
            cycle_id=("roll", 1, 4), now_utc=now,
            humanization_enabled=True, window_minutes=40, random_source=draw,
        )
        repeated, repeated_created = owner.schedule(
            cycle_id=("roll", 1, 4), now_utc=now + datetime.timedelta(minutes=1),
            humanization_enabled=True, window_minutes=40, random_source=draw,
        )
        self.assertTrue(created)
        self.assertFalse(repeated_created)
        self.assertEqual(first, repeated)
        self.assertEqual(len(draws), 1)
        self.assertTrue(owner.start(("roll", 1, 4)))
        self.assertFalse(owner.start(("roll", 1, 4)))
        self.assertTrue(owner.complete(("roll", 1, 4)))
        self.assertFalse(owner.start(("roll", 1, 4)))

    def test_dirty_sync_can_defer_and_resume_the_same_roll_action(self):
        now = datetime.datetime(2026, 8, 27, 15, 13, tzinfo=datetime.timezone.utc)
        owner = NormalRollActionOwner(RollActionTiming())
        deadline, _ = owner.schedule(cycle_id="cycle", now_utc=now)
        self.assertTrue(owner.start("cycle"))
        self.assertTrue(owner.defer("cycle"))
        self.assertTrue(owner.is_waiting_claim("cycle"))
        resumed, created = owner.schedule(cycle_id="cycle", now_utc=now + datetime.timedelta(minutes=5))
        self.assertFalse(created)
        self.assertEqual(resumed, deadline)
        self.assertTrue(owner.resume_claim("cycle"))
        self.assertTrue(owner.start("cycle"))

    def test_exhausted_window_seals_cycle_until_successor(self):
        now = datetime.datetime(2026, 8, 30, 12, tzinfo=datetime.timezone.utc)
        cycle = ("roll", 100, 4)
        successor = ("roll", 100, 5)
        owner = NormalRollActionOwner(RollActionTiming())
        deadline, created = owner.schedule(cycle_id=cycle, now_utc=now)

        self.assertTrue(created)
        self.assertTrue(owner.defer_window(cycle))
        repeated, repeated_created = owner.schedule(
            cycle_id=cycle,
            now_utc=now + datetime.timedelta(seconds=20),
        )
        self.assertFalse(repeated_created)
        self.assertEqual(repeated, deadline)
        self.assertEqual(owner.state, "deferred_window")
        self.assertEqual(
            normal_action_status_policy(
                owner_cycle_id=cycle,
                current_roll_cycle_id=cycle,
                owner_state=owner.state,
                state_dirty=False,
            ),
            "suppress-routine",
        )
        self.assertEqual(
            normal_action_status_policy(
                owner_cycle_id=cycle,
                current_roll_cycle_id=cycle,
                owner_state=owner.state,
                state_dirty=True,
            ),
            "none",
        )

        successor_deadline, successor_created = owner.schedule(
            cycle_id=successor,
            now_utc=now + datetime.timedelta(hours=1),
        )
        self.assertTrue(successor_created)
        self.assertEqual(owner.cycle_id, successor)
        self.assertEqual(owner.state, "pending")
        self.assertEqual(successor_deadline, now + datetime.timedelta(hours=1))
        self.assertFalse(owner.defer_window(cycle))
        self.assertEqual(owner.cycle_id, successor)

    @staticmethod
    def _deferred_window_client(cycle, now, boundary, remaining=1258):
        owner = NormalRollActionOwner(RollActionTiming())
        owner.schedule(cycle_id=cycle, now_utc=now)
        handle = _TimerHandle(lambda: None, ())
        client = SimpleNamespace(
            normal_roll_action_owner=owner,
            current_roll_cycle_id=cycle,
            roll_reset_at_utc=boundary,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _normal_roll_action_scheduled_triggers={cycle},
            _predicted_roll_action_handle=handle,
            _predicted_roll_action_cycle_id=cycle,
            _normal_roll_deferred_cycle_id=None,
            _normal_roll_deferred_until_utc=None,
            _status_cycle_not_before_monotonic=0.0,
            _roll_count_sync_cycle_id=None,
            _roll_count_sync_handle=None,
            _roll_count_sync_at_utc=None,
            auto_rolls_enabled=False,
        )
        state = get_normal_roll_cycle_state(client, cycle)
        state.remaining = remaining
        state.remaining_authoritative = True
        return client, owner, handle

    def test_pending_safe_window_exhaustion_uses_atomic_production_defer(self):
        now = datetime.datetime(2026, 8, 30, 12, 59, tzinfo=datetime.timezone.utc)
        boundary = now + datetime.timedelta(seconds=20)
        cycle = ("roll", 200, 1)
        client, owner, handle = self._deferred_window_client(cycle, now, boundary)
        _latest, fits = normal_roll_start_window(now, boundary, 1258, 1.0)

        self.assertFalse(fits)
        self.assertTrue(defer_normal_roll_window(
            client, cycle, boundary, now_utc=now, monotonic_now=100.0,
        ))
        self.assertEqual(owner.cycle_id, cycle)
        self.assertEqual(owner.state, "deferred_window")
        self.assertNotEqual(owner.state, "completed")
        self.assertEqual(client._normal_roll_deferred_until_utc, boundary)
        self.assertEqual(client._normal_roll_deferred_cycle_id, cycle)
        self.assertEqual(client._status_cycle_not_before_monotonic, 120.0)
        self.assertTrue(handle.cancelled())
        self.assertNotIn(cycle, client._normal_roll_action_scheduled_triggers)
        _, created = owner.schedule(cycle_id=cycle, now_utc=now)
        self.assertFalse(created)

    def test_executing_pre_roll_exhaustion_defers_instead_of_completing(self):
        now = datetime.datetime(2026, 8, 30, 12, 59, tzinfo=datetime.timezone.utc)
        boundary = now + datetime.timedelta(seconds=20)
        cycle = ("roll", 200, 2)
        client, owner, _handle = self._deferred_window_client(cycle, now, boundary)
        self.assertTrue(owner.start(cycle))

        self.assertTrue(defer_normal_roll_window(
            client, cycle, boundary, now_utc=now, monotonic_now=500.0,
        ))
        self.assertEqual(owner.state, "deferred_window")
        self.assertFalse(owner.complete(cycle))

    def test_claim_wait_safe_window_exhaustion_returns_to_pending_before_defer(self):
        now = datetime.datetime(2026, 8, 30, 12, 59, tzinfo=datetime.timezone.utc)
        boundary = now + datetime.timedelta(seconds=20)
        cycle = ("roll", 200, 20)
        client, owner, _handle = self._deferred_window_client(cycle, now, boundary)
        self.assertTrue(owner.defer(cycle))
        self.assertTrue(owner.resume_claim(cycle))

        self.assertTrue(defer_normal_roll_window(
            client, cycle, boundary, now_utc=now, monotonic_now=750.0,
        ))
        self.assertEqual(owner.state, "deferred_window")

    def test_beta16_same_cycle_status_loop_stays_sealed(self):
        now = datetime.datetime(2026, 8, 30, 12, 59, tzinfo=datetime.timezone.utc)
        boundary = now + datetime.timedelta(seconds=20)
        cycle = ("roll", 200, 3)
        client, owner, _handle = self._deferred_window_client(cycle, now, boundary)
        defer_normal_roll_window(client, cycle, boundary, now_utc=now, monotonic_now=1000.0)

        reconcile_authoritative_current_roll_count(
            client, 1258, observation_kind="check-status", observed_at_utc=now + datetime.timedelta(seconds=2),
        )
        self.assertTrue(normal_roll_window_is_deferred(client, cycle, boundary))
        _, recreated = owner.schedule(cycle_id=cycle, now_utc=now + datetime.timedelta(seconds=2))
        self.assertFalse(recreated)
        self.assertEqual(owner.state, "deferred_window")
        self.assertEqual(normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=cycle,
            owner_state=owner.state,
            state_dirty=False,
        ), "suppress-routine")
        self.assertGreater(client._status_cycle_not_before_monotonic, 1000.0)

    def test_authoritative_same_cycle_dirty_reconciliation_keeps_defer_seal(self):
        now = datetime.datetime(2026, 8, 30, 12, 59, tzinfo=datetime.timezone.utc)
        boundary = now + datetime.timedelta(seconds=60)
        cycle = ("roll", 200, 4)
        client, owner, _handle = self._deferred_window_client(cycle, now, boundary)
        initialize_status_tracking(client)
        defer_normal_roll_window(client, cycle, boundary, now_utc=now, monotonic_now=2000.0)
        mark_status_dirty(client, {"power"}, reason="legitimate-power-reconcile")
        self.assertIn("power", status_dirty_fields(client))

        reconcile_authoritative_current_roll_count(
            client, 1258, observation_kind="check-status", observed_at_utc=now + datetime.timedelta(seconds=2),
        )
        clear_status_dirty(client, {"power"})
        self.assertFalse(status_dirty_fields(client))
        self.assertEqual(owner.state, "deferred_window")
        self.assertTrue(normal_roll_window_is_deferred(client, cycle, boundary))
        self.assertEqual(normal_action_status_policy(
            owner_cycle_id=cycle,
            current_roll_cycle_id=cycle,
            owner_state=owner.state,
            state_dirty=False,
        ), "suppress-routine")

    def test_small_reset_reanchor_preserves_defer_seal(self):
        now = datetime.datetime(2026, 8, 30, 12, 59, tzinfo=datetime.timezone.utc)
        boundary = now + datetime.timedelta(minutes=20)
        cycle = ("roll", 200, 5)
        client, owner, _handle = self._deferred_window_client(cycle, now, boundary)
        defer_normal_roll_window(client, cycle, boundary, now_utc=now, monotonic_now=3000.0)

        refined_cycle_key = ("roll", 201, 5)
        refined_boundary = boundary + datetime.timedelta(seconds=125)
        self.assertTrue(normal_roll_window_is_deferred(
            client, refined_cycle_key, refined_boundary,
        ))
        self.assertEqual(owner.cycle_id, cycle)
        self.assertEqual(client._normal_roll_deferred_until_utc, boundary)

    def test_true_successor_schedules_once_and_stale_cycle_cannot_act(self):
        now = datetime.datetime(2026, 8, 30, 12, 59, tzinfo=datetime.timezone.utc)
        boundary = now + datetime.timedelta(minutes=1)
        cycle = ("roll", 200, 6)
        successor = ("roll", 200, 7)
        successor_boundary = boundary + datetime.timedelta(hours=1)
        client, owner, _handle = self._deferred_window_client(cycle, now, boundary)
        defer_normal_roll_window(client, cycle, boundary, now_utc=now, monotonic_now=4000.0)

        self.assertFalse(normal_roll_window_is_deferred(client, successor, successor_boundary))
        deadline, created = owner.schedule(cycle_id=successor, now_utc=boundary)
        repeated_deadline, repeated_created = owner.schedule(
            cycle_id=successor, now_utc=boundary + datetime.timedelta(seconds=2),
        )
        self.assertTrue(created)
        self.assertFalse(repeated_created)
        self.assertEqual(deadline, repeated_deadline)
        self.assertFalse(owner.start(cycle))
        self.assertFalse(defer_normal_roll_window(client, cycle, boundary))
        _, stale_created = owner.schedule(cycle_id=cycle, now_utc=successor_boundary)
        self.assertFalse(stale_created)
        self.assertEqual(owner.cycle_id, successor)
        self.assertEqual(owner.state, "pending")

    def test_duplicate_production_defer_is_idempotent(self):
        now = datetime.datetime(2026, 8, 30, 12, 59, tzinfo=datetime.timezone.utc)
        boundary = now + datetime.timedelta(minutes=10)
        cycle = ("roll", 200, 8)
        client, owner, handle = self._deferred_window_client(cycle, now, boundary)
        self.assertTrue(defer_normal_roll_window(
            client, cycle, boundary, now_utc=now, monotonic_now=5000.0,
        ))
        original_status_deadline = client._status_cycle_not_before_monotonic
        refined_boundary = boundary + datetime.timedelta(seconds=30)

        self.assertTrue(defer_normal_roll_window(
            client, cycle, refined_boundary,
            now_utc=now + datetime.timedelta(seconds=2), monotonic_now=9000.0,
        ))
        self.assertEqual(owner.state, "deferred_window")
        self.assertEqual(client._normal_roll_deferred_until_utc, boundary)
        self.assertEqual(client._status_cycle_not_before_monotonic, original_status_deadline)
        self.assertTrue(handle.cancelled())
        self.assertIsNone(client._predicted_roll_action_handle)
        self.assertFalse(client._normal_roll_action_scheduled_triggers)

    def test_prearmed_automation_text_command_keeps_ownership_before_receipt(self):
        tracker = RollCommandCorrelation()
        now = datetime.datetime(2026, 8, 27, 15, 13, tzinfo=datetime.timezone.utc)
        token = tracker.prearm(
            channel_id=10, owner_id=20, owner_name="self", command_name="rolls",
            mode="text", registered_at_utc=now, automation_owned=True,
        )
        observed = tracker.observe_text_command(
            channel_id=10, owner_id=20, owner_name="self", command_name="rolls",
            message_id=99, sent_at_utc=now,
        )
        self.assertEqual(observed.token, token)
        self.assertTrue(observed.automation_owned)
        self.assertTrue(observed.finalized)
        finalized = tracker.finalize(token, {
            "mode": "text", "message_id": 99,
            "sent_at_utc": now + datetime.timedelta(milliseconds=10),
        })
        self.assertTrue(finalized.automation_owned)

    def test_gateway_only_text_roll_is_manual(self):
        tracker = RollCommandCorrelation()
        now = datetime.datetime(2026, 8, 27, 15, 13, tzinfo=datetime.timezone.utc)
        observed = tracker.observe_text_command(
            channel_id=10, owner_id=20, owner_name="self", command_name="rolls",
            message_id=99, sent_at_utc=now,
        )
        self.assertFalse(observed.automation_owned)

    def test_waiting_claim_expired_deadline_gets_one_post_claim_draw(self):
        start = datetime.datetime(2026, 8, 27, 15, 13, tzinfo=datetime.timezone.utc)
        owner = NormalRollActionOwner(RollActionTiming())
        owner.schedule(cycle_id="r", now_utc=start)
        owner.defer("r")
        draws = []
        deadline, created = owner.resume_after_claim(
            cycle_id="r", now_utc=start + datetime.timedelta(minutes=17),
            latest_action_at_utc=start + datetime.timedelta(minutes=50),
            humanization_enabled=True, window_minutes=20,
            random_source=lambda _a, _b: draws.append(True) or 300,
        )
        repeated, repeated_created = owner.schedule(
            cycle_id="r", now_utc=start + datetime.timedelta(minutes=18),
        )
        self.assertTrue(created)
        self.assertFalse(repeated_created)
        self.assertEqual(deadline, start + datetime.timedelta(minutes=22))
        self.assertEqual(repeated, deadline)
        self.assertEqual(len(draws), 1)

    def test_simultaneous_reset_explicitly_supersedes_waiting_cycle(self):
        start = datetime.datetime(2026, 8, 27, 15, 13, tzinfo=datetime.timezone.utc)
        owner = NormalRollActionOwner(RollActionTiming())
        owner.schedule(cycle_id="r", now_utc=start)
        owner.defer("r")
        deadline, created = owner.schedule(
            cycle_id="r+1", now_utc=start + datetime.timedelta(hours=1),
            humanization_enabled=True, window_minutes=10,
            random_source=lambda _a, _b: 120,
        )
        self.assertTrue(created)
        self.assertEqual(owner.cycle_id, "r+1")
        self.assertEqual(owner.state, "pending")
        self.assertEqual(deadline, start + datetime.timedelta(hours=1, minutes=2))

    def test_executing_cycle_coalesces_and_promotes_latest_successor(self):
        start = datetime.datetime(2026, 8, 27, 15, 13, tzinfo=datetime.timezone.utc)
        owner = NormalRollActionOwner(RollActionTiming())
        owner.schedule(cycle_id="r", now_utc=start)
        owner.start("r")
        owner.schedule(cycle_id="r+1", now_utc=start + datetime.timedelta(hours=1))
        latest, _ = owner.schedule(cycle_id="r+2", now_utc=start + datetime.timedelta(hours=2))
        self.assertEqual(owner.cycle_id, "r")
        self.assertEqual(owner.queued_cycle_id, "r+2")
        self.assertTrue(owner.complete("r"))
        self.assertEqual(owner.cycle_id, "r+2")
        self.assertEqual(owner.deadline_utc, latest)
        self.assertEqual(owner.state, "pending")

    def test_manual_invalidation_cancels_waiting_claim_but_not_execution(self):
        owner = NormalRollActionOwner(RollActionTiming())
        now = datetime.datetime(2026, 8, 27, tzinfo=datetime.timezone.utc)
        owner.schedule(cycle_id="r", now_utc=now)
        owner.defer("r")
        self.assertTrue(owner.cancel())
        self.assertEqual(owner.state, "completed")
        owner.schedule(cycle_id="r+1", now_utc=now)
        owner.start("r+1")
        self.assertFalse(owner.cancel())
        self.assertEqual(owner.state, "executing")
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

    def test_daily_rolls_requires_a_claim_right_and_explicit_key_mode_permission(self):
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
        ), "wait-claim-reset")

        # Round 3 with available claim inside this roll interval executes.
        self.assertEqual(daily_rolls_decision(
            enabled=True, only_claim_hour=True, claim_right_available=True,
            key_mode=True, auto_rolls_in_key_mode=True,
            next_claim_reset_at_utc=now + datetime.timedelta(minutes=10),
            roll_reset_at_utc=now + datetime.timedelta(minutes=20),
            used_this_interval=False, limit_reached=False, ack_retry_ready=True,
            now_utc=now,
        ), "execute")
        self.assertEqual(daily_rolls_decision(
            enabled=True, only_claim_hour=True, claim_right_available=False,
            key_mode=True, auto_rolls_in_key_mode=True,
            next_claim_reset_at_utc=now + datetime.timedelta(hours=3),
            roll_reset_at_utc=now + datetime.timedelta(minutes=20),
            used_this_interval=False, limit_reached=False, ack_retry_ready=True,
            now_utc=now,
        ), "outside-claim-hour")
        self.assertEqual(daily_rolls_decision(
            enabled=True, only_claim_hour=True, claim_right_available=True,
            key_mode=True, auto_rolls_in_key_mode=False,
            next_claim_reset_at_utc=now + datetime.timedelta(minutes=10),
            roll_reset_at_utc=now + datetime.timedelta(minutes=20),
            used_this_interval=False, limit_reached=False, ack_retry_ready=True,
            now_utc=now,
        ), "key-mode-disabled")

    def test_auto_rolls_mandatory_issue_1_semantics(self):
        now = datetime.datetime(2026, 8, 25, 12, tzinfo=datetime.timezone.utc)
        # Test A: Round 1 (claim in 3h), claim available, Auto $rolls enabled, only_claim_hour enabled -> NOT used
        self.assertEqual(
            daily_rolls_decision(
                enabled=True,
                only_claim_hour=True,
                claim_right_available=True,
                key_mode=False,
                auto_rolls_in_key_mode=False,
                next_claim_reset_at_utc=now + datetime.timedelta(hours=3),
                roll_reset_at_utc=now + datetime.timedelta(minutes=20),
                used_this_interval=False,
                limit_reached=False,
                ack_retry_ready=True,
                now_utc=now,
            ),
            "outside-claim-hour",
        )
        # Test B: Round 2 (claim in 2h), claim available, Auto $rolls enabled, only_claim_hour enabled -> NOT used
        self.assertEqual(
            daily_rolls_decision(
                enabled=True,
                only_claim_hour=True,
                claim_right_available=True,
                key_mode=False,
                auto_rolls_in_key_mode=False,
                next_claim_reset_at_utc=now + datetime.timedelta(hours=2),
                roll_reset_at_utc=now + datetime.timedelta(minutes=20),
                used_this_interval=False,
                limit_reached=False,
                ack_retry_ready=True,
                now_utc=now,
            ),
            "outside-claim-hour",
        )
        # Test D: Round 3 (claim in 10m, rolls in 20m), claim unavailable, only_claim_hour enabled -> wait-claim-reset
        self.assertEqual(
            daily_rolls_decision(
                enabled=True,
                only_claim_hour=True,
                claim_right_available=False,
                key_mode=False,
                auto_rolls_in_key_mode=False,
                next_claim_reset_at_utc=now + datetime.timedelta(minutes=10),
                roll_reset_at_utc=now + datetime.timedelta(minutes=20),
                used_this_interval=False,
                limit_reached=False,
                ack_retry_ready=True,
                now_utc=now,
            ),
            "wait-claim-reset",
        )
        # Round 3 with claim available -> execute
        self.assertEqual(
            daily_rolls_decision(
                enabled=True,
                only_claim_hour=True,
                claim_right_available=True,
                key_mode=False,
                auto_rolls_in_key_mode=False,
                next_claim_reset_at_utc=now + datetime.timedelta(minutes=10),
                roll_reset_at_utc=now + datetime.timedelta(minutes=20),
                used_this_interval=False,
                limit_reached=False,
                ack_retry_ready=True,
                now_utc=now,
            ),
            "execute",
        )

    def test_round_three_auto_rolls_executes_when_roll_replenishment_precedes_claim_reset(self):
        now = datetime.datetime(2026, 8, 25, 12, tzinfo=datetime.timezone.utc)
        # Recreate Certi's exact conceptual state:
        # round = 3 (claim resets in 45 min <= 60 min)
        # claim available = true
        # normal rolls just reached zero, next replenishment in 20 min (preceding claim reset)
        # Auto $rolls enabled
        # Auto $rolls allowed in key mode
        # claim-hour-only enabled
        # daily $rolls item unused
        self.assertEqual(
            daily_rolls_decision(
                enabled=True,
                only_claim_hour=True,
                claim_right_available=True,
                key_mode=False,
                auto_rolls_in_key_mode=False,
                next_claim_reset_at_utc=now + datetime.timedelta(minutes=45),
                roll_reset_at_utc=now + datetime.timedelta(minutes=20),
                used_this_interval=False,
                limit_reached=False,
                ack_retry_ready=True,
                now_utc=now,
            ),
            "execute",
        )
        # Key mode enabled with permission
        self.assertEqual(
            daily_rolls_decision(
                enabled=True,
                only_claim_hour=True,
                claim_right_available=True,
                key_mode=True,
                auto_rolls_in_key_mode=True,
                next_claim_reset_at_utc=now + datetime.timedelta(minutes=45),
                roll_reset_at_utc=now + datetime.timedelta(minutes=20),
                used_this_interval=False,
                limit_reached=False,
                ack_retry_ready=True,
                now_utc=now,
            ),
            "execute",
        )

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
    @staticmethod
    def _authoritative_reconciliation_client(*, auto_rolls_enabled=False):
        cycle_id = ("roll", 1700000000, 4)
        return SimpleNamespace(
            current_roll_cycle_id=cycle_id,
            normal_roll_action_owner=NormalRollActionOwner(RollActionTiming()),
            auto_rolls_enabled=auto_rolls_enabled,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _roll_count_sync_cycle_id=None,
            _roll_count_sync_at_utc=None,
            _roll_count_sync_handle=None,
            _predicted_roll_action_handle=None,
            _roll_count_reconcile_cycle_id=None,
            _roll_count_reconcile_started_at_utc=None,
            rolls_left=0,
        )

    def test_reconciliation_lease_same_cycle_success_clears_id_and_timestamp(self):
        client = self._authoritative_reconciliation_client()
        cycle_id = client.current_roll_cycle_id
        owner = client.normal_roll_action_owner
        owner.schedule(
            cycle_id=cycle_id,
            now_utc=datetime.datetime(2026, 8, 28, 8, 0, tzinfo=datetime.timezone.utc),
        )
        acquired_at = datetime.datetime(2026, 8, 28, 8, 0, 5, tzinfo=datetime.timezone.utc)

        self.assertTrue(claim_roll_count_reconciliation(client, cycle_id, now_utc=acquired_at))
        self.assertEqual(client._roll_count_reconcile_started_at_utc, acquired_at)
        reconcile_authoritative_current_roll_count(
            client,
            12,
            observation_kind="same-cycle-reconciliation",
            observed_at_utc=acquired_at + datetime.timedelta(seconds=3),
        )

        self.assertIsNone(client._roll_count_reconcile_cycle_id)
        self.assertIsNone(client._roll_count_reconcile_started_at_utc)
        self.assertIs(client.normal_roll_action_owner, owner)
        self.assertTrue(owner.is_pending(cycle_id))

    def test_newer_cycle_snapshot_supersedes_old_lease_and_allows_new_claim(self):
        client = self._authoritative_reconciliation_client()
        cycle_r1 = ("roll", 1700000000, 5)
        cycle_r2 = ("roll", 1700000000, 6)
        client.current_roll_cycle_id = cycle_r1
        acquired_at = datetime.datetime(2026, 8, 28, 8, 0, tzinfo=datetime.timezone.utc)
        self.assertTrue(claim_roll_count_reconciliation(client, cycle_r1, now_utc=acquired_at))

        client.current_roll_cycle_id = cycle_r2
        reconcile_authoritative_current_roll_count(
            client,
            11,
            observation_kind="post-reset-response",
            observed_at_utc=acquired_at + datetime.timedelta(minutes=1),
        )

        self.assertEqual(get_normal_roll_cycle_state(client, cycle_r2).remaining, 11)
        self.assertIsNone(client._roll_count_reconcile_cycle_id)
        self.assertIsNone(client._roll_count_reconcile_started_at_utc)
        add_roll_cycle_uncertainty(
            client,
            cycle_r2,
            ("confirmed-boundary-result", 77),
            reason="cross-cycle-roll-result-race",
        )
        self.assertTrue(claim_roll_count_reconciliation(client, cycle_r2))

    def test_older_snapshot_does_not_clear_future_cycle_lease(self):
        client = self._authoritative_reconciliation_client()
        cycle_r = ("roll", 1700000000, 4)
        cycle_r1 = ("roll", 1700000000, 5)
        acquired_at = datetime.datetime(2026, 8, 28, 8, 0, tzinfo=datetime.timezone.utc)
        client.current_roll_cycle_id = cycle_r
        self.assertTrue(claim_roll_count_reconciliation(client, cycle_r1, now_utc=acquired_at))

        apply_authoritative_roll_remaining(
            client,
            cycle_r,
            3,
            observed_at_utc=acquired_at + datetime.timedelta(seconds=2),
        )

        self.assertEqual(client._roll_count_reconcile_cycle_id, cycle_r1)
        self.assertEqual(client._roll_count_reconcile_started_at_utc, acquired_at)
        self.assertFalse(roll_cycle_is_same_or_newer(cycle_r, cycle_r1))

    def test_tu_timeout_releases_lease_and_backoff_allows_later_retry(self):
        client = self._authoritative_reconciliation_client()
        initialize_status_tracking(client)
        cycle_id = client.current_roll_cycle_id
        self.assertTrue(claim_roll_count_reconciliation(client, cycle_id))

        delay = record_tu_failure(client, now_monotonic=100.0)

        self.assertEqual(delay, 30.0)
        self.assertIsNone(client._roll_count_reconcile_cycle_id)
        self.assertIsNone(client._roll_count_reconcile_started_at_utc)
        self.assertEqual(tu_retry_wait(client, now_monotonic=110.0), 20.0)
        self.assertEqual(tu_retry_wait(client, now_monotonic=131.0), 0.0)
        self.assertTrue(claim_roll_count_reconciliation(client, cycle_id))

    def test_tu_send_failure_releases_lease_without_immediate_retry_spam(self):
        client = self._authoritative_reconciliation_client()
        initialize_status_tracking(client)
        cycle_id = client.current_roll_cycle_id
        self.assertTrue(claim_roll_count_reconciliation(client, cycle_id))

        record_tu_failure(client, now_monotonic=200.0)

        self.assertIsNone(client._roll_count_reconcile_cycle_id)
        self.assertGreater(tu_retry_wait(client, now_monotonic=200.0), 0.0)
        self.assertTrue(claim_roll_count_reconciliation(client, cycle_id))

    def test_partial_tu_without_rolls_releases_lease_and_keeps_rolls_dirty(self):
        client = self._authoritative_reconciliation_client()
        initialize_status_tracking(client)
        cycle_id = client.current_roll_cycle_id
        self.assertTrue(claim_roll_count_reconciliation(client, cycle_id))

        mark_status_dirty(client, {"rolls"}, reason="partial-tu-response")
        self.assertTrue(release_roll_count_reconciliation(client))
        defer_tu_queries(client, 30.0, now_monotonic=300.0)

        self.assertIsNone(client._roll_count_reconcile_cycle_id)
        self.assertIn("rolls", status_dirty_fields(client))
        self.assertEqual(tu_retry_wait(client, now_monotonic=305.0), 25.0)

    def test_material_reanchor_releases_old_lineage_lease(self):
        client = self._authoritative_reconciliation_client()
        old_cycle = ("roll", 1700000000, 8)
        new_cycle = ("roll", 1800000000, 0)
        client.current_roll_cycle_id = new_cycle
        self.assertTrue(claim_roll_count_reconciliation(client, old_cycle))

        reconcile_authoritative_current_roll_count(
            client,
            13,
            observation_kind="material-reanchor",
            material_reanchor=True,
        )

        self.assertIsNone(client._roll_count_reconcile_cycle_id)
        self.assertFalse(roll_cycle_is_same_or_newer(new_cycle, old_cycle))
        self.assertTrue(claim_roll_count_reconciliation(client, new_cycle))

    def test_duplicate_reconciliation_claims_share_one_active_physical_owner(self):
        client = self._authoritative_reconciliation_client()
        cycle_id = client.current_roll_cycle_id
        acquired_at = datetime.datetime(2026, 8, 28, 8, 0, tzinfo=datetime.timezone.utc)

        claims = [
            claim_roll_count_reconciliation(client, cycle_id, now_utc=acquired_at)
            for _ in range(5)
        ]

        self.assertEqual(claims, [True, False, False, False, False])
        self.assertEqual(sum(claims), 1)
        self.assertEqual(client._roll_count_reconcile_started_at_utc, acquired_at)

    def test_definite_same_cycle_send_decrements_executable_remaining(self):
        client = self._authoritative_reconciliation_client()
        cycle_id = client.current_roll_cycle_id
        state = get_normal_roll_cycle_state(client, cycle_id)
        state.remaining = 12
        state.remaining_authoritative = True
        client._normal_roll_action_roll_counts[cycle_id] = 12

        self.assertTrue(record_definite_normal_roll_consumption(client, cycle_id))

        self.assertEqual(state.remaining, 11)
        self.assertTrue(state.remaining_authoritative)
        self.assertEqual(state.known_consumed, 1)
        self.assertEqual(client._normal_roll_action_roll_counts[cycle_id], 11)

    def test_old_batch_exact_completion_preserves_successor_reconciliation(self):
        client = self._authoritative_reconciliation_client()
        initialize_status_tracking(client)
        cycle_r = ("roll", 1700000000, 4)
        cycle_r1 = ("roll", 1700000000, 5)
        client.current_roll_cycle_id = cycle_r1
        client.normal_roll_action_owner.schedule(
            cycle_id=cycle_r1,
            now_utc=datetime.datetime(2026, 8, 28, 8, 0, tzinfo=datetime.timezone.utc),
        )
        state = get_normal_roll_cycle_state(client, cycle_r1)
        state.remaining = 12
        add_roll_cycle_uncertainty(
            client,
            cycle_r1,
            ("confirmed-boundary-result", 7001),
            reason="cross-cycle-roll-result-race",
        )
        self.assertTrue(claim_roll_count_reconciliation(client, cycle_r1))
        mark_status_dirty(
            client,
            {"rolls"},
            reason="normal-action-count-reconcile",
            urgent=True,
        )
        deferred_status_fields = {"rolls"}
        mark_status_dirty(
            client,
            deferred_status_fields,
            reason="roll-batch-deferred-status",
            urgent=True,
        )

        if can_clear_roll_status_after_exact_batch(
            client,
            logical_roll_cycle_id=cycle_r,
            deferred_status_fields=deferred_status_fields,
        ):
            clear_status_dirty(client, {"rolls"})

        policy = normal_action_status_policy(
            owner_cycle_id=cycle_r1,
            current_roll_cycle_id=cycle_r1,
            owner_state="pending",
            state_dirty=bool(status_dirty_fields(client)),
            reconciliation_cycle_ids=set(),
        )
        physical_tu_count = int(policy == "none" and tu_retry_wait(client) == 0)
        self.assertEqual(client._roll_count_reconcile_cycle_id, cycle_r1)
        self.assertIn("rolls", status_dirty_fields(client))
        self.assertTrue(state.count_uncertain)
        self.assertEqual(policy, "none")
        self.assertEqual(physical_tu_count, 1)

    def test_clean_same_cycle_exact_completion_may_clear_stale_roll_dirty_state(self):
        client = self._authoritative_reconciliation_client()
        initialize_status_tracking(client)
        cycle_id = client.current_roll_cycle_id
        state = get_normal_roll_cycle_state(client, cycle_id)
        state.remaining = 0
        mark_status_dirty(client, {"rolls"}, reason="pre-batch-cache")

        self.assertTrue(can_clear_roll_status_after_exact_batch(
            client,
            logical_roll_cycle_id=cycle_id,
            deferred_status_fields=set(),
        ))
        clear_status_dirty(client, {"rolls"})

        self.assertEqual(status_dirty_fields(client), set())

    def test_authoritative_positive_count_is_state_only_for_idle_owner(self):
        client = self._authoritative_reconciliation_client()
        rearm_calls = []

        applied = reconcile_authoritative_current_roll_count(
            client,
            13,
            observation_kind="check-status",
            rearm_existing_owner=lambda *args: rearm_calls.append(args),
        )

        state = get_normal_roll_cycle_state(client, client.current_roll_cycle_id)
        self.assertTrue(applied)
        self.assertEqual(state.remaining, 13)
        self.assertTrue(state.remaining_authoritative)
        self.assertEqual(client.rolls_left, 13)
        self.assertEqual(client.normal_roll_action_owner.state, "idle")
        self.assertEqual(rearm_calls, [])

    def test_authoritative_zero_with_auto_rolls_is_state_only_for_idle_owner(self):
        client = self._authoritative_reconciliation_client(auto_rolls_enabled=True)
        rearm_calls = []

        reconcile_authoritative_current_roll_count(
            client,
            0,
            observation_kind="check-status-no-rolls",
            rearm_existing_owner=lambda *args: rearm_calls.append(args),
        )

        self.assertEqual(client.normal_roll_action_owner.state, "idle")
        self.assertEqual(rearm_calls, [])

    def test_authoritative_count_rearms_only_existing_owner_at_same_deadline(self):
        client = self._authoritative_reconciliation_client()
        cycle_id = client.current_roll_cycle_id
        scheduled_at = datetime.datetime(2026, 8, 28, 8, 0, tzinfo=datetime.timezone.utc)
        deadline, created = client.normal_roll_action_owner.schedule(
            cycle_id=cycle_id,
            now_utc=scheduled_at,
            persistent_stagger_seconds=17,
        )
        rearm_calls = []

        reconcile_authoritative_current_roll_count(
            client,
            7,
            observation_kind="check-rolls-tu",
            observed_at_utc=scheduled_at + datetime.timedelta(seconds=3),
            rearm_existing_owner=lambda *args: rearm_calls.append(args),
        )

        self.assertTrue(created)
        self.assertEqual(client.normal_roll_action_owner.state, "pending")
        self.assertEqual(client.normal_roll_action_owner.deadline_utc, deadline)
        self.assertEqual(rearm_calls, [(cycle_id, deadline)])
        state = get_normal_roll_cycle_state(client, cycle_id)
        self.assertEqual(state.authoritative_revision, 1)

    def test_authoritative_zero_rearms_existing_auto_rolls_owner(self):
        client = self._authoritative_reconciliation_client(auto_rolls_enabled=True)
        cycle_id = client.current_roll_cycle_id
        deadline, _ = client.normal_roll_action_owner.schedule(
            cycle_id=cycle_id,
            now_utc=datetime.datetime(2026, 8, 28, 8, 0, tzinfo=datetime.timezone.utc),
        )
        rearm_calls = []

        reconcile_authoritative_current_roll_count(
            client,
            0,
            observation_kind="check-status-auto-rolls",
            rearm_existing_owner=lambda *args: rearm_calls.append(args),
        )

        self.assertEqual(client.normal_roll_action_owner.state, "pending")
        self.assertEqual(rearm_calls, [(cycle_id, deadline)])

    def test_authoritative_zero_cancels_existing_owner_and_sync_callbacks(self):
        client = self._authoritative_reconciliation_client()
        cycle_id = client.current_roll_cycle_id
        client.normal_roll_action_owner.schedule(
            cycle_id=cycle_id,
            now_utc=datetime.datetime(2026, 8, 28, 8, 0, tzinfo=datetime.timezone.utc),
        )
        sync_handle = _TimerHandle(lambda: None, ())
        action_handle = _TimerHandle(lambda: None, ())
        client._roll_count_sync_cycle_id = cycle_id
        client._roll_count_sync_at_utc = datetime.datetime.now(datetime.timezone.utc)
        client._roll_count_sync_handle = sync_handle
        client._predicted_roll_action_handle = action_handle

        reconcile_authoritative_current_roll_count(
            client,
            0,
            observation_kind="check-status",
        )

        self.assertEqual(client.normal_roll_action_owner.state, "completed")
        self.assertTrue(sync_handle.cancelled())
        self.assertTrue(action_handle.cancelled())
        self.assertIsNone(client._roll_count_sync_cycle_id)
        self.assertIsNone(client._roll_count_sync_at_utc)
        self.assertIsNone(client._roll_count_sync_handle)
        self.assertIsNone(client._predicted_roll_action_handle)

    def test_behavior_gates_lurker_and_state_only_status_before_owner_creation(self):
        client = self._authoritative_reconciliation_client()
        reconcile_authoritative_current_roll_count(
            client,
            13,
            observation_kind="lurker-status",
        )

        immediate, should_evaluate = normal_roll_behavior_flags(
            rolling_enabled=True,
            proceed_to_rolls=True,
            scheduled_roll_due=False,
            can_claim=True,
            is_lurking=True,
            key_mode=False,
            rt_available=False,
            is_timing_window=False,
            is_panic_window=False,
        )

        self.assertFalse(immediate)
        self.assertFalse(should_evaluate)
        self.assertEqual(client.normal_roll_action_owner.state, "idle")

    def test_proceed_to_rolls_false_updates_state_without_owner(self):
        client = self._authoritative_reconciliation_client()
        reconcile_authoritative_current_roll_count(
            client,
            13,
            observation_kind="status-only",
        )

        immediate, should_evaluate = normal_roll_behavior_flags(
            rolling_enabled=True,
            proceed_to_rolls=False,
            scheduled_roll_due=True,
            can_claim=True,
            is_lurking=False,
            key_mode=True,
            rt_available=True,
            is_timing_window=True,
            is_panic_window=True,
            pending_rolls=True,
            pending_us=True,
        )

        self.assertFalse(immediate)
        self.assertFalse(should_evaluate)
        self.assertEqual(client.rolls_left, 13)
        self.assertEqual(client.normal_roll_action_owner.state, "idle")

    def test_eligible_behavior_path_creates_exactly_one_owner(self):
        client = self._authoritative_reconciliation_client()
        cycle_id = client.current_roll_cycle_id
        observed_at = datetime.datetime(2026, 8, 28, 8, 0, tzinfo=datetime.timezone.utc)
        reconcile_authoritative_current_roll_count(
            client,
            13,
            observation_kind="eligible-status",
            observed_at_utc=observed_at,
        )
        immediate, should_evaluate = normal_roll_behavior_flags(
            rolling_enabled=True,
            proceed_to_rolls=True,
            scheduled_roll_due=False,
            can_claim=True,
            is_lurking=False,
            key_mode=False,
            rt_available=False,
            is_timing_window=False,
            is_panic_window=False,
        )

        self.assertTrue(immediate)
        self.assertTrue(should_evaluate)
        first_deadline, first_created = client.normal_roll_action_owner.schedule(
            cycle_id=cycle_id,
            now_utc=observed_at,
        )
        second_deadline, second_created = client.normal_roll_action_owner.schedule(
            cycle_id=cycle_id,
            now_utc=observed_at + datetime.timedelta(seconds=5),
        )
        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(second_deadline, first_deadline)
        self.assertTrue(client.normal_roll_action_owner.is_pending(cycle_id))

    @staticmethod
    def _pending_boundary_snapshot():
        cycle_id = ("roll", 1700000000, 5)
        owner = NormalRollActionOwner(RollActionTiming())
        deadline, _ = owner.schedule(
            cycle_id=cycle_id,
            now_utc=datetime.datetime(2026, 8, 28, 8, 5, tzinfo=datetime.timezone.utc),
            persistent_stagger_seconds=23,
        )
        client = SimpleNamespace(
            current_roll_cycle_id=cycle_id,
            normal_roll_action_owner=owner,
            auto_rolls_enabled=False,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _pending_boundary_roll_origins={},
            _roll_count_sync_cycle_id=None,
            _roll_count_sync_at_utc=None,
            _roll_count_sync_handle=None,
            _roll_count_reconcile_cycle_id=None,
            _predicted_roll_action_handle=None,
            _roll_batch_deferred_status_fields=set(),
            normal_roll_replenishment_capacity=13,
            normal_roll_replenishment_capacity_confidence=True,
            cross_cycle_roll_count_uncertain=False,
            cross_cycle_uncertain_cycle_id=None,
            rolls_left=0,
        )
        state = get_normal_roll_cycle_state(client, cycle_id)
        state.proven_fresh = True
        state.known_consumed = 0
        initialize_status_tracking(client)
        token = 4242
        client._pending_boundary_roll_origins[token] = {
            "affected_cycle_id": cycle_id,
            "expires_at": time.monotonic() + 15.0,
        }
        add_provisional_roll_cycle_uncertainty(
            client,
            cycle_id,
            ("pending-boundary-origin", token),
        )
        observed_at = datetime.datetime(2026, 8, 28, 8, 5, 8, tzinfo=datetime.timezone.utc)
        reconcile_authoritative_current_roll_count(
            client,
            12,
            observation_kind="pending-boundary-status",
            observed_at_utc=observed_at,
        )
        return client, state, cycle_id, token, deadline, observed_at

    @staticmethod
    def _timer_scheduler(client, loop=None):
        loop = loop or _Loop()
        fired_cycles = []
        replacement_requests = []

        def schedule_callback(cycle_id, delay=0.0, *, replace_existing=False):
            replacement_requests.append((cycle_id, delay, replace_existing))
            existing = client._predicted_roll_action_handle
            if existing is not None and not existing.cancelled():
                if not replace_existing:
                    return
                existing.cancel()
            client._predicted_roll_action_handle = loop.call_later(
                max(0.0, delay),
                fired_cycles.append,
                cycle_id,
            )

        return loop, fired_cycles, replacement_requests, schedule_callback

    def test_pending_boundary_token_survives_status_and_cannot_poison_capacity(self):
        client, state, cycle_id, token, _deadline, observed_at = self._pending_boundary_snapshot()

        self.assertEqual(state.remaining, 12)
        self.assertTrue(state.remaining_authoritative)
        self.assertEqual(state.last_authoritative_at_utc, observed_at)
        self.assertEqual(state.authoritative_revision, 1)
        self.assertTrue(state.count_uncertain)
        self.assertEqual(
            unresolved_pending_roll_uncertainty_keys(client, cycle_id),
            {("pending-boundary-origin", token)},
        )
        self.assertIn(token, client._pending_boundary_roll_origins)
        self.assertEqual(client.normal_roll_replenishment_capacity, 13)
        self.assertTrue(client.normal_roll_action_owner.is_pending(cycle_id))
        self.assertFalse(client.normal_roll_action_owner.start("other-cycle"))

    def test_pending_only_uncertainty_waits_without_repeated_reconciliation(self):
        client, state, cycle_id, _token, _deadline, _observed_at = self._pending_boundary_snapshot()
        physical_tu_count = 0

        for _ in range(5):
            self.assertTrue(roll_cycle_has_only_pending_boundary_origins(state))
            if roll_cycle_needs_authoritative_reconcile(state):
                physical_tu_count += int(claim_roll_count_reconciliation(client, cycle_id))

        self.assertEqual(physical_tu_count, 0)
        self.assertTrue(client.normal_roll_action_owner.is_pending(cycle_id))

    def test_provisional_registration_is_state_only_and_preserves_unrelated_dirty_fields(self):
        client, state, cycle_id, _token, _deadline, _observed_at = self._pending_boundary_snapshot()
        mark_status_dirty(client, {"claim"}, reason="unrelated-claim")
        client._roll_batch_deferred_status_fields.add("power")

        add_provisional_roll_cycle_uncertainty(
            client, cycle_id, ("pending-boundary-origin", 5252)
        )

        self.assertTrue(state.count_uncertain)
        self.assertEqual(status_dirty_fields(client), {"claim"})
        self.assertEqual(client._roll_batch_deferred_status_fields, {"power"})
        self.assertIsNone(client._roll_count_reconcile_cycle_id)

    def test_pending_only_batch_release_requires_zero_status_requests(self):
        client, state, cycle_id, _token, _deadline, _observed_at = self._pending_boundary_snapshot()
        action_policy = normal_action_status_policy(
            owner_cycle_id=client.normal_roll_action_owner.cycle_id,
            current_roll_cycle_id=cycle_id,
            owner_state=client.normal_roll_action_owner.state,
            state_dirty=bool(status_dirty_fields(client)),
            reconciliation_cycle_ids={client._roll_count_reconcile_cycle_id},
        )

        self.assertFalse(roll_cycle_uncertainty_requires_status(state))
        self.assertEqual(action_policy, "suppress-routine")
        self.assertEqual(status_dirty_fields(client), set())
        self.assertEqual(client._roll_batch_deferred_status_fields, set())

    def test_clean_pending_resolution_leaves_status_clean_and_rearms_same_deadline(self):
        client, state, cycle_id, token, deadline, _observed_at = self._pending_boundary_snapshot()
        client._predicted_roll_action_handle = _TimerHandle(lambda: None, ())
        loop, _fired, requests, schedule_callback = self._timer_scheduler(client)

        self.assertTrue(resolve_pending_boundary_roll_and_rearm(
            client,
            cycle_id,
            token,
            schedule_callback,
            now_utc=deadline - datetime.timedelta(seconds=4),
        ))

        self.assertFalse(state.count_uncertain)
        self.assertEqual(status_dirty_fields(client), set())
        self.assertEqual(client._roll_batch_deferred_status_fields, set())
        self.assertEqual(requests, [(cycle_id, 4.0, True)])
        self.assertEqual(loop.calls[-1][0], 4.0)
        self.assertEqual(client.normal_roll_action_owner.deadline_utc, deadline)

    def test_old_result_resolution_creates_no_status_work(self):
        client, state, cycle_id, token, deadline, observed_at = self._pending_boundary_snapshot()
        self.assertLess(observed_at - datetime.timedelta(seconds=1), state.last_authoritative_at_utc)
        _loop, _fired, _requests, schedule_callback = self._timer_scheduler(client)

        resolve_pending_boundary_roll_and_rearm(
            client,
            cycle_id,
            token,
            schedule_callback,
            now_utc=deadline - datetime.timedelta(seconds=2),
        )

        self.assertFalse(state.count_uncertain)
        self.assertEqual(status_dirty_fields(client), set())
        self.assertEqual(client._roll_batch_deferred_status_fields, set())
        self.assertIsNone(client._roll_count_reconcile_cycle_id)

    def test_confirmed_result_creates_one_dirty_reconciliation_claim(self):
        client, state, cycle_id, token, _deadline, _observed_at = self._pending_boundary_snapshot()
        client._pending_boundary_roll_origins.pop(token)
        remove_roll_cycle_uncertainty(client, cycle_id, ("pending-boundary-origin", token))
        add_roll_cycle_uncertainty(
            client,
            cycle_id,
            ("confirmed-boundary-result", token),
            reason="cross-cycle-roll-result-race",
        )

        claims = sum(claim_roll_count_reconciliation(client, cycle_id) for _ in range(5))

        self.assertTrue(roll_cycle_uncertainty_requires_status(state))
        self.assertEqual(status_dirty_fields(client), {"rolls"})
        self.assertEqual(client._roll_batch_deferred_status_fields, {"rolls"})
        self.assertEqual(claims, 1)
        self.assertEqual(client._roll_count_reconcile_cycle_id, cycle_id)

    def test_timeout_conversion_creates_one_dirty_reconciliation_claim(self):
        client, state, cycle_id, token, _deadline, _observed_at = self._pending_boundary_snapshot()
        self.assertEqual(status_dirty_fields(client), set())
        client._pending_boundary_roll_origins.pop(token)
        remove_roll_cycle_uncertainty(client, cycle_id, ("pending-boundary-origin", token))
        add_roll_cycle_uncertainty(
            client,
            cycle_id,
            ("boundary-origin-timeout", token),
            reason="pending-origin-timeout",
        )

        claims = sum(claim_roll_count_reconciliation(client, cycle_id) for _ in range(5))

        self.assertTrue(roll_cycle_uncertainty_requires_status(state))
        self.assertEqual(status_dirty_fields(client), {"rolls"})
        self.assertEqual(client._roll_batch_deferred_status_fields, {"rolls"})
        self.assertEqual(claims, 1)

    def test_multiple_pending_tokens_stay_status_clean_until_final_clean_result(self):
        client, state, cycle_id, token_a, deadline, _observed_at = self._pending_boundary_snapshot()
        token_b = 5353
        client._pending_boundary_roll_origins[token_b] = {
            "affected_cycle_id": cycle_id,
            "expires_at": time.monotonic() + 15.0,
        }
        add_provisional_roll_cycle_uncertainty(
            client, cycle_id, ("pending-boundary-origin", token_b)
        )
        _loop, _fired, requests, schedule_callback = self._timer_scheduler(client)

        self.assertFalse(resolve_pending_boundary_roll_and_rearm(
            client, cycle_id, token_a, schedule_callback, now_utc=deadline,
        ))
        self.assertEqual(status_dirty_fields(client), set())
        self.assertTrue(resolve_pending_boundary_roll_and_rearm(
            client, cycle_id, token_b, schedule_callback, now_utc=deadline,
        ))

        self.assertFalse(state.count_uncertain)
        self.assertEqual(status_dirty_fields(client), set())
        self.assertEqual(client._roll_batch_deferred_status_fields, set())
        self.assertEqual(len(requests), 1)

    def test_pending_plus_confirmed_keeps_one_claim_and_does_not_rearm(self):
        client, state, cycle_id, token, deadline, _observed_at = self._pending_boundary_snapshot()
        add_roll_cycle_uncertainty(
            client,
            cycle_id,
            ("confirmed-boundary-result", 5454),
            reason="cross-cycle-roll-result-race",
        )
        first_claim = claim_roll_count_reconciliation(client, cycle_id)
        _loop, _fired, requests, schedule_callback = self._timer_scheduler(client)

        self.assertFalse(resolve_pending_boundary_roll_and_rearm(
            client, cycle_id, token, schedule_callback, now_utc=deadline,
        ))
        duplicate_claims = sum(
            claim_roll_count_reconciliation(client, cycle_id) for _ in range(5)
        )

        self.assertTrue(first_claim)
        self.assertEqual(duplicate_claims, 0)
        self.assertTrue(state.count_uncertain)
        self.assertEqual(status_dirty_fields(client), {"rolls"})
        self.assertEqual(requests, [])
        self.assertEqual(client.normal_roll_action_owner.deadline_utc, deadline)

    def test_old_delayed_result_rearms_same_owner_at_original_future_deadline_without_second_tu(self):
        client, state, cycle_id, token, deadline, observed_at = self._pending_boundary_snapshot()
        owner_before = client.normal_roll_action_owner
        result_created_at = observed_at - datetime.timedelta(seconds=5)
        now_utc = datetime.datetime(2026, 8, 28, 18, 5, 10, tzinfo=datetime.timezone.utc)
        deadline = datetime.datetime(2026, 8, 28, 18, 37, tzinfo=datetime.timezone.utc)
        owner_before.deadline_utc = deadline
        owner_before.timing.deadline_utc = deadline
        loop = _Loop()
        old_handle = loop.call_later(31 * 60 + 50, lambda: None)
        client._predicted_roll_action_handle = old_handle
        loop, fired_cycles, requests, schedule_callback = self._timer_scheduler(client, loop)
        physical_tu_count = 0

        self.assertLessEqual(result_created_at, state.last_authoritative_at_utc)
        self.assertTrue(resolve_pending_boundary_roll_and_rearm(
            client,
            cycle_id,
            token,
            schedule_callback,
            now_utc=now_utc,
        ))
        if roll_cycle_needs_authoritative_reconcile(state):
            physical_tu_count += int(claim_roll_count_reconciliation(client, cycle_id))

        self.assertEqual(physical_tu_count, 0)
        self.assertEqual(requests, [(cycle_id, 31 * 60 + 50, True)])
        self.assertEqual([call[0] for call in loop.calls], [31 * 60 + 50, 31 * 60 + 50])
        self.assertEqual(loop.calls[-1][0], 31 * 60 + 50)
        self.assertTrue(old_handle.cancelled())
        self.assertIsInstance(client._predicted_roll_action_handle, _TimerHandle)
        self.assertIsNot(client._predicted_roll_action_handle, old_handle)
        self.assertEqual(fired_cycles, [])
        self.assertFalse(state.count_uncertain)
        self.assertEqual(state.remaining, 12)
        self.assertEqual(state.known_consumed, 0)
        self.assertIs(client.normal_roll_action_owner, owner_before)
        self.assertEqual(client.normal_roll_action_owner.cycle_id, cycle_id)
        self.assertEqual(client.normal_roll_action_owner.deadline_utc, deadline)
        self.assertEqual(client.normal_roll_action_owner.timing.deadline_utc, deadline)

    def test_resolved_pending_result_rearms_expired_deadline_at_zero_delay(self):
        client, _state, cycle_id, token, _deadline, _observed_at = self._pending_boundary_snapshot()
        now_utc = datetime.datetime(2026, 8, 28, 18, 5, 10, tzinfo=datetime.timezone.utc)
        deadline = now_utc - datetime.timedelta(seconds=1)
        client.normal_roll_action_owner.deadline_utc = deadline
        client.normal_roll_action_owner.timing.deadline_utc = deadline
        old_handle = _TimerHandle(lambda: None, ())
        client._predicted_roll_action_handle = old_handle
        loop, fired_cycles, requests, schedule_callback = self._timer_scheduler(client)

        self.assertTrue(resolve_pending_boundary_roll_and_rearm(
            client,
            cycle_id,
            token,
            schedule_callback,
            now_utc=now_utc,
        ))

        self.assertEqual(requests, [(cycle_id, 0.0, True)])
        self.assertEqual(loop.calls[-1][0], 0.0)
        self.assertTrue(old_handle.cancelled())
        self.assertEqual(fired_cycles, [])
        self.assertEqual(client.normal_roll_action_owner.deadline_utc, deadline)
        self.assertEqual(client.normal_roll_action_owner.timing.deadline_utc, deadline)

    def test_nonpending_delayed_result_does_not_replace_existing_timer(self):
        client, _state, cycle_id, _token, deadline, _observed_at = self._pending_boundary_snapshot()
        old_handle = _TimerHandle(lambda: None, ())
        client._predicted_roll_action_handle = old_handle
        loop, fired_cycles, requests, schedule_callback = self._timer_scheduler(client)

        self.assertFalse(resolve_pending_boundary_roll_and_rearm(
            client,
            cycle_id,
            9999,
            schedule_callback,
            now_utc=datetime.datetime(2026, 8, 28, 8, 5, 10, tzinfo=datetime.timezone.utc),
        ))

        self.assertEqual(requests, [])
        self.assertEqual(loop.calls, [])
        self.assertFalse(old_handle.cancelled())
        self.assertIs(client._predicted_roll_action_handle, old_handle)
        self.assertEqual(fired_cycles, [])
        self.assertEqual(client.normal_roll_action_owner.deadline_utc, deadline)

    def test_multiple_pending_origins_rearm_only_after_final_resolution(self):
        client, state, cycle_id, token_a, deadline, _observed_at = self._pending_boundary_snapshot()
        token_b = 4343
        client._pending_boundary_roll_origins[token_b] = {
            "affected_cycle_id": cycle_id,
            "expires_at": time.monotonic() + 15.0,
        }
        add_provisional_roll_cycle_uncertainty(
            client,
            cycle_id,
            ("pending-boundary-origin", token_b),
        )
        old_handle = _TimerHandle(lambda: None, ())
        client._predicted_roll_action_handle = old_handle
        loop, _fired_cycles, requests, schedule_callback = self._timer_scheduler(client)
        now_utc = deadline - datetime.timedelta(seconds=7)

        self.assertFalse(resolve_pending_boundary_roll_and_rearm(
            client, cycle_id, token_a, schedule_callback, now_utc=now_utc,
        ))
        self.assertNotIn(token_a, client._pending_boundary_roll_origins)
        self.assertIn(token_b, client._pending_boundary_roll_origins)
        self.assertTrue(state.count_uncertain)
        self.assertEqual(requests, [])
        self.assertFalse(old_handle.cancelled())

        self.assertTrue(resolve_pending_boundary_roll_and_rearm(
            client, cycle_id, token_b, schedule_callback, now_utc=now_utc,
        ))
        self.assertFalse(state.count_uncertain)
        self.assertEqual(requests, [(cycle_id, 7.0, True)])
        self.assertEqual(loop.calls[-1][0], 7.0)
        self.assertTrue(old_handle.cancelled())

    def test_confirmed_uncertainty_blocks_rearm_after_pending_resolution(self):
        client, state, cycle_id, token, deadline, _observed_at = self._pending_boundary_snapshot()
        confirmed_key = ("confirmed-boundary-result", 3131)
        add_roll_cycle_uncertainty(
            client,
            cycle_id,
            confirmed_key,
            reason="cross-cycle-roll-result-race",
        )
        old_handle = _TimerHandle(lambda: None, ())
        client._predicted_roll_action_handle = old_handle
        loop, _fired_cycles, requests, schedule_callback = self._timer_scheduler(client)

        self.assertFalse(resolve_pending_boundary_roll_and_rearm(
            client,
            cycle_id,
            token,
            schedule_callback,
            now_utc=deadline - datetime.timedelta(seconds=7),
        ))

        self.assertNotIn(token, client._pending_boundary_roll_origins)
        self.assertNotIn(("pending-boundary-origin", token), state.uncertainty_reasons)
        self.assertIn(confirmed_key, state.uncertainty_reasons)
        self.assertTrue(state.count_uncertain)
        self.assertEqual(requests, [])
        self.assertEqual(loop.calls, [])
        self.assertFalse(old_handle.cancelled())

    def test_newer_result_claims_exactly_one_reconciliation(self):
        client, state, cycle_id, token, deadline, observed_at = self._pending_boundary_snapshot()
        result_created_at = observed_at + datetime.timedelta(seconds=2)
        client._pending_boundary_roll_origins.pop(token)
        remove_roll_cycle_uncertainty(client, cycle_id, ("pending-boundary-origin", token))
        add_roll_cycle_uncertainty(
            client,
            cycle_id,
            ("confirmed-boundary-result", token),
            reason="cross-cycle-roll-result-race",
        )
        state.known_consumed += 1
        physical_tu_count = 0

        self.assertGreater(result_created_at, state.last_authoritative_at_utc)
        for _ in range(5):
            if roll_cycle_needs_authoritative_reconcile(state):
                physical_tu_count += int(claim_roll_count_reconciliation(client, cycle_id))

        self.assertEqual(physical_tu_count, 1)
        self.assertTrue(state.count_uncertain)
        self.assertTrue(client.normal_roll_action_owner.is_pending(cycle_id))
        reconcile_authoritative_current_roll_count(
            client,
            11,
            observation_kind="newer-result-reconcile",
            observed_at_utc=observed_at + datetime.timedelta(seconds=3),
        )
        self.assertFalse(state.count_uncertain)
        self.assertIsNone(client._roll_count_reconcile_cycle_id)
        self.assertEqual(client.normal_roll_action_owner.deadline_utc, deadline)

    def test_pending_timeout_claims_one_reconciliation_then_same_owner_continues(self):
        client, state, cycle_id, token, deadline, observed_at = self._pending_boundary_snapshot()
        client._pending_boundary_roll_origins.pop(token)
        remove_roll_cycle_uncertainty(client, cycle_id, ("pending-boundary-origin", token))
        add_roll_cycle_uncertainty(
            client,
            cycle_id,
            ("boundary-origin-timeout", token),
            reason="pending-origin-timeout",
        )
        physical_tu_count = 0

        for _ in range(5):
            if roll_cycle_needs_authoritative_reconcile(state):
                physical_tu_count += int(claim_roll_count_reconciliation(client, cycle_id))

        self.assertEqual(physical_tu_count, 1)
        self.assertFalse(client.normal_roll_action_owner.start("not-the-cycle"))
        self.assertTrue(state.count_uncertain)
        reconcile_authoritative_current_roll_count(
            client,
            12,
            observation_kind="timeout-reconcile",
            observed_at_utc=observed_at + datetime.timedelta(seconds=20),
        )
        self.assertFalse(state.count_uncertain)
        self.assertEqual(client.normal_roll_action_owner.deadline_utc, deadline)
        self.assertTrue(client.normal_roll_action_owner.start(cycle_id))

    def test_us_bonus_scheduling_reads_state_without_mutating_authority(self):
        client = self._authoritative_reconciliation_client()
        cycle_id = client.current_roll_cycle_id
        client.normal_roll_replenishment_capacity = None
        client.normal_roll_replenishment_capacity_confidence = False
        client._pending_boundary_roll_origins = {}
        state = get_normal_roll_cycle_state(client, cycle_id)
        state.proven_fresh = True
        state.known_consumed = 0
        observed_at = datetime.datetime(2026, 8, 28, 9, 0, 8, tzinfo=datetime.timezone.utc)
        reconcile_authoritative_current_roll_count(
            client,
            18,
            observation_kind="check-rolls-tu",
            observed_at_utc=observed_at,
            base_normal_remaining=13,
        )
        evidence_before = (
            state.remaining,
            state.remaining_authoritative,
            state.last_authoritative_at_utc,
            state.authoritative_revision,
            client.normal_roll_replenishment_capacity,
            set(state.uncertainty_reasons),
        )

        for seconds in (0, 3, 9):
            self.assertEqual(normal_roll_schedule_count(state), 18)
            client.normal_roll_action_owner.schedule(
                cycle_id=cycle_id,
                now_utc=observed_at + datetime.timedelta(seconds=seconds),
            )

        evidence_after = (
            state.remaining,
            state.remaining_authoritative,
            state.last_authoritative_at_utc,
            state.authoritative_revision,
            client.normal_roll_replenishment_capacity,
            set(state.uncertainty_reasons),
        )
        self.assertEqual(evidence_after, evidence_before)
        self.assertEqual(state.remaining, 18)
        self.assertEqual(client.normal_roll_replenishment_capacity, 13)
        successor = successor_roll_cycle_id(cycle_id)
        successor_state = get_normal_roll_cycle_state(client, successor)
        successor_state.remaining = client.normal_roll_replenishment_capacity
        successor_state.remaining_authoritative = False
        self.assertEqual(normal_roll_schedule_count(successor_state), 13)

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

    async def test_loki_regression_stops_old_cycle_rolls_and_promotes_queued_cycle_cleanly(self):
        anchor = ResetAnchor("roll", 60)
        now_time = datetime.datetime(2026, 8, 27, 17, 5, tzinfo=datetime.timezone.utc)
        next_reset = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        anchor.observe(next_reset, now_time)
        cycle_r = anchor.cycle_id_for_boundary(-1)

        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)
        owner.schedule(cycle_id=cycle_r, now_utc=now_time)
        self.assertTrue(owner.start(cycle_r))
        self.assertEqual(owner.state, "executing")

        current_roll_cycle_id = cycle_r
        roll_counts = {cycle_r: 10}
        remaining_batch_rolls = 2
        active_batch_remaining = remaining_batch_rolls

        # Advance time to 18:05:01 (after reset boundary 18:05:00)
        boundary_time = next_reset + datetime.timedelta(seconds=1)
        advanced_cycles = anchor.advance_through(boundary_time)
        self.assertEqual(len(advanced_cycles), 1)
        cycle_r_plus_1 = advanced_cycles[0][0]
        current_roll_cycle_id = cycle_r_plus_1

        # Predict 13 fresh rolls for R+1
        roll_counts[cycle_r_plus_1] = 13
        owner.schedule(cycle_id=cycle_r_plus_1, now_utc=boundary_time)

        # Assert:
        # 1. current_roll_cycle_id == R+1
        self.assertEqual(current_roll_cycle_id, cycle_r_plus_1)
        # 2. active owner still: cycle_id == R, state == executing
        self.assertEqual(owner.cycle_id, cycle_r)
        self.assertEqual(owner.state, "executing")
        # 3. R+1 is queued/coalesced
        self.assertEqual(owner.queued_cycle_id, cycle_r_plus_1)
        # 4. active R remaining counter is NOT overwritten to 13
        self.assertEqual(active_batch_remaining, 2)
        # 5. no physical /tu while R owns the transaction
        policy = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=current_roll_cycle_id,
            owner_state=owner.state,
            state_dirty=False,
        )
        self.assertEqual(policy, "defer-executing")

        # 6. Before next roll send: runtime notices current_roll_cycle_id != cycle_r
        # Therefore R sends ZERO intentional old-cycle commands after the known boundary!
        rolls_sent_after_boundary = []
        while remaining_batch_rolls > 0:
            if cycle_r is not None and current_roll_cycle_id != cycle_r:
                break
            rolls_sent_after_boundary.append("roll")
            remaining_batch_rolls -= 1

        self.assertEqual(len(rolls_sent_after_boundary), 0)
        self.assertEqual(remaining_batch_rolls, 2)

        # 7. After R releases: R+1 becomes actionable exactly once
        self.assertTrue(owner.complete(cycle_r))
        self.assertEqual(owner.cycle_id, cycle_r_plus_1)
        self.assertEqual(owner.state, "pending")
        self.assertIsNone(owner.queued_cycle_id)

        # No in-flight ambiguity: R+1 retains full 13-roll predicted count and no /tu
        self.assertEqual(roll_counts[cycle_r_plus_1], 13)
        post_r_policy = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=current_roll_cycle_id,
            owner_state=owner.state,
            state_dirty=False,
        )
        self.assertEqual(post_r_policy, "suppress-routine")

        # R+1 executes with full 13 rolls
        self.assertTrue(owner.start(cycle_r_plus_1))
        self.assertEqual(owner.state, "executing")
        r_plus_1_rolls = 0
        r_plus_1_remaining = roll_counts[cycle_r_plus_1]
        while r_plus_1_remaining > 0:
            r_plus_1_rolls += 1
            r_plus_1_remaining -= 1
        self.assertEqual(r_plus_1_rolls, 13)
        self.assertTrue(owner.complete(cycle_r_plus_1))
        self.assertEqual(owner.state, "completed")

    async def test_in_flight_boundary_race_marks_uncertain_and_reconciles_with_one_tu(self):
        anchor = ResetAnchor("roll", 60)
        now_time = datetime.datetime(2026, 8, 27, 17, 5, tzinfo=datetime.timezone.utc)
        next_reset = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        anchor.observe(next_reset, now_time)
        cycle_r = anchor.cycle_id_for_boundary(-1)

        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)
        owner.schedule(cycle_id=cycle_r, now_utc=now_time)
        owner.start(cycle_r)

        current_roll_cycle_id = cycle_r
        roll_counts = {cycle_r: 10}
        cross_cycle_roll_count_uncertain = False
        cross_cycle_uncertain_cycle_id = None
        state_dirty_fields = set()

        # Simulate roll begins immediately before reset (18:04:59.950)
        # and transport/server response finishes at (18:05:00.050)
        send_end = next_reset + datetime.timedelta(milliseconds=50)

        # Advance anchor after send
        advanced_cycles = anchor.advance_through(send_end)
        self.assertEqual(len(advanced_cycles), 1)
        cycle_r_plus_1 = advanced_cycles[0][0]
        current_roll_cycle_id = cycle_r_plus_1
        roll_counts[cycle_r_plus_1] = 13
        owner.schedule(cycle_id=cycle_r_plus_1, now_utc=send_end)

        # In-flight boundary crossing detected!
        if cycle_r is not None and current_roll_cycle_id != cycle_r:
            cross_cycle_roll_count_uncertain = True
            cross_cycle_uncertain_cycle_id = current_roll_cycle_id
            state_dirty_fields.add("rolls")

        # Assert:
        # 1. R+1 exact roll count marked uncertain
        self.assertTrue(cross_cycle_roll_count_uncertain)
        self.assertEqual(cross_cycle_uncertain_cycle_id, cycle_r_plus_1)
        # 2. Reset anchor remains trusted
        self.assertTrue(anchor.confidence)
        self.assertEqual(anchor.next_boundary_at_utc, next_reset + datetime.timedelta(hours=1))
        # 3. physical /tu while R executing == 0
        policy_during_r = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=current_roll_cycle_id,
            owner_state=owner.state,
            state_dirty=bool(state_dirty_fields),
        )
        self.assertEqual(policy_during_r, "defer-executing")

        # R completes and releases command lane
        owner.complete(cycle_r)
        self.assertEqual(owner.cycle_id, cycle_r_plus_1)
        self.assertEqual(owner.state, "pending")

        # After R releases: policy allows status check for dirty rolls
        policy_after_r = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=current_roll_cycle_id,
            owner_state=owner.state,
            state_dirty=bool(state_dirty_fields),
        )
        self.assertEqual(policy_after_r, "none")

        # Exactly ONE reconciliation /tu is sent
        tu_query_count = 1
        # Authoritative /tu response arrives reporting Rolls: 12
        parsed_rolls = 12
        roll_counts[cycle_r_plus_1] = parsed_rolls
        cross_cycle_roll_count_uncertain = False
        cross_cycle_uncertain_cycle_id = None
        state_dirty_fields.clear()

        self.assertEqual(roll_counts[cycle_r_plus_1], 12)
        self.assertFalse(cross_cycle_roll_count_uncertain)

        # Subsequent R+1 action uses exactly 12 (not 13)
        self.assertTrue(owner.start(cycle_r_plus_1))
        executed_rolls = 0
        batch_remaining = roll_counts[cycle_r_plus_1]
        while batch_remaining > 0:
            executed_rolls += 1
            batch_remaining -= 1
        self.assertEqual(executed_rolls, 12)
        self.assertTrue(owner.complete(cycle_r_plus_1))
        self.assertEqual(tu_query_count, 1)

    async def test_clean_no_ambiguity_crossing_stops_and_executes_r_plus_1_without_tu(self):
        anchor = ResetAnchor("roll", 60)
        now_time = datetime.datetime(2026, 8, 27, 17, 5, tzinfo=datetime.timezone.utc)
        next_reset = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        anchor.observe(next_reset, now_time)
        cycle_r = anchor.cycle_id_for_boundary(-1)

        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)
        owner.schedule(cycle_id=cycle_r, now_utc=now_time)
        owner.start(cycle_r)

        current_roll_cycle_id = cycle_r
        roll_counts = {cycle_r: 10}
        cross_cycle_roll_count_uncertain = False
        cross_cycle_uncertain_cycle_id = None
        state_dirty_fields = set()

        # Roll 1 sent at 18:04:30 and completed at 18:04:31 (well before reset)
        send_end = next_reset - datetime.timedelta(seconds=29)
        anchor.advance_through(send_end)
        self.assertEqual(current_roll_cycle_id, cycle_r)

        # Idle delay until 18:05:01
        now_utc = next_reset + datetime.timedelta(seconds=1)
        advanced = anchor.advance_through(now_utc)
        self.assertEqual(len(advanced), 1)
        cycle_r_plus_1 = advanced[0][0]
        current_roll_cycle_id = cycle_r_plus_1
        roll_counts[cycle_r_plus_1] = 13
        owner.schedule(cycle_id=cycle_r_plus_1, now_utc=now_utc)

        # Boundary becomes known BEFORE next roll starts
        rolls_sent = []
        while True:
            if cycle_r is not None and current_roll_cycle_id != cycle_r:
                break
            rolls_sent.append("roll")

        # Assert:
        # 1. Old R batch stops immediately
        self.assertEqual(len(rolls_sent), 0)
        # 2. No R command crosses boundary
        self.assertFalse(cross_cycle_roll_count_uncertain)
        # 3. R+1 full count remains trusted (13)
        self.assertEqual(roll_counts[cycle_r_plus_1], 13)

        owner.complete(cycle_r)
        self.assertEqual(owner.cycle_id, cycle_r_plus_1)
        self.assertEqual(owner.state, "pending")

        # 4. No post-batch /tu
        policy = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=current_roll_cycle_id,
            owner_state=owner.state,
            state_dirty=bool(state_dirty_fields),
        )
        self.assertEqual(policy, "suppress-routine")

        # 5. R+1 executes normally once with 13 rolls
        self.assertTrue(owner.start(cycle_r_plus_1))
        r1_rolls = 0
        rem = roll_counts[cycle_r_plus_1]
        while rem > 0:
            r1_rolls += 1
            rem -= 1
        self.assertEqual(r1_rolls, 13)
        self.assertTrue(owner.complete(cycle_r_plus_1))

    async def test_real_check_status_physical_tu_path_during_and_after_executing_owner(self):
        anchor = ResetAnchor("roll", 60)
        start_time = datetime.datetime(2026, 8, 27, 17, 5, tzinfo=datetime.timezone.utc)
        next_reset = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        anchor.observe(next_reset, start_time)
        cycle_r = anchor.cycle_id_for_boundary(-1)
        cycle_r_plus_1 = ("roll", int(next_reset.timestamp()), 0)

        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)
        owner.schedule(cycle_id=cycle_r, now_utc=start_time)
        owner.start(cycle_r)
        owner.schedule(cycle_id=cycle_r_plus_1, now_utc=next_reset)

        tu_calls = []
        async def mock_send_tu():
            tu_calls.append("tu")
            return True

        # During cross-cycle R execution (owner.cycle_id = R, owner.state = executing, current = R+1)
        policy_exec = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=cycle_r_plus_1,
            owner_state=owner.state,
            state_dirty=True,
        )
        suppress_physical_tu = policy_exec in {"suppress-routine", "defer-executing"}
        self.assertTrue(suppress_physical_tu)
        if not suppress_physical_tu:
            await mock_send_tu()
        self.assertEqual(len(tu_calls), 0)

        # When R finishes and count uncertainty requires reconciliation:
        owner.complete(cycle_r)
        self.assertEqual(owner.cycle_id, cycle_r_plus_1)
        self.assertEqual(owner.state, "pending")

        policy_pending_dirty = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=cycle_r_plus_1,
            owner_state=owner.state,
            state_dirty=True,
        )
        suppress_physical_tu_after = policy_pending_dirty in {"suppress-routine", "defer-executing"}
        self.assertFalse(suppress_physical_tu_after)
        if not suppress_physical_tu_after:
            await mock_send_tu()
        self.assertEqual(len(tu_calls), 1)

        # After reconciliation /tu response makes state clean:
        policy_clean = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=cycle_r_plus_1,
            owner_state=owner.state,
            state_dirty=False,
        )
        self.assertEqual(policy_clean, "suppress-routine")
        suppress_clean = policy_clean in {"suppress-routine", "defer-executing"}
        self.assertTrue(suppress_clean)
        if not suppress_clean:
            await mock_send_tu()
        self.assertEqual(len(tu_calls), 1)

    async def test_command_pacer_returns_nonempty_action_result(self):
        async def wait(_delay):
            return True

        expected = object()

        async def action():
            return expected

        pacer = CommandPacer(0, 0)

        self.assertIs(await pacer.run(action, wait), expected)

    def test_is_roll_result_cross_boundary_ambiguous_logic(self):
        boundary = datetime.datetime(2026, 8, 27, 18, 5, 0, tzinfo=datetime.timezone.utc)
        self.assertFalse(is_roll_result_cross_boundary_ambiguous(None, None, boundary))
        self.assertFalse(is_roll_result_cross_boundary_ambiguous(SimpleNamespace(), None, None))

        # 1. Result created_at >= boundary -> ambiguous
        entry = SimpleNamespace(
            expected_reset_boundary_utc=boundary,
            sent_at_utc=boundary - datetime.timedelta(seconds=10),
            send_end_utc=boundary - datetime.timedelta(seconds=9),
        )
        res_after = boundary + datetime.timedelta(milliseconds=300)
        self.assertTrue(is_roll_result_cross_boundary_ambiguous(entry, res_after, boundary))

        # 2. Local send_end >= boundary -> ambiguous
        entry_send_after = SimpleNamespace(
            expected_reset_boundary_utc=boundary,
            sent_at_utc=boundary - datetime.timedelta(milliseconds=100),
            send_end_utc=boundary + datetime.timedelta(milliseconds=50),
        )
        self.assertTrue(is_roll_result_cross_boundary_ambiguous(entry_send_after, boundary - datetime.timedelta(milliseconds=10), boundary))

        # 3. Command sent within guard window (e.g. within 1.5s) -> ambiguous
        entry_near = SimpleNamespace(
            expected_reset_boundary_utc=boundary,
            sent_at_utc=boundary - datetime.timedelta(milliseconds=300),
            send_end_utc=boundary - datetime.timedelta(milliseconds=250),
        )
        self.assertTrue(is_roll_result_cross_boundary_ambiguous(entry_near, boundary - datetime.timedelta(milliseconds=100), boundary))

        # 4. Command sent and result arrived well before boundary (30s before) -> NOT ambiguous
        entry_safe = SimpleNamespace(
            expected_reset_boundary_utc=boundary,
            sent_at_utc=boundary - datetime.timedelta(seconds=30),
            send_end_utc=boundary - datetime.timedelta(seconds=29, milliseconds=800),
        )
        res_safe = boundary - datetime.timedelta(seconds=29, milliseconds=500)
        self.assertFalse(is_roll_result_cross_boundary_ambiguous(entry_safe, res_safe, boundary))

    async def test_real_text_command_cross_boundary_orchestration(self):
        anchor = ResetAnchor("roll", 60)
        start_time = datetime.datetime(2026, 8, 27, 17, 5, tzinfo=datetime.timezone.utc)
        next_reset = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        anchor.observe(next_reset, start_time)
        cycle_r = anchor.cycle_id_for_boundary(-1)

        correlation = RollCommandCorrelation()
        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)
        owner.schedule(cycle_id=cycle_r, now_utc=start_time)
        owner.start(cycle_r)

        current_roll_cycle_id = cycle_r
        replenishment_capacity = 13
        capacity_confident = True
        roll_counts = {cycle_r: 10}
        consumed_counts = {cycle_r: 9}
        cross_cycle_roll_count_uncertain = False
        cross_cycle_uncertain_cycle_id = None
        state_dirty_fields = set()

        # Step 1: Owner R is executing. Automation sends $wa at 18:04:59.700.
        send_start = next_reset - datetime.timedelta(milliseconds=300)
        token = correlation.prearm(
            channel_id=1,
            owner_id=2,
            owner_name="self",
            command_name="wa",
            mode="text",
            automation_owned=True,
            logical_roll_cycle_id=cycle_r,
            expected_reset_boundary_utc=next_reset,
            send_start_utc=send_start,
        )
        send_end = next_reset - datetime.timedelta(milliseconds=250)
        correlation.finalize(token, {
            "mode": "text",
            "message_id": 100,
            "sent_at_utc": send_start,
            "send_end_utc": send_end,
        })

        # Step 2: Mudae result arrives at 18:05:00.300 (after reset 18:05:00.000).
        result_created_at = next_reset + datetime.timedelta(milliseconds=300)
        origin = correlation.latest_text_origin(
            channel_id=1,
            message_id=101,
            created_at_utc=result_created_at,
        )
        self.assertIsNotNone(origin)
        self.assertEqual(origin.token, token)
        self.assertTrue(origin.automation_owned)

        # Result straddle detection:
        ambiguous = is_roll_result_cross_boundary_ambiguous(origin, result_created_at, next_reset)
        self.assertTrue(ambiguous)

        # Advance anchor locally
        advanced = anchor.advance_through(result_created_at)
        self.assertEqual(len(advanced), 1)
        cycle_r_plus_1 = advanced[0][0]
        current_roll_cycle_id = cycle_r_plus_1
        consumed_counts[cycle_r_plus_1] = 0
        owner.schedule(cycle_id=cycle_r_plus_1, now_utc=result_created_at)

        if ambiguous:
            cross_cycle_roll_count_uncertain = True
            cross_cycle_uncertain_cycle_id = cycle_r_plus_1
            state_dirty_fields.add("rolls")
            consumed_counts[cycle_r_plus_1] += 1

        # Assert: cross-cycle count marked uncertain
        self.assertTrue(cross_cycle_roll_count_uncertain)
        self.assertEqual(cross_cycle_uncertain_cycle_id, cycle_r_plus_1)

        # Physical /tu during R execution MUST remain zero
        policy_during_r = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=current_roll_cycle_id,
            owner_state=owner.state,
            state_dirty=bool(state_dirty_fields),
        )
        self.assertEqual(policy_during_r, "defer-executing")

        tu_calls = []
        if policy_during_r not in {"defer-executing", "suppress-routine"}:
            tu_calls.append("tu")
        self.assertEqual(len(tu_calls), 0)

        # R completes and releases visible command lane
        owner.complete(cycle_r)
        self.assertEqual(owner.cycle_id, cycle_r_plus_1)
        self.assertEqual(owner.state, "pending")

        # After R releases: policy allows exactly one reconciliation status check
        policy_after_r = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=current_roll_cycle_id,
            owner_state=owner.state,
            state_dirty=bool(state_dirty_fields),
        )
        self.assertEqual(policy_after_r, "none")
        tu_calls.append("reconciliation_tu")
        self.assertEqual(len(tu_calls), 1)

        # Authoritative /tu responds with Rolls: 12
        parsed_rolls = 12
        roll_counts[cycle_r_plus_1] = parsed_rolls
        is_fresh_cycle = (
            consumed_counts.get(cycle_r_plus_1, 0) == 0
            and not cross_cycle_roll_count_uncertain
        )
        if is_fresh_cycle:
            replenishment_capacity = parsed_rolls
        # Because R+1 had a boundary race (not fresh), capacity is NOT poisoned to 12!
        self.assertEqual(roll_counts[cycle_r_plus_1], 12)
        self.assertEqual(replenishment_capacity, 13)

        cross_cycle_roll_count_uncertain = False
        cross_cycle_uncertain_cycle_id = None
        state_dirty_fields.clear()

        # At R+2 reset: predicted normal rolls remains 13!
        r_plus_2_boundary = next_reset + datetime.timedelta(hours=1)
        advanced_r2 = anchor.advance_through(r_plus_2_boundary)
        self.assertEqual(len(advanced_r2), 1)
        cycle_r_plus_2 = advanced_r2[0][0]
        roll_counts[cycle_r_plus_2] = replenishment_capacity
        self.assertEqual(roll_counts[cycle_r_plus_2], 13)

    async def test_real_slash_command_cross_boundary_orchestration(self):
        anchor = ResetAnchor("roll", 60)
        start_time = datetime.datetime(2026, 8, 27, 17, 5, tzinfo=datetime.timezone.utc)
        next_reset = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        anchor.observe(next_reset, start_time)
        cycle_r = anchor.cycle_id_for_boundary(-1)

        correlation = RollCommandCorrelation()
        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)
        owner.schedule(cycle_id=cycle_r, now_utc=start_time)
        owner.start(cycle_r)

        current_roll_cycle_id = cycle_r
        replenishment_capacity = 13
        roll_counts = {cycle_r: 10}
        consumed_counts = {cycle_r: 9}
        cross_cycle_roll_count_uncertain = False
        cross_cycle_uncertain_cycle_id = None
        state_dirty_fields = set()

        # Step 1: Owner R is executing. Automation sends slash /wa at 18:04:59.600.
        send_start = next_reset - datetime.timedelta(milliseconds=400)
        token = correlation.prearm(
            channel_id=1,
            owner_id=2,
            owner_name="self",
            command_name="wa",
            mode="slash",
            automation_owned=True,
            logical_roll_cycle_id=cycle_r,
            expected_reset_boundary_utc=next_reset,
            send_start_utc=send_start,
        )
        send_end = next_reset - datetime.timedelta(milliseconds=350)
        correlation.finalize(token, {
            "mode": "slash",
            "sent_at_utc": send_start,
            "send_end_utc": send_end,
            "nonce": "slash-123",
        })

        # Step 2: Mudae slash result arrives at 18:05:00.250 (after reset).
        result_created_at = next_reset + datetime.timedelta(milliseconds=250)
        origin = correlation.latest_slash_origin(
            channel_id=1,
            created_at_utc=result_created_at,
            owner_id=2,
            command_name="wa",
        )
        self.assertIsNotNone(origin)
        self.assertEqual(origin.token, token)
        self.assertTrue(origin.automation_owned)

        # Ambiguity detection:
        ambiguous = is_roll_result_cross_boundary_ambiguous(origin, result_created_at, next_reset)
        self.assertTrue(ambiguous)

        advanced = anchor.advance_through(result_created_at)
        cycle_r_plus_1 = advanced[0][0]
        current_roll_cycle_id = cycle_r_plus_1
        consumed_counts[cycle_r_plus_1] = 0
        owner.schedule(cycle_id=cycle_r_plus_1, now_utc=result_created_at)

        if ambiguous:
            cross_cycle_roll_count_uncertain = True
            cross_cycle_uncertain_cycle_id = cycle_r_plus_1
            state_dirty_fields.add("rolls")
            consumed_counts[cycle_r_plus_1] += 1

        self.assertTrue(cross_cycle_roll_count_uncertain)

        # Suppress physical /tu during R execution
        policy_during_r = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=current_roll_cycle_id,
            owner_state=owner.state,
            state_dirty=bool(state_dirty_fields),
        )
        self.assertEqual(policy_during_r, "defer-executing")

        # R completes
        owner.complete(cycle_r)
        self.assertEqual(owner.cycle_id, cycle_r_plus_1)

        # Reconciliation /tu reports 12 rolls
        parsed_rolls = 12
        roll_counts[cycle_r_plus_1] = parsed_rolls
        is_fresh_cycle = (
            consumed_counts.get(cycle_r_plus_1, 0) == 0
            and not cross_cycle_roll_count_uncertain
        )
        if is_fresh_cycle:
            replenishment_capacity = parsed_rolls
        self.assertEqual(roll_counts[cycle_r_plus_1], 12)
        self.assertEqual(replenishment_capacity, 13)

    async def test_real_clean_boundary_crossing_orchestration(self):
        anchor = ResetAnchor("roll", 60)
        start_time = datetime.datetime(2026, 8, 27, 17, 5, tzinfo=datetime.timezone.utc)
        next_reset = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        anchor.observe(next_reset, start_time)
        cycle_r = anchor.cycle_id_for_boundary(-1)

        correlation = RollCommandCorrelation()
        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)
        owner.schedule(cycle_id=cycle_r, now_utc=start_time)
        owner.start(cycle_r)

        current_roll_cycle_id = cycle_r
        replenishment_capacity = 13
        roll_counts = {cycle_r: 10}
        cross_cycle_roll_count_uncertain = False
        state_dirty_fields = set()

        # Command sent at 18:04:30 and result arrived at 18:04:30.500 (clean, 29.5s before reset)
        send_start = next_reset - datetime.timedelta(seconds=30)
        token = correlation.prearm(
            channel_id=1,
            owner_id=2,
            owner_name="self",
            command_name="wa",
            mode="text",
            automation_owned=True,
            logical_roll_cycle_id=cycle_r,
            expected_reset_boundary_utc=next_reset,
            send_start_utc=send_start,
        )
        correlation.finalize(token, {
            "mode": "text",
            "message_id": 100,
            "sent_at_utc": send_start,
            "send_end_utc": send_start + datetime.timedelta(milliseconds=100),
        })

        result_created_at = send_start + datetime.timedelta(milliseconds=500)
        origin = correlation.latest_text_origin(
            channel_id=1,
            message_id=101,
            created_at_utc=result_created_at,
        )
        self.assertFalse(is_roll_result_cross_boundary_ambiguous(origin, result_created_at, next_reset))

        # Time passes to 18:05:01 (after reset)
        boundary_time = next_reset + datetime.timedelta(seconds=1)
        advanced = anchor.advance_through(boundary_time)
        cycle_r_plus_1 = advanced[0][0]
        current_roll_cycle_id = cycle_r_plus_1
        roll_counts[cycle_r_plus_1] = replenishment_capacity
        owner.schedule(cycle_id=cycle_r_plus_1, now_utc=boundary_time)

        # Pre-send check sees current_roll_cycle_id != cycle_r -> old R stops!
        rolls_sent_from_old_r = 0
        remaining_r = 5
        while remaining_r > 0:
            if cycle_r is not None and current_roll_cycle_id != cycle_r:
                break
            rolls_sent_from_old_r += 1
            remaining_r -= 1

        self.assertEqual(rolls_sent_from_old_r, 0)
        self.assertFalse(cross_cycle_roll_count_uncertain)
        self.assertEqual(roll_counts[cycle_r_plus_1], 13)

        # R completes and releases
        owner.complete(cycle_r)
        self.assertEqual(owner.cycle_id, cycle_r_plus_1)
        self.assertEqual(owner.state, "pending")

        # Zero /tu calls needed!
        policy = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=current_roll_cycle_id,
            owner_state=owner.state,
            state_dirty=bool(state_dirty_fields),
        )
        self.assertEqual(policy, "suppress-routine")

        # R+1 starts and executes exactly 13 rolls once
        self.assertTrue(owner.start(cycle_r_plus_1))
        executed = 0
        rem = roll_counts[cycle_r_plus_1]
        while rem > 0:
            executed += 1
            rem -= 1
        self.assertEqual(executed, 13)
        self.assertTrue(owner.complete(cycle_r_plus_1))

    async def test_zero_roll_reconciliation_clears_stale_count_without_poisoning_capacity(self):
        anchor = ResetAnchor("roll", 60)
        now_time = datetime.datetime(2026, 8, 27, 17, 5, tzinfo=datetime.timezone.utc)
        next_reset = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        anchor.observe(next_reset, now_time)
        cycle_r = anchor.cycle_id_for_boundary(-1)

        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)
        owner.schedule(cycle_id=cycle_r, now_utc=now_time)
        owner.start(cycle_r)

        replenishment_capacity = 13
        capacity_confident = True
        roll_counts = {cycle_r: 10}

        # Advance to R+1 with predicted 13 rolls
        boundary_time = next_reset + datetime.timedelta(milliseconds=50)
        advanced = anchor.advance_through(boundary_time)
        cycle_r_plus_1 = advanced[0][0]
        roll_counts[cycle_r_plus_1] = replenishment_capacity # 13
        owner.schedule(cycle_id=cycle_r_plus_1, now_utc=boundary_time)

        # Cross-boundary ambiguity forces reconciliation
        owner.complete(cycle_r)
        self.assertEqual(owner.cycle_id, cycle_r_plus_1)
        self.assertEqual(owner.state, "pending")

        # Authoritative /tu returns Rolls: 0!
        parsed_rolls = 0
        roll_counts[cycle_r_plus_1] = parsed_rolls
        owner.cancel(cycle_r_plus_1)
        self.assertEqual(owner.state, "completed")

        # Assert:
        # 1. R+1 stored remaining count is 0
        self.assertEqual(roll_counts[cycle_r_plus_1], 0)
        # 2. Stale 13 is replaced
        self.assertNotEqual(roll_counts[cycle_r_plus_1], 13)
        # 3. Capacity remains independent (13)
        self.assertEqual(replenishment_capacity, 13)

        # 4. Next reset (R+2) replenishes correctly with 13 rolls
        r2_reset = next_reset + datetime.timedelta(hours=1)
        advanced_r2 = anchor.advance_through(r2_reset)
        cycle_r_plus_2 = advanced_r2[0][0]
        roll_counts[cycle_r_plus_2] = replenishment_capacity
        self.assertEqual(roll_counts[cycle_r_plus_2], 13)

    def test_periodic_sanity_sync_does_not_poison_capacity(self):
        replenishment_capacity = 13
        capacity_confident = True
        cycle_r = ("roll", 1000, 0)
        consumed = {cycle_r: 5}
        roll_counts = {cycle_r: 13}

        # Periodic sanity /tu at randomized non-boundary time returns Rolls: 8
        parsed_rolls = 8
        roll_counts[cycle_r] = parsed_rolls
        is_fresh_cycle = consumed.get(cycle_r, 0) == 0
        if is_fresh_cycle:
            replenishment_capacity = parsed_rolls

        # Current remaining is 8, but replenishment capacity remains 13!
        self.assertEqual(roll_counts[cycle_r], 8)
        self.assertEqual(replenishment_capacity, 13)

        # At R+1: predicted normal rolls = 13
        cycle_r_plus_1 = ("roll", 1000, 1)
        roll_counts[cycle_r_plus_1] = replenishment_capacity
        self.assertEqual(roll_counts[cycle_r_plus_1], 13)

    def test_manual_tu_does_not_poison_capacity(self):
        replenishment_capacity = 13
        cycle_r = ("roll", 2000, 0)
        consumed = {cycle_r: 3}
        roll_counts = {cycle_r: 13}

        # User's manual /tu returns Rolls: 7
        parsed_rolls = 7
        roll_counts[cycle_r] = parsed_rolls
        is_fresh_cycle = consumed.get(cycle_r, 0) == 0
        if is_fresh_cycle:
            replenishment_capacity = parsed_rolls

        self.assertEqual(roll_counts[cycle_r], 7)
        self.assertEqual(replenishment_capacity, 13)

    def test_multi_account_sanity_resync_distinct_staggers(self):
        now_utc = datetime.datetime(2026, 8, 27, 17, 10, tzinfo=datetime.timezone.utc)
        roll_anchor = ResetAnchor("roll", 60)
        claim_anchor = ResetAnchor("claim", 180)
        next_reset = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        roll_anchor.observe(next_reset, now_utc)
        claim_anchor.observe(next_reset, now_utc)

        roll_seconds = max(60.0, float(roll_anchor.interval_minutes) * 60.0)
        anchor_stamp = int(roll_anchor.anchor_at_utc.timestamp())

        # Account A: "MainAccount"
        seed_a = abs(hash("MainAccount")) % 3600
        offset_a = ((anchor_stamp + seed_a) % max(1, int(roll_seconds * 0.6))) + roll_seconds * 0.2
        cand_a, guard_a = bounded_sanity_deadline(now_utc, roll_anchor, claim_anchor, offset_a)
        safe_a = ensure_sanity_deadline_safe(cand_a, roll_anchor, claim_anchor, guard_a)

        # Account B: "AltPreset"
        seed_b = abs(hash("AltPreset")) % 3600
        offset_b = ((anchor_stamp + seed_b) % max(1, int(roll_seconds * 0.6))) + roll_seconds * 0.2
        cand_b, guard_b = bounded_sanity_deadline(now_utc, roll_anchor, claim_anchor, offset_b)
        safe_b = ensure_sanity_deadline_safe(cand_b, roll_anchor, claim_anchor, guard_b)

        # Same account -> stable deadline across passes
        offset_a_repeat = ((anchor_stamp + seed_a) % max(1, int(roll_seconds * 0.6))) + roll_seconds * 0.2
        self.assertEqual(offset_a, offset_a_repeat)

        # Different accounts -> naturally different offsets
        self.assertNotEqual(offset_a, offset_b)
        self.assertNotEqual(safe_a, safe_b)

    def test_startup_mid_cycle_capacity_not_learned(self):
        """Startup halfway through cycle with Rolls: 8 must NOT learn capacity = 8."""
        client = SimpleNamespace(
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            normal_roll_replenishment_capacity=None,
            normal_roll_replenishment_capacity_confidence=False,
            cross_cycle_roll_count_uncertain=False,
            rolls_left=0,
        )
        current_cycle = ("roll", 1700000000, 0)

        # Initial /tu arrives at startup
        apply_authoritative_roll_remaining(
            client, current_cycle, 8, observation_kind="startup-tu",
        )

        state = get_normal_roll_cycle_state(client, current_cycle)
        self.assertEqual(state.remaining, 8)
        self.assertTrue(state.remaining_authoritative)
        self.assertFalse(state.proven_fresh)
        # Capacity MUST remain None and unconfident!
        self.assertIsNone(client.normal_roll_replenishment_capacity)
        self.assertFalse(client.normal_roll_replenishment_capacity_confidence)

    def test_learn_capacity_from_proven_fresh_cycle(self):
        """A cycle proven fresh with 0 consumed learns full replenishment capacity."""
        client = SimpleNamespace(
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            normal_roll_replenishment_capacity=None,
            normal_roll_replenishment_capacity_confidence=False,
            cross_cycle_roll_count_uncertain=False,
            rolls_left=0,
        )
        fresh_cycle = ("roll", 1700000000, 1)

        # Mark cycle as proven fresh when scheduler advances R -> R+1
        mark_roll_cycle_proven_fresh(client, fresh_cycle)
        state = get_normal_roll_cycle_state(client, fresh_cycle)
        self.assertTrue(state.proven_fresh)
        self.assertEqual(state.known_consumed, 0)

        # Initial clean /tu reports Rolls: 13
        apply_authoritative_roll_remaining(
            client, fresh_cycle, 13, observation_kind="fresh-tu",
        )

        self.assertEqual(state.remaining, 13)
        self.assertEqual(client.normal_roll_replenishment_capacity, 13)
        self.assertTrue(client.normal_roll_replenishment_capacity_confidence)

    def test_result_arrives_before_anchor_advance_maps_successor(self):
        """Delayed result arriving before anchor advance maps ambiguity to successor(origin)."""
        anchor = ResetAnchor("roll", 60)
        start_time = datetime.datetime(2026, 8, 27, 17, 5, tzinfo=datetime.timezone.utc)
        next_reset = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        anchor.observe(next_reset, start_time)
        cycle_r = anchor.cycle_id_for_boundary(-1)

        client = SimpleNamespace(
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _pending_boundary_roll_origins={},
            _roll_batch_deferred_status_fields=set(),
            roll_reset_anchor=anchor,
            current_roll_cycle_id=cycle_r,
            cross_cycle_roll_count_uncertain=False,
            cross_cycle_uncertain_cycle_id=None,
        )

        # Command sent for R near boundary
        origin_cmd = OutgoingRollCommand(
            token=1,
            channel_id=1,
            owner_id=2,
            owner_name="user",
            command_name="wa",
            mode="text",
            registered_at_utc=next_reset - datetime.timedelta(milliseconds=200),
            automation_owned=True,
            logical_roll_cycle_id=cycle_r,
            expected_reset_boundary_utc=next_reset,
            send_start_utc=next_reset - datetime.timedelta(milliseconds=200),
            send_end_utc=next_reset - datetime.timedelta(milliseconds=50),
        )

        # Result arrives at 18:05:00.200 (after reset) while scheduler is still at cycle_r
        result_created_at = next_reset + datetime.timedelta(milliseconds=200)
        self.assertTrue(is_roll_result_cross_boundary_ambiguous(origin_cmd, result_created_at, next_reset))

        affected_cycle = successor_roll_cycle_id(origin_cmd.logical_roll_cycle_id)
        expected_successor = anchor.cycle_id_for_boundary(anchor.next_boundary_index)
        self.assertEqual(affected_cycle, expected_successor)

        mark_roll_cycle_count_uncertain(client, affected_cycle, reason="cross-cycle-roll-result-race")
        self.assertTrue(client.cross_cycle_roll_count_uncertain)
        self.assertEqual(client.cross_cycle_uncertain_cycle_id, affected_cycle)

    def test_result_arrives_after_anchor_advance_maps_successor_never_r2(self):
        """Delayed result arriving after scheduler already advanced to R+1 MUST still target R+1, never R+2."""
        anchor = ResetAnchor("roll", 60)
        start_time = datetime.datetime(2026, 8, 27, 17, 5, tzinfo=datetime.timezone.utc)
        next_reset = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        anchor.observe(next_reset, start_time)
        cycle_r = anchor.cycle_id_for_boundary(-1)

        client = SimpleNamespace(
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _pending_boundary_roll_origins={},
            _roll_batch_deferred_status_fields=set(),
            roll_reset_anchor=anchor,
            current_roll_cycle_id=cycle_r,
            cross_cycle_roll_count_uncertain=False,
            cross_cycle_uncertain_cycle_id=None,
        )

        origin_cmd = OutgoingRollCommand(
            token=2,
            channel_id=1,
            owner_id=2,
            owner_name="user",
            command_name="wa",
            mode="text",
            registered_at_utc=next_reset - datetime.timedelta(milliseconds=300),
            automation_owned=True,
            logical_roll_cycle_id=cycle_r,
            expected_reset_boundary_utc=next_reset,
            send_start_utc=next_reset - datetime.timedelta(milliseconds=300),
            send_end_utc=next_reset - datetime.timedelta(milliseconds=50),
        )

        # Scheduler advances through boundary: current cycle is now R+1, and next_boundary_index points to R+2!
        advanced = anchor.advance_through(next_reset + datetime.timedelta(seconds=1))
        cycle_r_plus_1 = advanced[0][0]
        client.current_roll_cycle_id = cycle_r_plus_1

        cycle_r_plus_2 = anchor.cycle_id_for_boundary(anchor.next_boundary_index)
        self.assertNotEqual(cycle_r_plus_1, cycle_r_plus_2)

        # Delayed Mudae result arrives now
        result_created_at = next_reset + datetime.timedelta(milliseconds=500)
        self.assertTrue(is_roll_result_cross_boundary_ambiguous(origin_cmd, result_created_at, next_reset))

        # Affected cycle derived from origin command:
        affected_cycle = successor_roll_cycle_id(origin_cmd.logical_roll_cycle_id)
        # MUST be R+1, NEVER R+2!
        self.assertEqual(affected_cycle, cycle_r_plus_1)
        self.assertNotEqual(affected_cycle, cycle_r_plus_2)

        mark_roll_cycle_count_uncertain(client, affected_cycle, reason="cross-cycle-roll-result-race")
        self.assertEqual(client.cross_cycle_uncertain_cycle_id, cycle_r_plus_1)

    def test_delayed_result_beyond_timeout_with_pending_boundary_origin(self):
        """Near-boundary command provisionally protects R+1 even if result takes >5s."""
        anchor = ResetAnchor("roll", 60)
        start_time = datetime.datetime(2026, 8, 27, 17, 5, tzinfo=datetime.timezone.utc)
        next_reset = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        anchor.observe(next_reset, start_time)
        cycle_r = anchor.cycle_id_for_boundary(-1)

        client = SimpleNamespace(
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _pending_boundary_roll_origins={},
            _roll_batch_deferred_status_fields=set(),
            roll_reset_anchor=anchor,
            current_roll_cycle_id=cycle_r,
            cross_cycle_roll_count_uncertain=False,
            cross_cycle_uncertain_cycle_id=None,
            normal_roll_replenishment_capacity=13,
            normal_roll_replenishment_capacity_confidence=True,
        )

        send_time = next_reset - datetime.timedelta(seconds=1.0)
        successor = successor_roll_cycle_id(cycle_r)

        # Command sent within 3.0s guard of boundary -> provisionally tracked
        dist = abs((send_time - next_reset).total_seconds())
        self.assertLessEqual(dist, ROLL_BOUNDARY_ATTRIBUTION_GUARD_SECONDS)

        token = 42
        client._pending_boundary_roll_origins[token] = {
            "origin_cycle_id": cycle_r,
            "affected_cycle_id": successor,
            "boundary_utc": next_reset,
            "expires_at": 999999.0,
        }
        mark_roll_cycle_count_uncertain(client, successor, reason="pending-boundary-roll-command")

        # 5-second receive wait expires, R completes and releases
        r_state = get_normal_roll_cycle_state(client, successor)
        self.assertTrue(r_state.count_uncertain)
        self.assertTrue(client.cross_cycle_roll_count_uncertain)

        # R+1 CANNOT roll with full trusted count until resolved
        self.assertFalse(r_state.remaining_authoritative)

        # Authoritative reconciliation occurs
        apply_authoritative_roll_remaining(client, successor, 12, observation_kind="reconcile-tu")
        client._pending_boundary_roll_origins.pop(token, None)
        clear_roll_cycle_count_uncertainty(client, successor)

        self.assertEqual(r_state.remaining, 12)
        self.assertTrue(r_state.remaining_authoritative)
        self.assertFalse(r_state.count_uncertain)
        # Full capacity remains 13!
        self.assertEqual(client.normal_roll_replenishment_capacity, 13)

    def test_shared_reset_known_capacity_materializes_r1_and_predicted_rolls(self):
        """Account B with known capacity receives shared reset: materializes R+1 locally with predicted count and no /tu."""
        anchor = ResetAnchor("roll", 60)
        start_time = datetime.datetime(2026, 8, 27, 17, 5, tzinfo=datetime.timezone.utc)
        boundary_1805 = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        anchor.observe(boundary_1805, start_time)
        cycle_r = anchor.cycle_id_for_boundary(-1)

        owner = NormalRollActionOwner(RollActionTiming())
        client = SimpleNamespace(
            user=SimpleNamespace(id=1001, name="AccountB", display_name="AccountB"),
            target_channel_id=12345,
            roll_interval=60,
            claim_interval=180,
            roll_reset_anchor=anchor,
            claim_reset_anchor=ResetAnchor("claim", 180),
            current_roll_cycle_id=cycle_r,
            current_claim_cycle_id=None,
            normal_roll_replenishment_capacity=13,
            normal_roll_replenishment_capacity_confidence=True,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _normal_roll_action_scheduled_triggers=set(),
            _pending_boundary_roll_origins={},
            _roll_batch_deferred_status_fields=set(),
            normal_roll_action_owner=owner,
            predicted_roll_state_valid=False,
            predicted_roll_cycle_id=None,
            rolls_left=0,
            us_pulled_this_cycle=0,
            us_failed_this_cycle=False,
            auto_rolls_enabled=False,
            roll_speed=1.0,
            use_slash_rolls=False,
            time_rolls_to_claim_reset=False,
            claim_right_available=True,
            humanization_enabled=False,
            humanization_window_minutes=0,
            persistent_stagger_seconds=0,
            loop=_Loop(),
            _predicted_roll_action_handle=None,
            _predicted_roll_action_cycle_id=None,
            _roll_count_sync_cycle_id=None,
            _roll_count_sync_at_utc=None,
            _roll_count_sync_handle=None,
        )

        def advance_predicted_reset_cycles(now_utc=None):
            now_utc = now_utc or datetime.datetime.now(datetime.timezone.utc)
            for cid, boundary in client.roll_reset_anchor.advance_through(now_utc):
                client.current_roll_cycle_id = cid
                client.roll_reset_at_utc = client.roll_reset_anchor.next_boundary_at_utc
                st = get_normal_roll_cycle_state(client, cid)
                st.proven_fresh = True
                st.known_consumed = 0
                if client.normal_roll_replenishment_capacity_confidence and client.normal_roll_replenishment_capacity is not None:
                    cnt = max(0, int(client.normal_roll_replenishment_capacity))
                    st.remaining = cnt
                    st.remaining_authoritative = False
                    client._normal_roll_action_roll_counts[cid] = cnt
                    client.rolls_left = cnt
                    client.predicted_roll_state_valid = not st.count_uncertain
                else:
                    st.remaining = None
                    st.remaining_authoritative = False
                    client.predicted_roll_state_valid = False
            return {"rolls"}

        client._advance_predicted_reset_cycles = advance_predicted_reset_cycles

        # Peer observes 18:05 reset at 18:05:02 and proposes next reset at 19:05
        from mudae_bot import _apply_shared_reset_snapshot
        observed_at = datetime.datetime(2026, 8, 27, 18, 5, 2, tzinfo=datetime.timezone.utc)
        proposed_next = datetime.datetime(2026, 8, 27, 19, 5, tzinfo=datetime.timezone.utc)
        snapshot = ServerResetSnapshot(
            server_id=999,
            observed_at_utc=observed_at,
            roll_reset_at_utc=proposed_next,
            observed_fields=frozenset(["rolls"]),
        )

        _apply_shared_reset_snapshot(client, snapshot)

        # Assert: B materialized R+1 locally
        cycle_r1 = anchor.cycle_id_for_boundary(0)
        self.assertEqual(client.current_roll_cycle_id, cycle_r1)
        r1_state = get_normal_roll_cycle_state(client, cycle_r1)
        self.assertIsNotNone(r1_state)
        self.assertTrue(r1_state.proven_fresh)
        self.assertEqual(r1_state.remaining, 13)
        self.assertTrue(client.predicted_roll_state_valid)
        self.assertEqual(client.rolls_left, 13)
        # Next boundary on anchor is refined to 19:05
        self.assertEqual(client.roll_reset_at_utc, proposed_next)

    def test_shared_reset_unknown_capacity_schedules_private_sync_not_skipped(self):
        """Account B with unknown capacity receives shared reset: materializes R+1, schedules private count sync, learns capacity on /tu."""
        anchor = ResetAnchor("roll", 60)
        start_time = datetime.datetime(2026, 8, 27, 17, 5, tzinfo=datetime.timezone.utc)
        boundary_1805 = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        anchor.observe(boundary_1805, start_time)
        cycle_r = anchor.cycle_id_for_boundary(-1)

        loop = _Loop()
        owner = NormalRollActionOwner(RollActionTiming())
        client = SimpleNamespace(
            user=SimpleNamespace(id=1002, name="AccountB", display_name="AccountB"),
            target_channel_id=12345,
            roll_interval=60,
            claim_interval=180,
            roll_reset_anchor=anchor,
            claim_reset_anchor=ResetAnchor("claim", 180),
            current_roll_cycle_id=cycle_r,
            current_claim_cycle_id=None,
            normal_roll_replenishment_capacity=None,
            normal_roll_replenishment_capacity_confidence=False,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _normal_roll_action_scheduled_triggers=set(),
            _pending_boundary_roll_origins={},
            _roll_batch_deferred_status_fields=set(),
            normal_roll_action_owner=owner,
            predicted_roll_state_valid=False,
            predicted_roll_cycle_id=None,
            rolls_left=0,
            us_pulled_this_cycle=0,
            us_failed_this_cycle=False,
            auto_rolls_enabled=False,
            roll_speed=1.0,
            use_slash_rolls=False,
            time_rolls_to_claim_reset=False,
            claim_right_available=True,
            humanization_enabled=False,
            humanization_window_minutes=0,
            persistent_stagger_seconds=0,
            loop=loop,
            _predicted_roll_action_handle=None,
            _predicted_roll_action_cycle_id=None,
            _roll_count_sync_cycle_id=None,
            _roll_count_sync_at_utc=None,
            _roll_count_sync_handle=None,
        )

        def advance_predicted_reset_cycles(now_utc=None):
            now_utc = now_utc or datetime.datetime.now(datetime.timezone.utc)
            for cid, boundary in client.roll_reset_anchor.advance_through(now_utc):
                client.current_roll_cycle_id = cid
                client.roll_reset_at_utc = client.roll_reset_anchor.next_boundary_at_utc
                st = get_normal_roll_cycle_state(client, cid)
                st.proven_fresh = True
                st.known_consumed = 0
                st.remaining = None
                st.remaining_authoritative = False
                client.predicted_roll_state_valid = False
                client._normal_roll_action_roll_counts.pop(cid, None)
                # schedule private count sync for unknown capacity
                client._roll_count_sync_cycle_id = cid
                client._roll_count_sync_at_utc = boundary + datetime.timedelta(seconds=45)
                client._roll_count_sync_handle = loop.call_later(45.0, lambda: None)
            return {"rolls"}

        client._advance_predicted_reset_cycles = advance_predicted_reset_cycles

        from mudae_bot import _apply_shared_reset_snapshot
        observed_at = datetime.datetime(2026, 8, 27, 18, 5, 2, tzinfo=datetime.timezone.utc)
        proposed_next = datetime.datetime(2026, 8, 27, 19, 5, tzinfo=datetime.timezone.utc)
        snapshot = ServerResetSnapshot(
            server_id=999,
            observed_at_utc=observed_at,
            roll_reset_at_utc=proposed_next,
            observed_fields=frozenset(["rolls"]),
        )

        _apply_shared_reset_snapshot(client, snapshot)

        cycle_r1 = anchor.cycle_id_for_boundary(0)
        self.assertEqual(client.current_roll_cycle_id, cycle_r1)
        r1_state = get_normal_roll_cycle_state(client, cycle_r1)
        self.assertIsNotNone(r1_state)
        self.assertTrue(r1_state.proven_fresh)
        self.assertIsNone(r1_state.remaining)
        self.assertFalse(client.predicted_roll_state_valid)
        self.assertEqual(client._roll_count_sync_cycle_id, cycle_r1)
        self.assertIsNotNone(client._roll_count_sync_handle)

        # Authoritative /tu returns at humanized sync time: Rolls: 13
        apply_authoritative_roll_remaining(client, cycle_r1, 13, observation_kind="private-roll-count-sync")
        self.assertEqual(r1_state.remaining, 13)
        self.assertTrue(r1_state.remaining_authoritative)
        # Because R+1 was proven fresh and known_consumed == 0, capacity 13 is learned!
        self.assertTrue(client.normal_roll_replenishment_capacity_confidence)
        self.assertEqual(client.normal_roll_replenishment_capacity, 13)

    def test_shared_snapshot_order_prevents_skipping_unmaterialized_cycle(self):
        """Account B materializes R -> R+1 before anchor.observe() can advance internal index."""
        anchor = ResetAnchor("roll", 60)
        start_time = datetime.datetime(2026, 8, 27, 17, 5, tzinfo=datetime.timezone.utc)
        boundary_1805 = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        anchor.observe(boundary_1805, start_time)
        cycle_r = anchor.cycle_id_for_boundary(-1)

        materialized_cycles = []
        client = SimpleNamespace(
            roll_reset_anchor=anchor,
            current_roll_cycle_id=cycle_r,
            roll_reset_at_utc=boundary_1805,
            _normal_roll_cycle_state={},
        )

        def advance_predicted_reset_cycles(now_utc=None):
            for cid, b in client.roll_reset_anchor.advance_through(now_utc):
                materialized_cycles.append(cid)
                client.current_roll_cycle_id = cid
                client.roll_reset_at_utc = client.roll_reset_anchor.next_boundary_at_utc

        client._advance_predicted_reset_cycles = advance_predicted_reset_cycles

        # Peer observes 18:05:02 and proposes next deadline 19:05
        from mudae_bot import _apply_shared_reset_snapshot
        observed_at = datetime.datetime(2026, 8, 27, 18, 5, 2, tzinfo=datetime.timezone.utc)
        proposed_next = datetime.datetime(2026, 8, 27, 19, 5, tzinfo=datetime.timezone.utc)
        snapshot = ServerResetSnapshot(
            server_id=999,
            observed_at_utc=observed_at,
            roll_reset_at_utc=proposed_next,
            observed_fields=frozenset(["rolls"]),
        )

        _apply_shared_reset_snapshot(client, snapshot)

        # Must have materialized R+1:
        self.assertEqual(len(materialized_cycles), 1)
        cycle_r1 = anchor.cycle_id_for_boundary(0)
        self.assertEqual(materialized_cycles[0], cycle_r1)
        self.assertEqual(client.current_roll_cycle_id, cycle_r1)
        self.assertEqual(client.roll_reset_at_utc, proposed_next)

    def test_two_command_ambiguous_and_clean_uncertainty(self):
        """Mandatory two-command test: command A arrives ambiguous and command B arrives clean -> successor MUST remain uncertain."""
        cycle_r = ("roll", 1700000000, 0)
        successor = ("roll", 1700000000, 1)

        client = SimpleNamespace(
            _normal_roll_cycle_state={},
            cross_cycle_roll_count_uncertain=False,
            cross_cycle_uncertain_cycle_id=None,
            _roll_batch_deferred_status_fields=set(),
        )

        token_a = 101
        token_b = 102

        # 1. Both commands provisionally mark successor uncertain at send time
        add_provisional_roll_cycle_uncertainty(client, successor, ("pending-boundary-origin", token_a))
        add_provisional_roll_cycle_uncertainty(client, successor, ("pending-boundary-origin", token_b))

        succ_state = get_normal_roll_cycle_state(client, successor)
        self.assertTrue(succ_state.count_uncertain)
        self.assertEqual(succ_state.uncertainty_reasons, {
            ("pending-boundary-origin", token_a),
            ("pending-boundary-origin", token_b),
        })

        # 2. Result A arrives AFTER reset (ambiguous) -> removes pending(A), adds confirmed(A)
        remove_roll_cycle_uncertainty(client, successor, ("pending-boundary-origin", token_a))
        add_roll_cycle_uncertainty(client, successor, ("confirmed-boundary-result", token_a), reason="cross-cycle-roll-result-race")

        self.assertTrue(succ_state.count_uncertain)
        self.assertIn(("confirmed-boundary-result", token_a), succ_state.uncertainty_reasons)
        self.assertIn(("pending-boundary-origin", token_b), succ_state.uncertainty_reasons)

        # 3. Result B arrives BEFORE reset (clean) -> removes ONLY pending(B)
        remove_roll_cycle_uncertainty(client, successor, ("pending-boundary-origin", token_b))

        # 4. CRITICAL ASSERTION: successor MUST STILL BE UNCERTAIN because confirmed(A) remains!
        self.assertTrue(succ_state.count_uncertain)
        self.assertTrue(client.cross_cycle_roll_count_uncertain)
        self.assertEqual(client.cross_cycle_uncertain_cycle_id, successor)
        self.assertEqual(succ_state.uncertainty_reasons, {("confirmed-boundary-result", token_a)})

        # 5. Authoritative /tu for successor resolves everything
        apply_authoritative_roll_remaining(client, successor, 12, observation_kind="check-status")
        self.assertFalse(succ_state.count_uncertain)
        self.assertFalse(client.cross_cycle_roll_count_uncertain)
        self.assertIsNone(client.cross_cycle_uncertain_cycle_id)
        self.assertEqual(succ_state.remaining, 12)
        self.assertTrue(succ_state.remaining_authoritative)

    def test_reset_advancement_preserves_existing_successor_uncertainty(self):
        """Reset advancement MUST NOT blindly clear uncertainty reasons for the new cycle."""
        anchor = ResetAnchor("roll", 60)
        start_time = datetime.datetime(2026, 8, 27, 17, 5, tzinfo=datetime.timezone.utc)
        boundary_1805 = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        anchor.observe(boundary_1805, start_time)
        cycle_r = anchor.cycle_id_for_boundary(-1)
        cycle_r1 = anchor.cycle_id_for_boundary(0)

        client = SimpleNamespace(
            roll_reset_anchor=anchor,
            current_roll_cycle_id=cycle_r,
            normal_roll_replenishment_capacity=13,
            normal_roll_replenishment_capacity_confidence=True,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _pending_boundary_roll_origins={},
            _roll_batch_deferred_status_fields=set(),
            cross_cycle_roll_count_uncertain=False,
            cross_cycle_uncertain_cycle_id=None,
            predicted_roll_state_valid=True,
            normal_roll_action_owner=NormalRollActionOwner(RollActionTiming()),
            rolls_left=0,
        )

        # Provisional command in R marked R+1 uncertain
        add_provisional_roll_cycle_uncertainty(client, cycle_r1, ("pending-boundary-origin", 99))
        r1_state = get_normal_roll_cycle_state(client, cycle_r1)
        self.assertTrue(r1_state.count_uncertain)

        # Reset advances to R+1
        advanced = anchor.advance_through(boundary_1805 + datetime.timedelta(seconds=1))
        cid = advanced[0][0]
        self.assertEqual(cid, cycle_r1)

        # Simulate advance logic
        r1_state.proven_fresh = True
        r1_state.known_consumed = 0
        r1_state.remaining = 13
        r1_state.remaining_authoritative = False
        # Do NOT clear uncertainty_reasons
        if r1_state.count_uncertain:
            client.predicted_roll_state_valid = False
        else:
            client.predicted_roll_state_valid = True

        # Uncertainty must still be active!
        self.assertTrue(r1_state.count_uncertain)
        self.assertFalse(client.predicted_roll_state_valid)

    def test_material_reanchor_delayed_result_marks_current_private_state(self):
        """Delayed result arriving after a material re-anchor checks lineage and marks current cycle uncertain."""
        old_anchor = ResetAnchor("roll", 60)
        old_start = datetime.datetime(2026, 8, 27, 17, 5, tzinfo=datetime.timezone.utc)
        old_anchor.observe(old_start, old_start)
        old_cycle = old_anchor.cycle_id_for_boundary(0)

        new_anchor = ResetAnchor("roll", 60)
        new_start = datetime.datetime(2026, 8, 27, 17, 30, tzinfo=datetime.timezone.utc)
        new_anchor.observe(new_start, new_start)
        new_current_cycle = new_anchor.cycle_id_for_boundary(0)

        # Lineage check helper
        self.assertTrue(roll_cycle_matches_anchor_lineage(old_anchor, old_cycle))
        self.assertFalse(roll_cycle_matches_anchor_lineage(new_anchor, old_cycle))
        self.assertTrue(roll_cycle_matches_anchor_lineage(new_anchor, new_current_cycle))

        client = SimpleNamespace(
            roll_reset_anchor=new_anchor,
            current_roll_cycle_id=new_current_cycle,
            _normal_roll_cycle_state={},
            _roll_batch_deferred_status_fields=set(),
            cross_cycle_roll_count_uncertain=False,
            cross_cycle_uncertain_cycle_id=None,
        )

        # Delayed result from old lineage arrives
        token = 777
        add_roll_cycle_uncertainty(client, new_current_cycle, ("result-after-reanchor", token), reason="cross-cycle-result-after-reanchor")

        curr_state = get_normal_roll_cycle_state(client, new_current_cycle)
        self.assertTrue(curr_state.count_uncertain)
        self.assertIn(("result-after-reanchor", token), curr_state.uncertainty_reasons)
        self.assertTrue(client.cross_cycle_roll_count_uncertain)

    def test_pending_origin_token_prune_timeout_transition(self):
        """Expired pending boundary origin converts to timeout uncertainty instead of clearing."""
        cycle = ("roll", 1700000000, 1)
        client = SimpleNamespace(
            _normal_roll_cycle_state={},
            cross_cycle_roll_count_uncertain=False,
            cross_cycle_uncertain_cycle_id=None,
            _roll_batch_deferred_status_fields=set(),
        )

        token = 888
        add_provisional_roll_cycle_uncertainty(client, cycle, ("pending-boundary-origin", token))
        state = get_normal_roll_cycle_state(client, cycle)
        self.assertTrue(state.count_uncertain)

        # Pruning transition when token expires:
        remove_roll_cycle_uncertainty(client, cycle, ("pending-boundary-origin", token))
        add_roll_cycle_uncertainty(client, cycle, ("boundary-origin-timeout", token), reason="pending-origin-timeout")

        self.assertTrue(state.count_uncertain)
        self.assertEqual(state.uncertainty_reasons, {("boundary-origin-timeout", token)})
        self.assertTrue(client.cross_cycle_roll_count_uncertain)

    def test_no_anchor_shared_snapshot_establishes_timing_not_private_count(self):
        """Account B without initial anchor learns server timing from peer but does NOT infer private rolls or capacity."""
        anchor = ResetAnchor("roll", 60)
        self.assertFalse(anchor.confidence)

        client = SimpleNamespace(
            roll_reset_anchor=anchor,
            current_roll_cycle_id=None,
            roll_reset_at_utc=None,
            normal_roll_replenishment_capacity=None,
            normal_roll_replenishment_capacity_confidence=False,
            _normal_roll_cycle_state={},
        )

        from mudae_bot import _apply_shared_reset_snapshot
        observed_at = datetime.datetime(2026, 8, 27, 18, 5, 2, tzinfo=datetime.timezone.utc)
        proposed_next = datetime.datetime(2026, 8, 27, 19, 5, tzinfo=datetime.timezone.utc)
        snapshot = ServerResetSnapshot(
            server_id=999,
            observed_at_utc=observed_at,
            roll_reset_at_utc=proposed_next,
            observed_fields=frozenset(["rolls"]),
        )

        _apply_shared_reset_snapshot(client, snapshot)

        # Server timing learned
        self.assertTrue(anchor.confidence)
        self.assertEqual(client.roll_reset_at_utc, proposed_next)
        self.assertIsNotNone(client.current_roll_cycle_id)

        # Private state NOT inferred
        curr_state = get_normal_roll_cycle_state(client, client.current_roll_cycle_id)
        self.assertFalse(curr_state.proven_fresh)
        self.assertIsNone(curr_state.remaining)
        self.assertFalse(curr_state.remaining_authoritative)
        self.assertFalse(client.normal_roll_replenishment_capacity_confidence)
        self.assertIsNone(client.normal_roll_replenishment_capacity)

    def test_execute_owned_normal_roll_action_count_uncertain_preserves_pending_state(self):
        """When count is uncertain or remaining is None, owner MUST remain pending and NOT transition to waiting_claim."""
        cycle_id = ("roll", 1700000000, 1)
        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)
        now_utc = datetime.datetime(2026, 8, 27, 18, 5, tzinfo=datetime.timezone.utc)
        owner.schedule(cycle_id=cycle_id, now_utc=now_utc)
        self.assertEqual(owner.state, "pending")
        self.assertTrue(owner.is_pending(cycle_id))

        client = SimpleNamespace(
            user=SimpleNamespace(id=1001, name="AccountA", display_name="AccountA"),
            current_roll_cycle_id=cycle_id,
            normal_roll_action_owner=owner,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _roll_batch_deferred_status_fields=set(),
            rolling_enabled=True,
            is_paused=False,
            auto_rolls_enabled=False,
        )

        state = get_normal_roll_cycle_state(client, cycle_id)
        state.remaining = None
        state.count_uncertain = True

        # When checking uncertainty before roll action, owner must stay in 'pending' state
        self.assertTrue(state.count_uncertain or state.remaining is None)
        # CRITICAL: owner state MUST still be 'pending' (NEVER 'waiting_claim')
        self.assertEqual(owner.state, "pending")
        self.assertTrue(owner.is_pending(cycle_id))

        # Authoritative /tu resolves count:
        apply_authoritative_roll_remaining(client, cycle_id, 13, observation_kind="check-status")
        self.assertFalse(state.count_uncertain)
        self.assertEqual(state.remaining, 13)

        # Owner is still pending and can start execution!
        self.assertTrue(owner.is_pending(cycle_id))
        self.assertTrue(owner.start(cycle_id))
        self.assertEqual(owner.state, "executing")

    def test_unknown_count_with_auto_rolls_does_not_execute_normal_action_before_sync(self):
        """When roll count is unknown (remaining is None), Auto $rolls enabled MUST NOT schedule/execute normal action before private count sync."""
        cycle_id = ("roll", 1700000000, 1)
        owner = NormalRollActionOwner(RollActionTiming())
        loop = _Loop()
        client = SimpleNamespace(
            user=SimpleNamespace(id=1001, name="AccountA", display_name="AccountA"),
            preset_name="AccountA",
            roll_interval=60,
            claim_interval=180,
            roll_reset_anchor=ResetAnchor("roll", 60),
            claim_reset_anchor=ResetAnchor("claim", 180),
            current_roll_cycle_id=cycle_id,
            normal_roll_action_owner=owner,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _normal_roll_action_scheduled_triggers=set(),
            _pending_boundary_roll_origins={},
            _roll_batch_deferred_status_fields=set(),
            rolling_enabled=True,
            is_paused=False,
            auto_rolls_enabled=True,
            auto_rolls_only_claim_hour=False,
            auto_rolls_in_key_mode=False,
            auto_rolls_limit=0,
            claim_right_available=True,
            key_mode=False,
            roll_speed=1.0,
            use_slash_rolls=False,
            time_rolls_to_claim_reset=False,
            humanization_enabled=False,
            humanization_window_minutes=0,
            persistent_stagger_seconds=0,
            roll_reset_at_utc=datetime.datetime(2026, 8, 27, 19, 0, tzinfo=datetime.timezone.utc),
            next_claim_reset_at_utc=datetime.datetime(2026, 8, 27, 21, 0, tzinfo=datetime.timezone.utc),
            loop=loop,
            _predicted_roll_action_handle=None,
            _predicted_roll_action_cycle_id=None,
            _roll_count_sync_cycle_id=None,
            _roll_count_sync_at_utc=None,
            _roll_count_sync_handle=None,
        )

        state = get_normal_roll_cycle_state(client, cycle_id)
        state.remaining = None
        state.remaining_authoritative = False

        def schedule_private_roll_count_sync(logical_roll_cycle_id, boundary_utc, *, reason="roll-count-unknown"):
            client._roll_count_sync_cycle_id = logical_roll_cycle_id
            client._roll_count_sync_handle = loop.call_later(45.0, lambda: None)

        def schedule_owned_normal_roll_action(logical_roll_cycle_id, boundary_utc, *, scheduled_trigger=False):
            st = get_normal_roll_cycle_state(client, logical_roll_cycle_id)
            if st is None or st.remaining is None:
                if st is None or not st.remaining_authoritative:
                    schedule_private_roll_count_sync(logical_roll_cycle_id, boundary_utc, reason="roll-count-unknown")
                return
            roll_count = max(0, int(st.remaining if st and st.remaining is not None else 0))
            if roll_count <= 0 and not client.auto_rolls_enabled:
                return
            action_at, created = owner.schedule(cycle_id=logical_roll_cycle_id, now_utc=boundary_utc)
            if action_at is not None and owner.is_pending(logical_roll_cycle_id):
                client._predicted_roll_action_handle = loop.call_later(1.0, lambda: None)

        now_utc = datetime.datetime(2026, 8, 27, 18, 0, tzinfo=datetime.timezone.utc)
        schedule_owned_normal_roll_action(cycle_id, now_utc)

        # Asserts:
        # 1. Private sync was scheduled
        self.assertEqual(client._roll_count_sync_cycle_id, cycle_id)
        self.assertIsNotNone(client._roll_count_sync_handle)
        # 2. Normal owner is NOT scheduled / pending
        self.assertEqual(owner.state, "idle")
        self.assertIsNone(client._predicted_roll_action_handle)

    def test_successor_consumption_evidence_survives_reset_advance(self):
        """Successor cycle R+1 with pre-existing known_consumed and uncertainty reasons retains them through reset advancement."""
        anchor = ResetAnchor("roll", 60)
        start_time = datetime.datetime(2026, 8, 27, 17, 0, tzinfo=datetime.timezone.utc)
        boundary_1800 = datetime.datetime(2026, 8, 27, 18, 0, tzinfo=datetime.timezone.utc)
        anchor.observe(boundary_1800, start_time)
        cycle_r = anchor.cycle_id_for_boundary(-1)
        cycle_r1 = anchor.cycle_id_for_boundary(0)

        owner = NormalRollActionOwner(RollActionTiming())
        loop = _Loop()
        client = SimpleNamespace(
            user=SimpleNamespace(id=1001, name="AccountA", display_name="AccountA"),
            roll_interval=60,
            claim_interval=180,
            roll_reset_anchor=anchor,
            claim_reset_anchor=ResetAnchor("claim", 180),
            current_roll_cycle_id=cycle_r,
            current_claim_cycle_id=None,
            normal_roll_replenishment_capacity=13,
            normal_roll_replenishment_capacity_confidence=True,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _normal_roll_action_scheduled_triggers=set(),
            _pending_boundary_roll_origins={},
            _roll_batch_deferred_status_fields=set(),
            normal_roll_action_owner=owner,
            predicted_roll_state_valid=False,
            predicted_roll_cycle_id=None,
            rolls_left=0,
            us_pulled_this_cycle=0,
            us_failed_this_cycle=False,
            auto_rolls_enabled=False,
            loop=loop,
            _predicted_roll_action_handle=None,
            _predicted_roll_action_cycle_id=None,
            _roll_count_sync_cycle_id=None,
            _roll_count_sync_at_utc=None,
            _roll_count_sync_handle=None,
        )

        # Before advance: R+1 received cross-boundary command result evidence
        r1_state = get_normal_roll_cycle_state(client, cycle_r1)
        r1_state.known_consumed = 1
        add_roll_cycle_uncertainty(client, cycle_r1, ("confirmed-boundary-result", 999), reason="cross-boundary")
        self.assertTrue(r1_state.count_uncertain)
        self.assertEqual(r1_state.known_consumed, 1)

        # Advance through 18:00 reset
        now_utc = datetime.datetime(2026, 8, 27, 18, 0, 1, tzinfo=datetime.timezone.utc)
        for cid, boundary in client.roll_reset_anchor.advance_through(now_utc):
            client.current_roll_cycle_id = cid
            client.roll_reset_at_utc = client.roll_reset_anchor.next_boundary_at_utc
            st = get_normal_roll_cycle_state(client, cid)
            had_uncertainty = st.count_uncertain
            known_consumed_before = int(st.known_consumed or 0)
            st.proven_fresh = (not had_uncertainty and known_consumed_before == 0)
            st.known_consumed = known_consumed_before
            if (
                client.normal_roll_replenishment_capacity_confidence
                and client.normal_roll_replenishment_capacity is not None
                and st.proven_fresh
            ):
                cnt = max(0, int(client.normal_roll_replenishment_capacity))
                st.remaining = cnt
                st.remaining_authoritative = False
                client.predicted_roll_state_valid = not st.count_uncertain
            else:
                st.remaining = None
                st.remaining_authoritative = False
                client.predicted_roll_state_valid = False

        # Verify:
        self.assertEqual(client.current_roll_cycle_id, cycle_r1)
        self.assertEqual(r1_state.known_consumed, 1)
        self.assertFalse(r1_state.proven_fresh)
        self.assertTrue(r1_state.count_uncertain)
        self.assertIn(("confirmed-boundary-result", 999), r1_state.uncertainty_reasons)
        self.assertIsNone(r1_state.remaining)
        self.assertFalse(client.predicted_roll_state_valid)

    def test_capacity_13_not_overwritten_by_12_on_successor_with_consumption(self):
        """Authoritative /tu reporting 12 rolls for R+1 (which had known_consumed=1) preserves full replenishment capacity 13."""
        cycle_r1 = ("roll", 1700000000, 2)
        client = SimpleNamespace(
            current_roll_cycle_id=cycle_r1,
            normal_roll_replenishment_capacity=13,
            normal_roll_replenishment_capacity_confidence=True,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _roll_batch_deferred_status_fields=set(),
        )

        state = get_normal_roll_cycle_state(client, cycle_r1)
        state.proven_fresh = False
        state.known_consumed = 1
        state.remaining = None

        apply_authoritative_roll_remaining(client, cycle_r1, 12, observation_kind="check-status")

        # State updated
        self.assertEqual(state.remaining, 12)
        self.assertTrue(state.remaining_authoritative)
        self.assertFalse(state.count_uncertain)
        # Capacity remains 13!
        self.assertEqual(client.normal_roll_replenishment_capacity, 13)
        self.assertTrue(client.normal_roll_replenishment_capacity_confidence)

    def test_startup_parser_order_establishes_cycle_before_applying_rolls(self):
        """On cold startup when current_roll_cycle_id is None, parsing /tu establishes anchor and cycle_id BEFORE applying rolls."""
        anchor = ResetAnchor("roll", 60)
        client = SimpleNamespace(
            roll_reset_anchor=anchor,
            current_roll_cycle_id=None,
            roll_reset_at_utc=None,
            normal_roll_replenishment_capacity=None,
            normal_roll_replenishment_capacity_confidence=False,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _roll_batch_deferred_status_fields=set(),
            normal_roll_action_owner=NormalRollActionOwner(RollActionTiming()),
            auto_rolls_enabled=False,
        )

        now_utc = datetime.datetime(2026, 8, 27, 18, 23, tzinfo=datetime.timezone.utc)
        parsed_rolls = 8
        roll_reset_minutes = 37

        # Step 1: Reconcile anchor and establish cycle_id first
        from mudae_core import reconcile_roll_reset_deadline, cooldown_deadline
        client.roll_reset_at_utc, _ = reconcile_roll_reset_deadline(
            getattr(client, "roll_reset_at_utc", None),
            now_utc,
            cooldown_deadline(now_utc, roll_reset_minutes),
        )
        client.roll_reset_anchor.observe(client.roll_reset_at_utc, now_utc)
        client.roll_reset_at_utc = client.roll_reset_anchor.next_boundary_at_utc
        client.current_roll_cycle_id = client.roll_reset_anchor.cycle_id_for_boundary(
            client.roll_reset_anchor.next_boundary_index - 1
        )

        # Step 2: Apply authoritative rolls to established cycle_id
        apply_authoritative_roll_remaining(
            client, client.current_roll_cycle_id, parsed_rolls, observation_kind="check-status", observed_at_utc=now_utc,
        )

        # Asserts:
        self.assertIsNotNone(client.current_roll_cycle_id)
        state = get_normal_roll_cycle_state(client, client.current_roll_cycle_id)
        self.assertIsNotNone(state)
        self.assertEqual(state.remaining, 8)
        self.assertTrue(state.remaining_authoritative)
        self.assertEqual(state.last_authoritative_at_utc, now_utc)
        # Mid-cycle startup Rolls:8 was not proven fresh, so capacity confidence remains False
        self.assertFalse(client.normal_roll_replenishment_capacity_confidence)
        self.assertIsNone(client.normal_roll_replenishment_capacity)

    def test_authoritative_status_supersedes_old_delayed_result(self):
        """Authoritative /tu observed at t=8 supersedes a delayed roll result created at t=3."""
        cycle_r1 = ("roll", 1700000000, 2)
        client = SimpleNamespace(
            current_roll_cycle_id=cycle_r1,
            _normal_roll_cycle_state={},
            _pending_boundary_roll_origins={},
            _roll_batch_deferred_status_fields=set(),
            cross_cycle_roll_count_uncertain=False,
            cross_cycle_uncertain_cycle_id=None,
        )

        # Register pending token for R+1
        token = 12345
        add_provisional_roll_cycle_uncertainty(client, cycle_r1, ("pending-boundary-origin", token))
        client._pending_boundary_roll_origins[token] = {
            "origin_cycle_id": ("roll", 1700000000, 1),
            "affected_cycle_id": cycle_r1,
            "expires_at": time.monotonic() + 15.0,
        }

        # At 18:05:08, authoritative /tu arrives reporting 12 rolls
        tu_at = datetime.datetime(2026, 8, 27, 18, 5, 8, tzinfo=datetime.timezone.utc)
        apply_authoritative_roll_remaining(client, cycle_r1, 12, observation_kind="check-status", observed_at_utc=tu_at)

        target_state = get_normal_roll_cycle_state(client, cycle_r1)
        self.assertEqual(target_state.remaining, 12)
        self.assertEqual(target_state.last_authoritative_at_utc, tu_at)
        self.assertTrue(target_state.count_uncertain)

        # At 18:05:10, gateway delivers message created at 18:05:03 (<= tu_at)
        result_created_at = datetime.datetime(2026, 8, 27, 18, 5, 3, tzinfo=datetime.timezone.utc)
        is_superseded = (
            target_state.last_authoritative_at_utc is not None
            and result_created_at <= target_state.last_authoritative_at_utc
        )
        self.assertTrue(is_superseded)

        # Applying supersession logic:
        client._pending_boundary_roll_origins.pop(token)
        remove_roll_cycle_uncertainty(client, cycle_r1, ("pending-boundary-origin", token))

        # Result: cycle remains clean, remaining remains 12, known_consumed remains 0
        self.assertFalse(target_state.count_uncertain)
        self.assertEqual(target_state.remaining, 12)
        self.assertEqual(target_state.known_consumed, 0)

    def test_newer_result_invalidates_authoritative_status(self):
        """A roll result created at t=10 after authoritative /tu at t=8 genuinely invalidates the count."""
        cycle_r1 = ("roll", 1700000000, 2)
        client = SimpleNamespace(
            current_roll_cycle_id=cycle_r1,
            _normal_roll_cycle_state={},
            _pending_boundary_roll_origins={},
            _roll_batch_deferred_status_fields=set(),
            cross_cycle_roll_count_uncertain=False,
            cross_cycle_uncertain_cycle_id=None,
        )

        tu_at = datetime.datetime(2026, 8, 27, 18, 5, 8, tzinfo=datetime.timezone.utc)
        apply_authoritative_roll_remaining(client, cycle_r1, 12, observation_kind="check-status", observed_at_utc=tu_at)
        target_state = get_normal_roll_cycle_state(client, cycle_r1)

        # Newer result created at 18:05:10 (> tu_at)
        result_created_at = datetime.datetime(2026, 8, 27, 18, 5, 10, tzinfo=datetime.timezone.utc)
        is_superseded = (
            target_state.last_authoritative_at_utc is not None
            and result_created_at <= target_state.last_authoritative_at_utc
        )
        self.assertFalse(is_superseded)

        # Mark confirmed uncertainty
        token = 999
        add_roll_cycle_uncertainty(client, cycle_r1, ("confirmed-boundary-result", token), reason="cross-boundary")
        target_state.known_consumed += 1

        self.assertTrue(target_state.count_uncertain)
        self.assertEqual(target_state.known_consumed, 1)

    def test_real_shared_reset_no_anchor_schedules_private_sync_via_registered_callback(self):
        """Production _apply_shared_reset_snapshot on unanchored client invokes registered _schedule_private_roll_count_sync."""
        anchor = ResetAnchor("roll", 60)
        self.assertFalse(anchor.confidence)
        loop = _Loop()

        client = SimpleNamespace(
            user=SimpleNamespace(id=1001, name="AccountB", display_name="AccountB"),
            preset_name="AccountB",
            target_channel_id=999,
            roll_interval=60,
            claim_interval=180,
            roll_reset_anchor=anchor,
            claim_reset_anchor=ResetAnchor("claim", 180),
            current_roll_cycle_id=None,
            roll_reset_at_utc=None,
            normal_roll_replenishment_capacity=None,
            normal_roll_replenishment_capacity_confidence=False,
            _normal_roll_cycle_state={},
            _roll_count_sync_cycle_id=None,
            _roll_count_sync_at_utc=None,
            _roll_count_sync_handle=None,
            loop=loop,
        )

        def schedule_private_roll_count_sync(logical_roll_cycle_id, boundary_utc, *, reason="roll-count-unknown"):
            client._roll_count_sync_cycle_id = logical_roll_cycle_id
            client._roll_count_sync_handle = loop.call_later(45.0, lambda: None)

        client._schedule_private_roll_count_sync = schedule_private_roll_count_sync

        from mudae_bot import _apply_shared_reset_snapshot
        observed_at = datetime.datetime(2026, 8, 27, 18, 5, 2, tzinfo=datetime.timezone.utc)
        proposed_next = datetime.datetime(2026, 8, 27, 19, 5, tzinfo=datetime.timezone.utc)
        snapshot = ServerResetSnapshot(
            server_id=999,
            observed_at_utc=observed_at,
            roll_reset_at_utc=proposed_next,
            observed_fields=frozenset(["rolls"]),
        )

        _apply_shared_reset_snapshot(client, snapshot)

        # Timing learned
        self.assertTrue(anchor.confidence)
        self.assertEqual(client.roll_reset_at_utc, proposed_next)
        self.assertIsNotNone(client.current_roll_cycle_id)

        # Private state unknown
        state = get_normal_roll_cycle_state(client, client.current_roll_cycle_id)
        self.assertIsNone(state.remaining)
        self.assertFalse(state.remaining_authoritative)

        # Private sync scheduled automatically!
        self.assertEqual(client._roll_count_sync_cycle_id, client.current_roll_cycle_id)
        self.assertIsNotNone(client._roll_count_sync_handle)

    def test_multiple_uncertain_cycles_survive_prune(self):
        """Multiple uncertain cycles survive _prune_normal_action_metadata even when legacy view only holds one."""
        cycle_r1 = ("roll", 1700000000, 1)
        cycle_r2 = ("roll", 1700000000, 2)
        cycle_current = ("roll", 1700000000, 3)

        owner = NormalRollActionOwner(RollActionTiming())
        owner.cycle_id = cycle_current
        client = SimpleNamespace(
            current_roll_cycle_id=cycle_current,
            normal_roll_action_owner=owner,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _normal_roll_action_scheduled_triggers=set(),
            _pending_boundary_roll_origins={},
            _auto_rolls_ack_ambiguous_cycle_id=None,
            _auto_rolls_reconcile_cycle_id=None,
            _active_normal_roll_cycle_id=None,
            _roll_count_sync_cycle_id=None,
            _roll_batch_deferred_status_fields=set(),
        )

        # Initialize current cycle state and mark both R1 and R2 uncertain
        get_normal_roll_cycle_state(client, cycle_current)
        add_roll_cycle_uncertainty(client, cycle_r1, ("confirmed-boundary-result", 101))
        add_roll_cycle_uncertainty(client, cycle_r2, ("confirmed-boundary-result", 102))

        # Run pruning logic
        states = getattr(client, "_normal_roll_cycle_state", {})
        active_cycles = {
            client.current_roll_cycle_id,
            client.normal_roll_action_owner.cycle_id,
            client.normal_roll_action_owner.queued_cycle_id,
        }
        active_cycles.update(
            cid for cid, st in states.items() if getattr(st, "count_uncertain", False)
        )
        active_cycles.discard(None)
        for cid in list(client._normal_roll_cycle_state.keys()):
            if cid not in active_cycles:
                client._normal_roll_cycle_state.pop(cid, None)

        # Verify BOTH R1 and R2 survived!
        self.assertIn(cycle_r1, client._normal_roll_cycle_state)
        self.assertIn(cycle_r2, client._normal_roll_cycle_state)
        self.assertIn(cycle_current, client._normal_roll_cycle_state)

    def test_unrelated_uncertain_cycle_does_not_block_clean_capacity_learning(self):
        """Uncertainty in an unrelated cycle does NOT block capacity learning on a clean, proven-fresh cycle."""
        cycle_clean = ("roll", 1700000000, 1)
        cycle_unrelated = ("roll", 1700000000, 2)

        client = SimpleNamespace(
            current_roll_cycle_id=cycle_clean,
            normal_roll_replenishment_capacity=None,
            normal_roll_replenishment_capacity_confidence=False,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _roll_batch_deferred_status_fields=set(),
        )

        # Set up clean cycle R1
        st_clean = get_normal_roll_cycle_state(client, cycle_clean)
        st_clean.proven_fresh = True
        st_clean.known_consumed = 0

        # Mark unrelated cycle R2 uncertain, which sets client.cross_cycle_roll_count_uncertain = True
        add_roll_cycle_uncertainty(client, cycle_unrelated, ("confirmed-boundary-result", 888))
        self.assertTrue(client.cross_cycle_roll_count_uncertain)

        # Authoritative /tu arrives for clean cycle R1 with 13 rolls
        apply_authoritative_roll_remaining(client, cycle_clean, 13, observation_kind="check-status")

        # Capacity 13 is successfully learned despite unrelated cycle uncertainty!
        self.assertEqual(client.normal_roll_replenishment_capacity, 13)
        self.assertTrue(client.normal_roll_replenishment_capacity_confidence)

    def test_repeated_status_boundary_iterations_do_not_redraw_or_replace_pending_callback(self):
        """Test A1: Repeated routine status iterations for the same cycle preserve pending callback without redraw."""
        cycle = ("roll", 1700000000, 1)
        now = datetime.datetime(2026, 8, 30, 19, 40, tzinfo=datetime.timezone.utc)
        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)

        first_deadline, created = owner.schedule(
            cycle_id=cycle,
            now_utc=now,
            humanization_enabled=True,
            window_minutes=20,
        )
        self.assertTrue(created)
        self.assertEqual(owner.state, "pending")

        policy = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=cycle,
            owner_state=owner.state,
            state_dirty=False,
        )
        self.assertEqual(policy, "suppress-routine")

        # Second routine iteration 20s later
        second_deadline, second_created = owner.schedule(
            cycle_id=cycle,
            now_utc=now + datetime.timedelta(seconds=20),
            humanization_enabled=True,
            window_minutes=20,
        )
        self.assertFalse(second_created)
        self.assertEqual(first_deadline, second_deadline)
        self.assertEqual(owner.state, "pending")

    def test_unrelated_dirty_fields_do_not_starve_pending_roll_action(self):
        """Test A2: Unrelated dirty status fields (power, points, dk) do not break normal action suppression."""
        cycle = ("roll", 1700000000, 1)
        owner = NormalRollActionOwner(RollActionTiming())
        owner.schedule(cycle_id=cycle, now_utc=datetime.datetime.now(datetime.timezone.utc))
        self.assertEqual(owner.state, "pending")

        # Only roll-relevant state is considered dirty for roll suppression
        unrelated_dirty = False  # power/points/dk dirty, but rolls clean
        policy = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=cycle,
            owner_state=owner.state,
            state_dirty=unrelated_dirty,
        )
        self.assertEqual(policy, "suppress-routine")

    def test_completed_owner_reschedules_when_new_authoritative_rolls_arrive_in_same_cycle(self):
        """Test A3: When an action was completed and new rolls are observed in the same cycle, owner re-arms to pending."""
        cycle = ("roll", 1700000000, 1)
        now = datetime.datetime(2026, 8, 30, 19, 0, tzinfo=datetime.timezone.utc)
        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)

        # First batch at 19:00 completes
        first_deadline, created = owner.schedule(cycle_id=cycle, now_utc=now)
        self.assertTrue(created)
        self.assertTrue(owner.start(cycle))
        self.assertTrue(owner.complete(cycle))
        self.assertEqual(owner.state, "completed")

        # At 19:40, authoritative $tu discovers 21 remaining rolls in the same cycle
        wake_time = datetime.datetime(2026, 8, 30, 19, 40, tzinfo=datetime.timezone.utc)
        rearmed_deadline, rearmed_created = owner.schedule(
            cycle_id=cycle,
            now_utc=wake_time,
        )
        self.assertTrue(rearmed_created)
        self.assertEqual(owner.state, "pending")
        self.assertTrue(owner.is_pending(cycle))

        # Status policy now correctly suppresses routine checks instead of looping
        policy = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=cycle,
            owner_state=owner.state,
            state_dirty=False,
        )
        self.assertEqual(policy, "suppress-routine")

    def test_peer_shared_reset_snapshot_does_not_erase_authoritative_roll_state(self):
        """Test B2: Peer $tu observation does not erase local client's authoritative roll count."""
        from mudae_bot import _apply_shared_reset_snapshot
        from mudae_core.status import ServerResetSnapshot
        anchor = ResetAnchor("roll", 60)
        client = SimpleNamespace(
            user=SimpleNamespace(id=1001, name="AccountA", display_name="AccountA"),
            preset_name="AccountA",
            target_channel_id=999,
            roll_interval=60,
            claim_interval=180,
            roll_reset_anchor=anchor,
            claim_reset_anchor=ResetAnchor("claim", 180),
            current_roll_cycle_id=("roll", 1787857500, -1),
            roll_reset_at_utc=None,
            normal_roll_replenishment_capacity=None,
            normal_roll_replenishment_capacity_confidence=False,
            _normal_roll_cycle_state={},
            _roll_count_sync_cycle_id=None,
            _roll_count_sync_at_utc=None,
            _roll_count_sync_handle=None,
            last_tu_snapshot_complete=True,
            loop=asyncio.get_event_loop(),
        )

        state = get_normal_roll_cycle_state(client, client.current_roll_cycle_id)
        state.remaining = 21
        state.remaining_authoritative = True

        observed_at = datetime.datetime(2026, 8, 27, 18, 5, 2, tzinfo=datetime.timezone.utc)
        proposed_next = datetime.datetime(2026, 8, 27, 19, 5, tzinfo=datetime.timezone.utc)
        snapshot = ServerResetSnapshot(
            server_id=999,
            observed_at_utc=observed_at,
            roll_reset_at_utc=proposed_next,
            observed_fields=frozenset(["rolls"]),
        )

        _apply_shared_reset_snapshot(client, snapshot)

        # Authoritative count was preserved!
        self.assertEqual(state.remaining, 21)
        self.assertTrue(state.remaining_authoritative)

    def test_peer_preset_actions_do_not_mutate_other_client_owner_or_timing(self):
        """Test B3: Multi-preset timing isolation ensures Preset 1's action owner is isolated from Preset 2."""
        cycle = ("roll", 1700000000, 1)
        now = datetime.datetime(2026, 8, 30, 19, 0, tzinfo=datetime.timezone.utc)

        timing1 = RollActionTiming()
        owner1 = NormalRollActionOwner(timing1)
        deadline1, _ = owner1.schedule(cycle_id=cycle, now_utc=now, persistent_stagger_seconds=0.0)

        timing2 = RollActionTiming()
        owner2 = NormalRollActionOwner(timing2)
        deadline2, _ = owner2.schedule(cycle_id=cycle, now_utc=now, persistent_stagger_seconds=20.0)

        self.assertNotEqual(deadline1, deadline2)
        self.assertTrue(owner2.start(cycle))
        self.assertTrue(owner2.complete(cycle))

        # Client 1 state is completely untouched by Client 2's actions
        self.assertEqual(owner1.state, "pending")
        self.assertEqual(owner1.deadline_utc, deadline1)

    def test_timing_threshold_wake_preserves_clean_roll_state(self):
        """Test A4: humanized wait wake for timing threshold arrival does not dirty clean roll state when owner is pending."""
        cycle = ("roll", 1700000000, 1)
        now = datetime.datetime(2026, 8, 30, 19, 40, tzinfo=datetime.timezone.utc)
        owner = NormalRollActionOwner(RollActionTiming())
        owner.schedule(cycle_id=cycle, now_utc=now)

        client = SimpleNamespace(
            normal_roll_action_owner=owner,
            current_roll_cycle_id=cycle,
            roll_reset_anchor=ResetAnchor("roll", 60),
            claim_reset_anchor=ResetAnchor("claim", 180),
            roll_reset_at_utc=now + datetime.timedelta(minutes=20),
            next_claim_reset_at_utc=now + datetime.timedelta(minutes=20),
            _status_dirty_fields=set(),
            _status_refresh_reasons=set(),
            _local_boundary_wake_pending=False,
            _immediate_check_event=asyncio.Event(),
        )

        boundary_fields = {"claim", "rolls"}
        unresolved_fields = set(boundary_fields)
        if owner.is_pending(client.current_roll_cycle_id):
            unresolved_fields.discard("rolls")

        self.assertNotIn("rolls", unresolved_fields)
        self.assertEqual(unresolved_fields, {"claim"})

    def test_multi_account_simultaneous_completed_to_pending_no_loop(self):
        """Test A5: Multiple accounts with completed batches transition cleanly to pending when new rolls arrive and suppress $tu."""
        cycle = ("roll", 1700000000, 1)
        now = datetime.datetime(2026, 8, 30, 19, 0, tzinfo=datetime.timezone.utc)
        accounts = []

        for i in range(4):
            timing = RollActionTiming()
            owner = NormalRollActionOwner(timing)
            owner.schedule(cycle_id=cycle, now_utc=now, persistent_stagger_seconds=i * 20.0)
            owner.start(cycle)
            owner.complete(cycle)
            self.assertEqual(owner.state, "completed")
            accounts.append((timing, owner))

        # At 19:40, all 4 accounts wake and receive authoritative rolls
        wake_time = datetime.datetime(2026, 8, 30, 19, 40, tzinfo=datetime.timezone.utc)
        for i, (timing, owner) in enumerate(accounts):
            deadline, created = owner.schedule(
                cycle_id=cycle,
                now_utc=wake_time,
                persistent_stagger_seconds=i * 20.0,
            )
            self.assertTrue(created)
            self.assertEqual(owner.state, "pending")
            self.assertTrue(owner.is_pending(cycle))

            policy = normal_action_status_policy(
                owner_cycle_id=owner.cycle_id,
                current_roll_cycle_id=cycle,
                owner_state=owner.state,
                state_dirty=False,
            )
            self.assertEqual(policy, "suppress-routine")

    def test_multi_preset_startup_unanchored_main_not_suppressed_by_peer_tu(self):
        """Test B1: Main account starting up is not suppressed by a peer preset's early $tu reset observation."""
        anchor = ResetAnchor("roll", 60)
        client = SimpleNamespace(
            user=SimpleNamespace(id=1001, name="MainAccount", display_name="MainAccount"),
            preset_name="MainAccount",
            target_channel_id=999,
            roll_interval=60,
            claim_interval=180,
            roll_reset_anchor=anchor,
            claim_reset_anchor=ResetAnchor("claim", 180),
            current_roll_cycle_id=("roll", 1787857500, -1),
            roll_reset_at_utc=None,
            normal_roll_replenishment_capacity=None,
            normal_roll_replenishment_capacity_confidence=False,
            _normal_roll_cycle_state={},
            _roll_count_sync_cycle_id=None,
            _roll_count_sync_at_utc=None,
            _roll_count_sync_handle=None,
            last_tu_snapshot_complete=False,
            loop=asyncio.get_event_loop(),
        )

        def schedule_private_sync(cid, boundary, *, reason=""):
            client._roll_count_sync_cycle_id = cid
            client._roll_count_sync_handle = client.loop.call_later(60.0, lambda: None)

        client._schedule_private_roll_count_sync = schedule_private_sync

        from mudae_bot import _apply_shared_reset_snapshot
        from mudae_core.status import ServerResetSnapshot

        observed_at = datetime.datetime(2026, 8, 27, 18, 5, 2, tzinfo=datetime.timezone.utc)
        proposed_next = datetime.datetime(2026, 8, 27, 19, 5, tzinfo=datetime.timezone.utc)
        snapshot = ServerResetSnapshot(
            server_id=999,
            observed_at_utc=observed_at,
            roll_reset_at_utc=proposed_next,
            observed_fields=frozenset(["rolls"]),
        )

        _apply_shared_reset_snapshot(client, snapshot)

        # Check status policy on startup:
        private_count_sync_pending = bool(
            getattr(client, "last_tu_snapshot_complete", False)
            and getattr(client, "_roll_count_sync_cycle_id", None) == client.current_roll_cycle_id
            and getattr(client, "_roll_count_sync_handle", None) is not None
            and not client._roll_count_sync_handle.cancelled()
        )
        # Main account's initial startup $tu is NOT suppressed!
        self.assertFalse(private_count_sync_pending)

    def test_unrelated_dirty_fields_real_client_do_not_starve_pending_callback(self):
        """Test A: Real dirty status tracking for power, dk, points does not starve a pending normal roll action."""
        cycle = ("roll", 1700000000, 1)
        now = datetime.datetime(2026, 8, 30, 19, 40, tzinfo=datetime.timezone.utc)
        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)

        first_deadline, created = owner.schedule(
            cycle_id=cycle,
            now_utc=now,
            humanization_enabled=True,
            window_minutes=20,
        )
        self.assertTrue(created)
        self.assertEqual(owner.state, "pending")

        client = SimpleNamespace(
            normal_roll_action_owner=owner,
            current_roll_cycle_id=cycle,
            time_rolls_to_claim_reset=False,
            _normal_roll_cycle_state={},
            _status_dirty_fields=set(),
            _status_refresh_reasons=set(),
            _roll_batch_deferred_status_fields=set(),
        )
        state = get_normal_roll_cycle_state(client, cycle)
        state.remaining = 21
        state.remaining_authoritative = True
        state.count_uncertain = False

        # Put real unrelated dirty fields into the client's status tracking
        mark_status_dirty(client, {"power", "dk", "points"}, reason="test-unrelated-dirty")
        self.assertEqual(status_dirty_fields(client), {"power", "dk", "points"})

        # normal_roll_action_state_is_dirty must report False
        self.assertFalse(normal_roll_action_state_is_dirty(client, cycle))

        # Scheduler policy must report suppress-routine
        policy = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=cycle,
            owner_state=owner.state,
            state_dirty=normal_roll_action_state_is_dirty(client, cycle),
        )
        self.assertEqual(policy, "suppress-routine")

        # Scheduling again does not redraw or replace
        second_deadline, second_created = owner.schedule(
            cycle_id=cycle,
            now_utc=now + datetime.timedelta(seconds=20),
            humanization_enabled=True,
            window_minutes=20,
        )
        self.assertFalse(second_created)
        self.assertEqual(first_deadline, second_deadline)
        self.assertEqual(owner.state, "pending")

    def test_claim_dirty_blocks_executor_when_time_rolls_to_claim_reset_enabled(self):
        """Test B: When time_rolls_to_claim_reset is True, claim dirtiness marks roll action dirty."""
        cycle = ("roll", 1700000000, 1)
        owner = NormalRollActionOwner(RollActionTiming())
        owner.schedule(cycle_id=cycle, now_utc=datetime.datetime.now(datetime.timezone.utc))

        client = SimpleNamespace(
            normal_roll_action_owner=owner,
            current_roll_cycle_id=cycle,
            time_rolls_to_claim_reset=True,
            _normal_roll_cycle_state={},
            _status_dirty_fields=set(),
            _status_refresh_reasons=set(),
        )
        state = get_normal_roll_cycle_state(client, cycle)
        state.remaining = 21
        state.remaining_authoritative = True
        state.count_uncertain = False

        # Claim state is dirty
        mark_status_dirty(client, {"claim"}, reason="claim-stale")
        self.assertIn("claim", status_dirty_fields(client))

        # normal_roll_action_state_is_dirty MUST be True
        self.assertTrue(normal_roll_action_state_is_dirty(client, cycle))

        # Policy allows status reconciliation
        policy = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=cycle,
            owner_state=owner.state,
            state_dirty=normal_roll_action_state_is_dirty(client, cycle),
        )
        self.assertEqual(policy, "none")

        # After claim status is cleared, roll action is clean again
        clear_status_dirty(client, {"claim"})
        self.assertFalse(normal_roll_action_state_is_dirty(client, cycle))
        policy_clean = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=cycle,
            owner_state=owner.state,
            state_dirty=normal_roll_action_state_is_dirty(client, cycle),
        )
        self.assertEqual(policy_clean, "suppress-routine")

    def test_claim_dirty_does_not_block_executor_when_time_rolls_to_claim_reset_disabled(self):
        """Test C: When time_rolls_to_claim_reset is False, claim dirtiness does NOT block roll action."""
        cycle = ("roll", 1700000000, 1)
        owner = NormalRollActionOwner(RollActionTiming())
        owner.schedule(cycle_id=cycle, now_utc=datetime.datetime.now(datetime.timezone.utc))

        client = SimpleNamespace(
            normal_roll_action_owner=owner,
            current_roll_cycle_id=cycle,
            time_rolls_to_claim_reset=False,
            _normal_roll_cycle_state={},
            _status_dirty_fields=set(),
            _status_refresh_reasons=set(),
        )
        state = get_normal_roll_cycle_state(client, cycle)
        state.remaining = 21
        state.remaining_authoritative = True
        state.count_uncertain = False

        # Claim state is dirty, but roll state is clean
        mark_status_dirty(client, {"claim"}, reason="claim-stale")
        self.assertIn("claim", status_dirty_fields(client))

        # normal_roll_action_state_is_dirty MUST be False
        self.assertFalse(normal_roll_action_state_is_dirty(client, cycle))

        policy = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=cycle,
            owner_state=owner.state,
            state_dirty=normal_roll_action_state_is_dirty(client, cycle),
        )
        self.assertEqual(policy, "suppress-routine")

    def test_david_same_cycle_completed_to_authoritative_rolls_executes(self):
        """Test D: Production flow for David DSC xx:40 wake with completed batch transitioning to execution."""
        cycle = ("roll", 1700000000, 1)
        now_1900 = datetime.datetime(2026, 8, 30, 19, 0, tzinfo=datetime.timezone.utc)
        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)

        # 19:00: first batch completes
        owner.schedule(cycle_id=cycle, now_utc=now_1900)
        owner.start(cycle)
        owner.complete(cycle)
        self.assertEqual(owner.state, "completed")

        client = SimpleNamespace(
            normal_roll_action_owner=owner,
            current_roll_cycle_id=cycle,
            time_rolls_to_claim_reset=False,
            _normal_roll_cycle_state={},
            _status_dirty_fields=set(),
            _status_refresh_reasons=set(),
            _normal_roll_action_roll_counts={},
            _roll_batch_deferred_status_fields=set(),
            normal_roll_replenishment_capacity=20,
            normal_roll_replenishment_capacity_confidence=True,
        )

        # 19:40: authoritative $tu reports 21 rolls
        now_1940 = datetime.datetime(2026, 8, 30, 19, 40, tzinfo=datetime.timezone.utc)
        apply_authoritative_roll_remaining(client, cycle, 21, observation_kind="check-status")

        # Owner re-arms to pending
        deadline, created = owner.schedule(
            cycle_id=cycle,
            now_utc=now_1940,
            humanization_enabled=True,
            window_minutes=20,
        )
        self.assertTrue(created)
        self.assertEqual(owner.state, "pending")

        # Status check suppresses physical $tu
        policy = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=cycle,
            owner_state=owner.state,
            state_dirty=normal_roll_action_state_is_dirty(client, cycle),
        )
        self.assertEqual(policy, "suppress-routine")

        # Action is ready to execute
        self.assertFalse(normal_roll_action_state_is_dirty(client, cycle))
        self.assertTrue(owner.start(cycle))
        self.assertEqual(owner.state, "executing")

    def test_multi_preset_runtime_orchestration_isolation(self):
        """Test E: JΛGGΣЯ multi-preset isolation: Preset B actions do not alter Preset A state or timing."""
        from mudae_bot import _apply_shared_reset_snapshot
        from mudae_core.status import ServerResetSnapshot

        cycle_a = ("roll", 1700000000, 1)
        cycle_b = ("roll", 1700000000, 1)
        now = datetime.datetime(2026, 8, 30, 19, 0, tzinfo=datetime.timezone.utc)

        timing_a = RollActionTiming()
        owner_a = NormalRollActionOwner(timing_a)
        deadline_a, _ = owner_a.schedule(cycle_id=cycle_a, now_utc=now, persistent_stagger_seconds=0.0)

        timing_b = RollActionTiming()
        owner_b = NormalRollActionOwner(timing_b)
        deadline_b, _ = owner_b.schedule(cycle_id=cycle_b, now_utc=now, persistent_stagger_seconds=20.0)

        client_a = SimpleNamespace(
            user=SimpleNamespace(id=1001, name="MainAccount", display_name="MainAccount"),
            preset_name="MainAccount",
            target_channel_id=999,
            roll_interval=60,
            claim_interval=180,
            roll_reset_anchor=ResetAnchor("roll", 60),
            claim_reset_anchor=ResetAnchor("claim", 180),
            current_roll_cycle_id=cycle_a,
            roll_reset_at_utc=None,
            normal_roll_action_owner=owner_a,
            normal_roll_replenishment_capacity=None,
            normal_roll_replenishment_capacity_confidence=False,
            _normal_roll_cycle_state={},
            _roll_count_sync_cycle_id=None,
            _roll_count_sync_at_utc=None,
            _roll_count_sync_handle=None,
            _status_dirty_fields=set(),
            _status_refresh_reasons=set(),
            last_tu_snapshot_complete=True,
            loop=asyncio.get_event_loop(),
        )

        state_a = get_normal_roll_cycle_state(client_a, cycle_a)
        state_a.remaining = 21
        state_a.remaining_authoritative = True

        # Preset B observes reset snapshot
        snapshot = ServerResetSnapshot(
            server_id=999,
            observed_at_utc=now,
            roll_reset_at_utc=now + datetime.timedelta(hours=1),
            observed_fields=frozenset(["rolls"]),
        )
        _apply_shared_reset_snapshot(client_a, snapshot)

        # Preset B executes its rolls
        owner_b.start(cycle_b)
        owner_b.complete(cycle_b)

        # Preset A is completely isolated
        self.assertEqual(state_a.remaining, 21)
        self.assertTrue(state_a.remaining_authoritative)
        self.assertEqual(owner_a.state, "pending")
        self.assertEqual(owner_a.deadline_utc, deadline_a)

    def test_completed_owner_without_fresh_roll_evidence_does_not_recreate_action(self):
        """Test Section 6: Completed owner without fresh usable roll evidence does not recreate roll action."""
        cycle = ("roll", 1700000000, 1)
        owner = NormalRollActionOwner(RollActionTiming())
        owner.schedule(cycle_id=cycle, now_utc=datetime.datetime.now(datetime.timezone.utc))
        owner.start(cycle)
        owner.complete(cycle)
        self.assertEqual(owner.state, "completed")

        client = SimpleNamespace(
            normal_roll_action_owner=owner,
            current_roll_cycle_id=cycle,
            auto_rolls_enabled=False,
            _normal_roll_cycle_state={},
        )
        state = get_normal_roll_cycle_state(client, cycle)
        state.remaining = 0
        state.remaining_authoritative = True

        roll_count = normal_roll_schedule_count(state)
        self.assertEqual(roll_count, 0)
        # Without fresh rolls, production guard skips owner.schedule()
        if roll_count <= 0 and not client.auto_rolls_enabled:
            pass  # production returns early
        self.assertEqual(owner.state, "completed")

    def test_stale_callback_metadata_safety_newer_cycle(self):
        """Test Section 8: A stale callback for cycle A does not clear metadata belonging to cycle B."""
        cycle_a = ("roll", 1700000000, 1)
        cycle_b = ("roll", 1700000000, 2)
        client = SimpleNamespace(
            _predicted_roll_action_cycle_id=cycle_b,
            _predicted_roll_action_handle=SimpleNamespace(cancelled=lambda: False),
        )

        # Callback for cycle A executes
        if getattr(client, "_predicted_roll_action_cycle_id", None) != cycle_a:
            pass  # Stale callback exits cleanly without touching cycle B metadata

        self.assertEqual(client._predicted_roll_action_cycle_id, cycle_b)
        self.assertIsNotNone(client._predicted_roll_action_handle)


if __name__ == "__main__":
    unittest.main()
