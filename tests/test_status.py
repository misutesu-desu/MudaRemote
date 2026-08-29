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
    tu_cache_seconds_remaining,
    tu_retry_wait,
)
from mudae_core.runtime import (
    claim_roll_count_reconciliation,
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


if __name__ == "__main__":
    unittest.main()
