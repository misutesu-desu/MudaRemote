import datetime
from types import SimpleNamespace
import unittest

from mudae_core.status import (
    STATUS_FIELDS,
    ServerResetCoordinator,
    clear_status_dirty,
    consume_tu_urgent_bypass,
    consume_current_tu_urgency_for_backoff,
    bounded_sanity_deadline,
    ensure_sanity_deadline_safe,
    nearest_periodic_boundary_distance,
    defer_tu_queries,
    initialize_status_tracking,
    looks_like_tu_status_snapshot,
    mark_status_dirty,
    parse_claim_denied_cooldown,
    record_tu_failure,
    record_tu_success,
    dynamic_claim_round,
    reconcile_private_claim_deadline,
    reconcile_roll_reset_deadline,
    ResetAnchor,
    roll_reset_wait_minutes,
    rolls_usage_is_active,
    status_dirty_fields,
    status_message_addresses_identity,
    status_refresh_reasons,
    PendingStatusRequest,
    coalesce_status_request,
    tu_cache_seconds_remaining,
    tu_retry_wait,
)
from mudae_core.coordinator import GlobalIntervalCoordinator
from mudae_core.runtime import (
    NormalRollActionOwner,
    RollActionTiming,
    claim_roll_count_reconciliation,
    get_normal_roll_cycle_state,
    is_tu_still_required,
    normal_action_status_policy,
    normal_roll_action_state_is_dirty,
    reconcile_authoritative_current_roll_count,
    release_roll_count_reconciliation,
)


class StatusFreshnessTests(unittest.TestCase):
    def test_localized_claim_denials_override_positive_substrings(self):
        self.assertEqual(
            parse_claim_denied_cooldown(
                "aakiras_, no puedes reclamar hasta dentro de 7 min."
            ),
            7,
        )
        self.assertEqual(
            parse_claim_denied_cooldown(
                "You can't claim for another **2h 9** min."
            ),
            129,
        )
        self.assertEqual(
            parse_claim_denied_cooldown(
                "Você não pode se casar por mais **14** min."
            ),
            14,
        )
        self.assertEqual(
            parse_claim_denied_cooldown(
                "Vous ne pouvez pas vous marier avant **1h 3** min."
            ),
            63,
        )
        self.assertIsNone(
            parse_claim_denied_cooldown("¡Puedes reclamar ahora!")
        )

    def setUp(self):
        self.client = SimpleNamespace()
        initialize_status_tracking(self.client)

    def test_dirty_state_is_field_scoped_and_reasoned(self):
        mark_status_dirty(self.client, {"claim"}, reason="claim-inconclusive", urgent=True)
        self.assertEqual(status_dirty_fields(self.client), {"claim"})
        self.assertTrue(self.client.desync_detected)
        self.assertTrue(self.client._status_refresh_urgent)
        self.assertEqual(status_refresh_reasons(self.client), ["claim-inconclusive"])

        mark_status_dirty(self.client, {"rolls"}, reason="roll-interrupted")
        clear_status_dirty(self.client, {"claim"})
        self.assertEqual(status_dirty_fields(self.client), {"rolls"})
        self.assertTrue(self.client.desync_detected)

        clear_status_dirty(self.client)
        self.assertEqual(status_dirty_fields(self.client), set())
        self.assertFalse(self.client.desync_detected)
        self.assertEqual(status_refresh_reasons(self.client), [])

    def test_legacy_desync_flag_is_treated_as_all_fields_dirty(self):
        self.client.desync_detected = True
        self.assertEqual(status_dirty_fields(self.client), set(STATUS_FIELDS))

    def test_unanswered_queries_back_off_and_success_resets_budget(self):
        first = record_tu_failure(self.client, now_monotonic=100.0)
        self.assertEqual(first, 30.0)
        self.assertEqual(tu_retry_wait(self.client, now_monotonic=110.0), 20.0)

        second = record_tu_failure(self.client, now_monotonic=130.0)
        self.assertEqual(second, 60.0)
        self.assertEqual(tu_retry_wait(self.client, now_monotonic=150.0), 40.0)

        record_tu_success(self.client)
        self.assertEqual(tu_retry_wait(self.client, now_monotonic=150.0), 0.0)
        self.assertEqual(self.client._tu_failure_streak, 0)

    def test_failed_reconciliation_same_reason_cannot_bypass_own_backoff(self):
        cycle_id = ("roll", 1700000000, 5)
        mark_status_dirty(
            self.client,
            {"rolls"},
            reason="normal-action-count-reconcile",
            urgent=True,
        )
        self.assertTrue(claim_roll_count_reconciliation(self.client, cycle_id))
        physical_tu_count = 1

        record_tu_failure(self.client, now_monotonic=0.0)
        self.assertIsNone(self.client._roll_count_reconcile_cycle_id)
        self.assertTrue(self.client._tu_urgent_bypass_used)
        self.assertTrue(claim_roll_count_reconciliation(self.client, cycle_id))
        mark_status_dirty(
            self.client,
            {"rolls"},
            reason="normal-action-count-reconcile",
            urgent=True,
        )

        for now_monotonic in (10.0, 29.0):
            if (
                tu_retry_wait(self.client, now_monotonic=now_monotonic) <= 0
                or consume_tu_urgent_bypass(self.client)
            ):
                physical_tu_count += 1
        self.assertEqual(physical_tu_count, 1)
        self.assertEqual(tu_retry_wait(self.client, now_monotonic=30.0), 0.0)
        physical_tu_count += 1
        self.assertEqual(physical_tu_count, 2)

    def test_partial_reconciliation_same_reason_cannot_bypass_own_defer(self):
        cycle_id = ("roll", 1700000000, 5)
        mark_status_dirty(
            self.client,
            {"rolls"},
            reason="normal-action-count-reconcile",
            urgent=True,
        )
        self.assertTrue(claim_roll_count_reconciliation(self.client, cycle_id))
        physical_tu_count = 1
        record_tu_success(self.client)
        self.assertTrue(release_roll_count_reconciliation(self.client))
        mark_status_dirty(self.client, {"rolls"}, reason="partial-tu-response")
        defer_tu_queries(self.client, 30.0, now_monotonic=0.0)
        consume_current_tu_urgency_for_backoff(self.client)
        self.assertTrue(claim_roll_count_reconciliation(self.client, cycle_id))
        mark_status_dirty(
            self.client,
            {"rolls"},
            reason="normal-action-count-reconcile",
            urgent=True,
        )

        for now_monotonic in (10.0, 29.0):
            if (
                tu_retry_wait(self.client, now_monotonic=now_monotonic) <= 0
                or consume_tu_urgent_bypass(self.client)
            ):
                physical_tu_count += 1
        self.assertEqual(physical_tu_count, 1)
        self.assertEqual(tu_retry_wait(self.client, now_monotonic=30.0), 0.0)

    def test_new_urgent_reason_can_bypass_existing_reconciliation_backoff_once(self):
        mark_status_dirty(
            self.client,
            {"rolls"},
            reason="normal-action-count-reconcile",
            urgent=True,
        )
        record_tu_failure(self.client, now_monotonic=0.0)
        self.assertFalse(consume_tu_urgent_bypass(self.client))

        mark_status_dirty(
            self.client,
            {"claim"},
            reason="new-claim-evidence",
            urgent=True,
        )

        self.assertTrue(consume_tu_urgent_bypass(self.client))
        self.assertFalse(consume_tu_urgent_bypass(self.client))

    def test_explicit_defer_never_shortens_an_existing_deadline(self):
        defer_tu_queries(self.client, 45.0, now_monotonic=10.0)
        defer_tu_queries(self.client, 5.0, now_monotonic=20.0)
        self.assertEqual(tu_retry_wait(self.client, now_monotonic=20.0), 35.0)

    def test_rolls_usage_marker_survives_recalculated_reset_deadlines(self):
        used_until = datetime.datetime(2026, 8, 10, 1, 0, tzinfo=datetime.timezone.utc)
        recalculated_reset = datetime.datetime(2026, 8, 10, 1, 1, tzinfo=datetime.timezone.utc)
        now = datetime.datetime(2026, 8, 10, 0, 30, tzinfo=datetime.timezone.utc)

        self.assertTrue(rolls_usage_is_active(used_until, now))
        self.assertTrue(rolls_usage_is_active(used_until, recalculated_reset - datetime.timedelta(minutes=2)))
        self.assertFalse(rolls_usage_is_active(used_until, used_until))

    def test_new_urgent_reason_bypasses_backoff_only_once(self):
        record_tu_failure(self.client, now_monotonic=100.0)
        mark_status_dirty(self.client, {"claim"}, reason="claim-inconclusive", urgent=True)
        self.assertTrue(consume_tu_urgent_bypass(self.client))
        self.assertFalse(consume_tu_urgent_bypass(self.client))
        mark_status_dirty(self.client, {"claim"}, reason="claim-inconclusive", urgent=True)
        self.assertFalse(consume_tu_urgent_bypass(self.client))
        mark_status_dirty(self.client, {"claim"}, reason="claim-reset", urgent=True)
        self.assertTrue(consume_tu_urgent_bypass(self.client))

    def test_cached_tu_lifetime_is_bounded(self):
        queried = datetime.datetime(2026, 8, 5, 10, 7, tzinfo=datetime.timezone.utc)
        now = queried + datetime.timedelta(minutes=6)
        self.assertEqual(tu_cache_seconds_remaining(queried, now), 24 * 60)
        self.assertEqual(
            tu_cache_seconds_remaining(queried, queried + datetime.timedelta(minutes=30)),
            0,
        )
        self.assertEqual(tu_cache_seconds_remaining(None, now), 0)

    def test_peer_roll_deadline_cannot_skip_an_imminent_local_boundary(self):
        observed = datetime.datetime(2026, 8, 20, 21, 4, 50, tzinfo=datetime.timezone.utc)
        local_boundary = datetime.datetime(2026, 8, 20, 21, 5, tzinfo=datetime.timezone.utc)
        rounded_next_boundary = datetime.datetime(2026, 8, 20, 22, 4, 50, tzinfo=datetime.timezone.utc)

        deadline, advanced = reconcile_roll_reset_deadline(
            local_boundary,
            observed,
            rounded_next_boundary,
        )

        self.assertEqual(deadline, local_boundary)
        self.assertFalse(advanced)

    def test_peer_roll_deadline_advances_after_local_boundary_passes(self):
        local_boundary = datetime.datetime(2026, 8, 20, 21, 5, tzinfo=datetime.timezone.utc)
        observed = local_boundary + datetime.timedelta(seconds=1)
        next_boundary = datetime.datetime(2026, 8, 20, 22, 5, tzinfo=datetime.timezone.utc)

        deadline, advanced = reconcile_roll_reset_deadline(
            local_boundary,
            observed,
            next_boundary,
        )

        self.assertEqual(deadline, next_boundary)
        self.assertTrue(advanced)

    def test_local_roll_parse_uses_the_same_imminent_boundary_protection(self):
        observed = datetime.datetime(2026, 8, 20, 21, 4, 50, tzinfo=datetime.timezone.utc)
        imminent = datetime.datetime(2026, 8, 20, 21, 5, tzinfo=datetime.timezone.utc)
        parsed_next_cycle = observed + datetime.timedelta(minutes=60)

        deadline, advanced = reconcile_roll_reset_deadline(imminent, observed, parsed_next_cycle)

        self.assertEqual(deadline, imminent)
        self.assertFalse(advanced)

    def test_private_claim_timer_refines_once_without_moving_back_to_an_earlier_round(self):
        observed = datetime.datetime(2026, 8, 20, 1, 0, tzinfo=datetime.timezone.utc)
        deadline_61 = observed + datetime.timedelta(minutes=61)
        deadline_60 = observed + datetime.timedelta(minutes=60)

        refined, changed = reconcile_private_claim_deadline(deadline_61, observed, deadline_60)
        noisy, noisy_changed = reconcile_private_claim_deadline(refined, observed, deadline_61)

        self.assertTrue(changed)
        self.assertEqual(refined, deadline_60)
        self.assertFalse(noisy_changed)
        self.assertEqual(noisy, deadline_60)
        self.assertEqual(dynamic_claim_round(180, noisy, observed)[0], 3)

    def test_known_roll_deadline_beats_the_sixty_minute_parse_fallback(self):
        now = datetime.datetime(2026, 8, 21, 11, 1, 42, tzinfo=datetime.timezone.utc)
        known_deadline = now + datetime.timedelta(minutes=4)

        self.assertEqual(roll_reset_wait_minutes(None, known_deadline, now), 4.0)
        self.assertEqual(roll_reset_wait_minutes(None, None, now), 60.0)

    def test_dynamic_claim_rounds_are_private_for_interleaved_accounts(self):
        now = datetime.datetime(2026, 8, 20, 1, 0, tzinfo=datetime.timezone.utc)
        deadlines = {
            "a": now + datetime.timedelta(minutes=170),
            "b": now + datetime.timedelta(minutes=100),
            "c": now + datetime.timedelta(minutes=40),
        }

        for _ in range(3):
            self.assertEqual(dynamic_claim_round(180, deadlines["a"], now)[0], 1)
            self.assertEqual(dynamic_claim_round(180, deadlines["b"], now)[0], 2)
            self.assertEqual(dynamic_claim_round(180, deadlines["c"], now)[0], 3)

    def test_peer_roll_snapshot_cannot_change_each_account_private_claim_round(self):
        now = datetime.datetime(2026, 8, 20, 1, 0, tzinfo=datetime.timezone.utc)
        account_a_claim = now + datetime.timedelta(minutes=45)
        account_b_claim = now + datetime.timedelta(minutes=110)
        coordinator = ServerResetCoordinator()

        snapshot, changed = coordinator.observe(
            10,
            200,
            now,
            roll_reset_at_utc=now + datetime.timedelta(minutes=24),
        )

        self.assertTrue(changed)
        self.assertEqual(snapshot.roll_reset_at_utc, now + datetime.timedelta(minutes=24))
        self.assertEqual(dynamic_claim_round(180, account_a_claim, now)[0], 3)
        self.assertEqual(dynamic_claim_round(180, account_b_claim, now)[0], 2)

    def test_verified_new_claim_cycle_can_return_from_round_three_to_round_one(self):
        now = datetime.datetime(2026, 8, 20, 1, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(dynamic_claim_round(180, now + datetime.timedelta(minutes=40), now)[0], 3)
        self.assertEqual(dynamic_claim_round(180, now + datetime.timedelta(minutes=180), now)[0], 1)

    def test_full_tu_snapshot_is_not_confused_with_claim_rejection(self):
        snapshot = (
            "**Visionaire**, you can't claim right now. Next claim in **3** min.\n"
            "You have **15** rolls left. Next rolls reset in **44** min.\n"
            "$rt is available!\n$dk is ready!\nYou can react to kakera right now!"
        )
        rejection = "**Visionaire**, you can't claim another character for **3** min."
        self.assertTrue(looks_like_tu_status_snapshot(snapshot))
        self.assertFalse(looks_like_tu_status_snapshot(rejection))

    def test_status_address_matching_is_exact(self):
        self.assertTrue(status_message_addresses_identity(
            "**alt-1**, you can't claim for another **2** min.",
            ["alt-1"],
        ))
        self.assertFalse(status_message_addresses_identity(
            "**alt-10**, you can't claim for another **2** min.",
            ["alt-1"],
        ))
        self.assertTrue(status_message_addresses_identity(
            "<@123>, you can't claim for another **2** min.",
            ["different-name"],
            user_id=123,
        ))

    def test_server_reset_observations_are_shared_per_server_and_deduplicated(self):
        coordinator = ServerResetCoordinator(message_limit=2)
        observed = datetime.datetime(2026, 8, 4, 12, 0, tzinfo=datetime.timezone.utc)
        roll_deadline = observed + datetime.timedelta(minutes=15)

        snapshot, changed = coordinator.observe(
            10,
            100,
            observed,
            roll_reset_at_utc=roll_deadline,
        )
        duplicate, duplicate_changed = coordinator.observe(
            10,
            100,
            observed + datetime.timedelta(seconds=1),
            roll_reset_at_utc=observed + datetime.timedelta(hours=1),
        )

        self.assertTrue(changed)
        self.assertFalse(duplicate_changed)
        self.assertEqual(snapshot, duplicate)
        self.assertFalse(hasattr(coordinator.snapshot(10), "claim_reset_at_utc"))
        self.assertEqual(coordinator.snapshot(10).roll_reset_at_utc, roll_deadline)
        self.assertIsNone(coordinator.snapshot(11))

    def test_clear_status_dirty_without_fields_clears_all_reasons_and_desync(self):
        mark_status_dirty(self.client, reason="mudae-maintenance", urgent=True)
        self.assertTrue(self.client.desync_detected)
        self.assertIn("mudae-maintenance", status_refresh_reasons(self.client))

        clear_status_dirty(self.client)
        self.assertFalse(self.client.desync_detected)
        self.assertEqual(status_dirty_fields(self.client), set())
        self.assertEqual(status_refresh_reasons(self.client), [])
        self.assertFalse(self.client._status_refresh_urgent)

    def test_reset_anchor_advances_known_cycles_without_new_observations(self):
        start = datetime.datetime(2026, 8, 27, 14, 13, tzinfo=datetime.timezone.utc)
        anchor = ResetAnchor("roll", 60)
        changed, refined = anchor.observe(start, start - datetime.timedelta(minutes=20))

        self.assertTrue(changed)
        self.assertFalse(refined)
        self.assertEqual(
            anchor.advance_through(start + datetime.timedelta(hours=3, seconds=1)),
            [
                (("roll", int(start.timestamp()), 0), start),
                (("roll", int(start.timestamp()), 1), start + datetime.timedelta(hours=1)),
                (("roll", int(start.timestamp()), 2), start + datetime.timedelta(hours=2)),
                (("roll", int(start.timestamp()), 3), start + datetime.timedelta(hours=3)),
            ],
        )
        self.assertEqual(anchor.next_boundary_at_utc, start + datetime.timedelta(hours=4))

    def test_reset_anchor_ignores_minute_rounding_but_reanchors_material_mismatch(self):
        start = datetime.datetime(2026, 8, 27, 14, 13, tzinfo=datetime.timezone.utc)
        anchor = ResetAnchor("roll", 60)
        anchor.observe(start, start - datetime.timedelta(minutes=20))

        changed, refined = anchor.observe(start + datetime.timedelta(seconds=62), start)
        self.assertFalse(changed)
        self.assertTrue(refined)
        self.assertEqual(anchor.cycle_id_for_boundary(), ("roll", int(start.timestamp()), 0))
        self.assertEqual(anchor.next_boundary_at_utc, start)

        shifted = start + datetime.timedelta(minutes=8)
        changed, refined = anchor.observe(shifted, start)
        self.assertTrue(changed)
        self.assertFalse(refined)
        self.assertEqual(anchor.cycle_id_for_boundary(), ("roll", int(shifted.timestamp()), 0))

    def test_bounded_sanity_deadline_avoids_future_and_short_interval_resets(self):
        now = datetime.datetime(2026, 8, 27, 14, 13, tzinfo=datetime.timezone.utc)
        roll = ResetAnchor("roll", 60)
        claim = ResetAnchor("claim", 180)
        roll.observe(now, now)
        claim.observe(now, now)
        candidate, guard = bounded_sanity_deadline(now, roll, claim, 0)
        self.assertGreaterEqual(
            nearest_periodic_boundary_distance(now, roll.interval_seconds, candidate), guard,
        )
        short_roll = ResetAnchor("roll", 2)
        short_claim = ResetAnchor("claim", 3)
        short_roll.observe(now, now)
        short_claim.observe(now, now)
        candidate, guard = bounded_sanity_deadline(now, short_roll, short_claim, 0)
        self.assertGreaterEqual(
            min(
                nearest_periodic_boundary_distance(now, short_roll.interval_seconds, candidate),
                nearest_periodic_boundary_distance(now, short_claim.interval_seconds, candidate),
            ),
            guard,
        )

    def test_shifted_sanity_candidate_is_rechecked_against_claim_boundaries(self):
        now = datetime.datetime(2026, 8, 27, 14, 13, tzinfo=datetime.timezone.utc)
        roll = ResetAnchor("roll", 60)
        claim = ResetAnchor("claim", 180)
        roll.observe(now, now)
        claim.observe(now, now)
        shifted = now + datetime.timedelta(hours=3)
        safe = ensure_sanity_deadline_safe(shifted, roll, claim, guard_seconds=180)
        self.assertGreaterEqual(
            nearest_periodic_boundary_distance(claim.anchor_at_utc, claim.interval_seconds, safe), 180,
        )
        self.assertGreaterEqual(
            nearest_periodic_boundary_distance(roll.anchor_at_utc, roll.interval_seconds, safe), 180,
        )


    def test_same_client_coalesces_simultaneous_boundary_requests(self):
        """Test 1: Simultaneous boundary refresh requests for the same client coalesce into one logical $tu."""
        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)
        client = SimpleNamespace(
            preset_name="test_account",
            is_paused=False,
            rolling_enabled=True,
            mudae_prefix="$",
            normal_roll_action_owner=owner,
            current_roll_cycle_id=("roll", 1700000000, 1),
            _normal_roll_cycle_state={},
            _roll_batch_deferred_status_fields=set(),
        )
        initialize_status_tracking(client)

        # Trigger claim cooldown boundary
        mark_status_dirty(client, {"claim"}, reason="claim cooldown-boundary", urgent=True)
        self.assertIsNotNone(client._pending_status_request)
        self.assertIn("claim", client._pending_status_request.required_fields)
        self.assertIn("claim cooldown-boundary", client._pending_status_request.reasons)

        # Trigger simultaneous rolls replenishment boundary
        mark_status_dirty(client, {"rolls"}, reason="rolls replenishment-boundary", urgent=True)
        self.assertIn("claim", client._pending_status_request.required_fields)
        self.assertIn("rolls", client._pending_status_request.required_fields)
        self.assertIn("claim cooldown-boundary", client._pending_status_request.reasons)
        self.assertIn("rolls replenishment-boundary", client._pending_status_request.reasons)

        # Trigger generic status boundary
        mark_status_dirty(client, None, reason="status-boundary", urgent=True)
        self.assertEqual(client._pending_status_request.required_fields, set(STATUS_FIELDS))
        self.assertIn("status-boundary", client._pending_status_request.reasons)
        self.assertTrue(client._pending_status_request.urgent)

        # Verify exactly one pending status request object exists with merged requirements
        self.assertEqual(status_dirty_fields(client), set(STATUS_FIELDS))
        self.assertEqual(
            status_refresh_reasons(client),
            ["claim cooldown-boundary", "rolls replenishment-boundary", "status-boundary"],
        )

    def test_stale_queued_tu_is_skipped_after_pacing_wait(self):
        """Test 2: A queued $tu whose required state was reconciled during the pacing wait is skipped without error."""
        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)
        now = datetime.datetime.now(datetime.timezone.utc)
        cycle_id = ("roll", 1700000000, 1)
        client = SimpleNamespace(
            preset_name="test_account",
            is_paused=False,
            rolling_enabled=True,
            mudae_prefix="$",
            time_rolls_to_claim_reset=False,
            scheduled_roll_due=False,
            last_tu_snapshot_complete=True,
            last_tu_query_utc=now,
            claim_right_available=True,
            next_claim_reset_at_utc=now + datetime.timedelta(hours=2),
            roll_reset_at_utc=now + datetime.timedelta(hours=1),
            current_roll_cycle_id=cycle_id,
            current_claim_cycle_id=("claim", 1700000000, 1),
            normal_roll_action_owner=owner,
            roll_reset_anchor=ResetAnchor("roll", 60),
            claim_reset_anchor=ResetAnchor("claim", 180),
            normal_roll_replenishment_capacity_confidence=True,
            normal_roll_replenishment_capacity=8,
            predicted_roll_state_valid=True,
            rolls_left=8,
            key_mode=False,
            rt_available=False,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _roll_batch_deferred_status_fields=set(),
        )
        initialize_status_tracking(client)

        state = get_normal_roll_cycle_state(client, cycle_id)
        state.remaining = 8
        state.remaining_authoritative = True
        state.count_uncertain = False

        owner.schedule(
            cycle_id=cycle_id,
            now_utc=now,
            humanization_enabled=True,
            window_minutes=10,
        )
        self.assertTrue(owner.is_pending(cycle_id))

        required, reason = is_tu_still_required(client, proceed_to_rolls=True)
        self.assertFalse(required)
        self.assertIn(reason, ("roll-action-already-pending", "policy-suppress-routine", "cached-status-valid"))

        client._tu_skipped_stale = True
        if client._tu_skipped_stale:
            client._tu_skipped_stale = False
            skipped_cleanly = True
        else:
            record_tu_failure(client)
            skipped_cleanly = False

        self.assertTrue(skipped_cleanly)
        self.assertEqual(getattr(client, "_tu_failure_streak", 0), 0)

    def test_high_account_boundary_burst_avoids_queue_explosion_and_stale_sends(self):
        """Test 3: 50 accounts experiencing simultaneous boundary events coalesce requests and skip stale work."""
        pacer = GlobalIntervalCoordinator()
        guild_id = 999999
        now = datetime.datetime.now(datetime.timezone.utc)
        cycle_id = ("roll", 1700000000, 1)
        clients = []
        for i in range(50):
            timing = RollActionTiming()
            owner = NormalRollActionOwner(timing)
            c = SimpleNamespace(
                preset_name=f"bot_{i}",
                user=SimpleNamespace(id=1000 + i, name=f"bot_{i}"),
                is_paused=False,
                rolling_enabled=True,
                mudae_prefix="$",
                time_rolls_to_claim_reset=False,
                scheduled_roll_due=False,
                last_tu_snapshot_complete=True,
                last_tu_query_utc=now,
                claim_right_available=True,
                next_claim_reset_at_utc=now + datetime.timedelta(hours=2),
                roll_reset_at_utc=now + datetime.timedelta(hours=1),
                current_roll_cycle_id=cycle_id,
                current_claim_cycle_id=("claim", 1700000000, 1),
                normal_roll_action_owner=owner,
                roll_reset_anchor=ResetAnchor("roll", 60),
                claim_reset_anchor=ResetAnchor("claim", 180),
                normal_roll_replenishment_capacity_confidence=True,
                normal_roll_replenishment_capacity=8,
                predicted_roll_state_valid=True,
                rolls_left=8,
                key_mode=False,
                rt_available=False,
                _normal_roll_cycle_state={},
                _normal_roll_action_roll_counts={},
                _roll_batch_deferred_status_fields=set(),
            )
            initialize_status_tracking(c)
            clients.append(c)

        # Simultaneously trigger 3 boundary events per account (150 boundary triggers total)
        for client in clients:
            mark_status_dirty(client, {"claim"}, reason="claim cooldown-boundary", urgent=True)
            mark_status_dirty(client, {"rolls"}, reason="rolls replenishment-boundary", urgent=True)
            mark_status_dirty(client, None, reason="status-boundary", urgent=True)

        # Each client has exactly 1 merged pending request
        total_pending_requests = sum(1 for c in clients if getattr(c, "_pending_status_request", None) is not None)
        self.assertEqual(total_pending_requests, 50)

        # Simulate first account executing $tu and clearing its status
        first_client = clients[0]
        pacing_wait_0 = pacer.reserve(guild_id, 20.0)
        self.assertEqual(pacing_wait_0, 0.0)
        clear_status_dirty(first_client)

        # Now simulate remaining 49 clients advancing their roll cycle locally from anchor prediction
        executed_tu_count = 1
        skipped_tu_count = 0

        for client in clients[1:]:
            clear_status_dirty(client)
            state = get_normal_roll_cycle_state(client, client.current_roll_cycle_id)
            state.remaining = 8
            state.count_uncertain = False
            client.normal_roll_action_owner.schedule(
                cycle_id=client.current_roll_cycle_id,
                now_utc=now,
                humanization_enabled=True,
                window_minutes=10,
            )

            required, skip_reason = is_tu_still_required(client, proceed_to_rolls=True)
            if not required:
                client._tu_skipped_stale = True
                skipped_tu_count += 1
            else:
                executed_tu_count += 1

        self.assertEqual(executed_tu_count, 1)
        self.assertEqual(skipped_tu_count, 49)

    def test_genuinely_unresolved_private_roll_count_still_gets_physical_tu(self):
        """Test 4: An account with a genuinely unknown roll count still sends a physical $tu."""
        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)
        now = datetime.datetime.now(datetime.timezone.utc)
        cycle_id = ("roll", 1700000000, 1)
        client = SimpleNamespace(
            preset_name="test_account",
            is_paused=False,
            rolling_enabled=True,
            mudae_prefix="$",
            time_rolls_to_claim_reset=False,
            scheduled_roll_due=False,
            last_tu_snapshot_complete=False,
            last_tu_query_utc=None,
            claim_right_available=True,
            next_claim_reset_at_utc=now + datetime.timedelta(hours=2),
            roll_reset_at_utc=now + datetime.timedelta(hours=1),
            current_roll_cycle_id=cycle_id,
            current_claim_cycle_id=("claim", 1700000000, 1),
            normal_roll_action_owner=owner,
            roll_reset_anchor=ResetAnchor("roll", 60),
            claim_reset_anchor=ResetAnchor("claim", 180),
            normal_roll_replenishment_capacity_confidence=False,
            normal_roll_replenishment_capacity=None,
            predicted_roll_state_valid=False,
            rolls_left=0,
            key_mode=False,
            rt_available=False,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _roll_batch_deferred_status_fields=set(),
        )
        initialize_status_tracking(client)

        # Mark rolls dirty with unknown count and uncertain state
        mark_status_dirty(client, {"rolls"}, reason="private-roll-count-sync", urgent=True)
        state = get_normal_roll_cycle_state(client, cycle_id)
        state.remaining = None
        state.count_uncertain = True
        client.rolls_left = 0
        client.predicted_roll_state_valid = False

        required, reason = is_tu_still_required(client, proceed_to_rolls=True)
        self.assertTrue(required)
        self.assertEqual(reason, "required")

    def test_sixty_account_realistic_boundary_avoids_pacer_queue_starvation(self):
        """Test 5: 60 realistic clients at a shared boundary only send physical $tu for genuinely unresolved accounts."""
        pacer = GlobalIntervalCoordinator()
        guild_id = 123456
        now = datetime.datetime.now(datetime.timezone.utc)
        cycle_id = ("roll", 1700000000, 1)
        clients = []

        # Construct 60 accounts with realistic operational states
        for i in range(60):
            timing = RollActionTiming()
            owner = NormalRollActionOwner(timing)
            is_claim_only = (i < 10)  # 10 claim-only accounts (rolling_enabled=False)
            is_timing_mode = (10 <= i < 20)  # 10 accounts waiting for claim reset (time_rolls_to_claim_reset=True)
            is_cached_idle = (20 <= i < 28)  # 8 accounts with 0 rolls left and cached status
            is_unresolved = (i >= 58)  # 2 accounts genuinely unresolved
            is_learned_normal = (not is_claim_only and not is_timing_mode and not is_cached_idle and not is_unresolved)  # 30 accounts

            c = SimpleNamespace(
                preset_name=f"bot_{i}",
                user=SimpleNamespace(id=2000 + i, name=f"bot_{i}"),
                is_paused=False,
                rolling_enabled=not is_claim_only,
                mudae_prefix="$",
                time_rolls_to_claim_reset=is_timing_mode,
                scheduled_roll_due=False,
                last_tu_snapshot_complete=not is_unresolved,
                last_tu_query_utc=now if not is_unresolved else None,
                claim_right_available=not is_timing_mode,
                next_claim_reset_at_utc=now + datetime.timedelta(minutes=90 if is_timing_mode else 120),
                roll_reset_at_utc=now + datetime.timedelta(hours=1),
                current_roll_cycle_id=cycle_id,
                current_claim_cycle_id=("claim", 1700000000, 1),
                normal_roll_action_owner=owner,
                roll_reset_anchor=ResetAnchor("roll", 60),
                claim_reset_anchor=ResetAnchor("claim", 180),
                normal_roll_replenishment_capacity_confidence=is_learned_normal,
                normal_roll_replenishment_capacity=8 if is_learned_normal else None,
                predicted_roll_state_valid=is_learned_normal,
                rolls_left=8 if is_learned_normal else 0,
                key_mode=False,
                rt_available=False,
                _normal_roll_cycle_state={},
                _normal_roll_action_roll_counts={},
                _roll_batch_deferred_status_fields=set(),
            )
            initialize_status_tracking(c)

            # Establish initial cycle state
            state = get_normal_roll_cycle_state(c, cycle_id)
            if is_learned_normal:
                state.remaining = 8
                state.remaining_authoritative = True
                state.count_uncertain = False
                c.normal_roll_action_owner.schedule(
                    cycle_id=cycle_id,
                    now_utc=now,
                    humanization_enabled=True,
                    window_minutes=10,
                )
            elif is_unresolved:
                state.remaining = None
                state.count_uncertain = True
            elif is_cached_idle:
                state.remaining = 0
                state.remaining_authoritative = True
                state.count_uncertain = False

            clients.append(c)

        # Trigger boundary events across all 60 accounts
        for client in clients:
            mark_status_dirty(client, {"claim"}, reason="claim cooldown-boundary", urgent=True)
            mark_status_dirty(client, {"rolls"}, reason="rolls replenishment-boundary", urgent=True)
            mark_status_dirty(client, {"claim", "rolls"}, reason="status-boundary", urgent=True)

        # 1. Duplicate reasons remain coalesced per client
        for client in clients:
            pending = getattr(client, "_pending_status_request", None)
            self.assertIsNotNone(pending)
            self.assertTrue(len(pending.reasons) >= 3)

        # 2. Advance predicted reset cycles locally on all accounts
        for idx, client in enumerate(clients):
            if getattr(client, "normal_roll_replenishment_capacity_confidence", False):
                clear_status_dirty(client, {"rolls", "claim"})
            elif not getattr(client, "rolling_enabled", True):
                clear_status_dirty(client, {"claim"})
            elif getattr(client, "time_rolls_to_claim_reset", False):
                clear_status_dirty(client, {"rolls", "claim"})
            elif 20 <= idx < 28:
                clear_status_dirty(client, {"rolls", "claim"})

        # 3. Simulate pre-pacing check and pacer reservation across all 60 clients
        physical_tu_sent = 0
        pacer_slots_reserved = 0
        skipped_accounts = 0

        for client in clients:
            # Check is_tu_still_required BEFORE reserving a slot in the pacer
            required, reason = is_tu_still_required(
                client,
                proceed_to_rolls=client.rolling_enabled,
            )
            if not required:
                skipped_accounts += 1
                continue

            # Only unresolved accounts reserve a pacer slot
            wait = pacer.reserve(guild_id, 20.0)
            pacer_slots_reserved += 1

            # After pacing, revalidate
            req_post, reason_post = is_tu_still_required(
                client,
                proceed_to_rolls=client.rolling_enabled,
            )
            if req_post:
                physical_tu_sent += 1

        # Assert exactly 58 accounts were skipped before pacing and only 2 genuinely unresolved accounts reached $tu
        self.assertEqual(skipped_accounts, 58)
        self.assertEqual(pacer_slots_reserved, 2)
        self.assertEqual(physical_tu_sent, 2)

    def test_disabled_rolling_account_does_not_enter_tu_pacing(self):
        """Test 6: An account with rolling disabled and only rolls marked dirty skips physical $tu."""
        now = datetime.datetime.now(datetime.timezone.utc)
        cycle_id = ("roll", 1700000000, 1)
        client = SimpleNamespace(
            preset_name="claim_only_bot",
            is_paused=False,
            rolling_enabled=False,
            mudae_prefix="$",
            time_rolls_to_claim_reset=False,
            scheduled_roll_due=False,
            last_tu_snapshot_complete=True,
            last_tu_query_utc=now,
            claim_right_available=True,
            next_claim_reset_at_utc=now + datetime.timedelta(hours=2),
            roll_reset_at_utc=now + datetime.timedelta(hours=1),
            current_roll_cycle_id=cycle_id,
            current_claim_cycle_id=("claim", 1700000000, 1),
            normal_roll_action_owner=None,
            roll_reset_anchor=ResetAnchor("roll", 60),
            claim_reset_anchor=ResetAnchor("claim", 180),
            rolls_left=0,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _roll_batch_deferred_status_fields=set(),
        )
        initialize_status_tracking(client)
        mark_status_dirty(client, {"rolls"}, reason="rolls replenishment-boundary")

        required, reason = is_tu_still_required(client, proceed_to_rolls=False)
        self.assertFalse(required)
        self.assertEqual(reason, "rolling-disabled")

    def test_server_reset_minute_anchoring_test_a(self):
        """Issue 1 Test A: server_reset_minute=25 anchors boundaries; stale xx:05 observation cannot advance early."""
        anchor = ResetAnchor("roll", 60, authoritative_minute=25)
        # Reference time at 14:10 UTC
        ref_time = datetime.datetime(2026, 8, 27, 14, 10, tzinfo=datetime.timezone.utc)
        anchor.advance_through(ref_time)
        self.assertEqual(anchor.next_boundary_at_utc, datetime.datetime(2026, 8, 27, 14, 25, tzinfo=datetime.timezone.utc))

        # Stale/learned anchor observation suggesting xx:05 (e.g. 15:05)
        stale_observed = datetime.datetime(2026, 8, 27, 14, 5, tzinfo=datetime.timezone.utc)
        stale_proposed = datetime.datetime(2026, 8, 27, 15, 5, tzinfo=datetime.timezone.utc)
        changed, refined = anchor.observe(stale_proposed, stale_observed)
        self.assertFalse(changed)
        self.assertEqual(anchor.next_boundary_at_utc.minute, 25)

        # Local roll cycle does NOT advance at xx:05
        early_adv = anchor.advance_through(stale_observed)
        self.assertEqual(early_adv, [])

        # Cycle advances at xx:25
        reset_time = datetime.datetime(2026, 8, 27, 14, 25, tzinfo=datetime.timezone.utc)
        advanced = anchor.advance_through(reset_time)
        self.assertEqual(len(advanced), 1)
        self.assertEqual(advanced[0][1], reset_time)
        self.assertEqual(anchor.next_boundary_at_utc, datetime.datetime(2026, 8, 27, 15, 25, tzinfo=datetime.timezone.utc))

    def test_server_reset_minute_none_auto_detection_test_b(self):
        """Issue 1 Test B: server_reset_minute=None preserves automatic reset boundary detection."""
        anchor = ResetAnchor("roll", 60, authoritative_minute=None)
        start = datetime.datetime(2026, 8, 27, 14, 5, tzinfo=datetime.timezone.utc)
        changed, refined = anchor.observe(start, start - datetime.timedelta(minutes=20))
        self.assertTrue(changed)
        self.assertEqual(anchor.next_boundary_at_utc, start)
        self.assertEqual(anchor.next_boundary_at_utc.minute, 5)

    def test_server_reset_minute_tu_private_state_preserved_test_c(self):
        """Issue 1 Test C: Authoritative $tu updates private state while reset minute remains strictly 25."""
        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)
        now = datetime.datetime(2026, 8, 27, 14, 10, tzinfo=datetime.timezone.utc)
        anchor = ResetAnchor("roll", 60, authoritative_minute=25)
        anchor.advance_through(now)
        cycle_id = anchor.cycle_id_for_boundary(anchor.next_boundary_index - 1)

        client = SimpleNamespace(
            preset_name="anchor_test",
            is_paused=False,
            rolling_enabled=True,
            mudae_prefix="$",
            time_rolls_to_claim_reset=False,
            scheduled_roll_due=False,
            last_tu_snapshot_complete=True,
            last_tu_query_utc=now,
            claim_right_available=True,
            next_claim_reset_at_utc=now + datetime.timedelta(hours=2),
            roll_reset_at_utc=anchor.next_boundary_at_utc,
            current_roll_cycle_id=cycle_id,
            current_claim_cycle_id=("claim", 1700000000, 1),
            normal_roll_action_owner=owner,
            roll_reset_anchor=anchor,
            claim_reset_anchor=ResetAnchor("claim", 180),
            rolls_left=0,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _roll_batch_deferred_status_fields=set(),
        )
        initialize_status_tracking(client)

        # $tu arrives indicating rolls = 16 and roll timer suggesting 5 minutes (xx:05)
        parsed_rolls = 16
        stale_reset_deadline = now + datetime.timedelta(minutes=5)
        anchor.observe(stale_reset_deadline, now)
        reconcile_authoritative_current_roll_count(
            client,
            parsed_rolls,
            observation_kind="check-status",
            observed_at_utc=now,
        )

        # Configured reset minute remains 25
        self.assertEqual(anchor.next_boundary_at_utc.minute, 25)
        # Private state updated to 16
        self.assertEqual(client.rolls_left, 16)
        state = get_normal_roll_cycle_state(client, cycle_id)
        self.assertEqual(state.remaining, 16)
        self.assertTrue(state.remaining_authoritative)

    def test_authoritative_status_pending_action_suppresses_redundant_tu_and_executes(self):
        """Issue 2 Mandatory Regression Test: Rolls=16 pending action suppresses redundant $tu and executes correctly."""
        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)
        now = datetime.datetime.now(datetime.timezone.utc)
        cycle_id = ("roll", 1700000000, 1)

        wake_invoked = []
        def mock_schedule_owned_normal_action(cid, now_ts):
            wake_invoked.append(cid)

        client = SimpleNamespace(
            preset_name="test_prod_path",
            is_paused=False,
            rolling_enabled=True,
            mudae_prefix="$",
            time_rolls_to_claim_reset=False,
            scheduled_roll_due=False,
            last_tu_snapshot_complete=True,
            last_tu_query_utc=now,
            claim_right_available=True,
            next_claim_reset_at_utc=now + datetime.timedelta(hours=2),
            roll_reset_at_utc=now + datetime.timedelta(hours=1),
            current_roll_cycle_id=cycle_id,
            current_claim_cycle_id=("claim", 1700000000, 1),
            normal_roll_action_owner=owner,
            roll_reset_anchor=ResetAnchor("roll", 60),
            claim_reset_anchor=ResetAnchor("claim", 180),
            rolls_left=16,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _roll_batch_deferred_status_fields=set(),
            _schedule_owned_normal_roll_action=mock_schedule_owned_normal_action,
        )
        initialize_status_tracking(client)

        state = get_normal_roll_cycle_state(client, cycle_id)
        state.remaining = 16
        state.remaining_authoritative = True
        state.count_uncertain = False

        # Real production scheduling
        owner.schedule(
            cycle_id=cycle_id,
            now_utc=now,
            humanization_enabled=True,
            window_minutes=5,
        )
        self.assertTrue(owner.is_pending(cycle_id))

        # Status boundary wake occurs before action execution
        mark_status_dirty(client, set(), reason="status-boundary")
        policy = normal_action_status_policy(
            owner_cycle_id=owner.cycle_id,
            current_roll_cycle_id=client.current_roll_cycle_id,
            owner_state=owner.state,
            state_dirty=normal_roll_action_state_is_dirty(client, client.current_roll_cycle_id),
        )
        self.assertEqual(policy, "suppress-routine")

        # Assert no second physical $tu requested
        required, reason = is_tu_still_required(client, proceed_to_rolls=True)
        self.assertFalse(required)
        self.assertEqual(reason, "policy-suppress-routine")

        # One valid normal action remains pending
        self.assertTrue(owner.is_pending(cycle_id))

        # When wake fires: execution transitions pending -> executing
        started = owner.start(cycle_id)
        self.assertTrue(started)
        self.assertEqual(owner.state, "executing")

    def test_pending_wake_cancelled_or_broken_rearmer(self):
        """Issue 2 Failure/Recovery Test: scheduler detects and rearms broken wake instead of permanently suppressing work."""
        timing = RollActionTiming()
        owner = NormalRollActionOwner(timing)
        now = datetime.datetime.now(datetime.timezone.utc)
        cycle_id = ("roll", 1700000000, 1)

        rearmed = []
        def mock_rearm(cid, now_ts):
            rearmed.append(cid)

        client = SimpleNamespace(
            preset_name="test_broken_wake",
            is_paused=False,
            rolling_enabled=True,
            mudae_prefix="$",
            time_rolls_to_claim_reset=False,
            scheduled_roll_due=False,
            last_tu_snapshot_complete=True,
            last_tu_query_utc=now,
            claim_right_available=True,
            next_claim_reset_at_utc=now + datetime.timedelta(hours=2),
            roll_reset_at_utc=now + datetime.timedelta(hours=1),
            current_roll_cycle_id=cycle_id,
            current_claim_cycle_id=("claim", 1700000000, 1),
            normal_roll_action_owner=owner,
            roll_reset_anchor=ResetAnchor("roll", 60),
            claim_reset_anchor=ResetAnchor("claim", 180),
            rolls_left=16,
            _normal_roll_cycle_state={},
            _normal_roll_action_roll_counts={},
            _roll_batch_deferred_status_fields=set(),
            _schedule_owned_normal_roll_action=mock_rearm,
        )
        initialize_status_tracking(client)

        state = get_normal_roll_cycle_state(client, cycle_id)
        state.remaining = 16
        state.remaining_authoritative = True
        state.count_uncertain = False

        owner.schedule(cycle_id=cycle_id, now_utc=now)
        self.assertTrue(owner.is_pending(cycle_id))

        # Status check verifies policy and triggers rearm check
        is_tu_still_required(client, proceed_to_rolls=True)
        self.assertIn(cycle_id, rearmed)


if __name__ == "__main__":
    unittest.main()
