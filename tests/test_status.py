import datetime
from types import SimpleNamespace
import unittest

from mudae_core.status import (
    STATUS_FIELDS,
    ServerResetCoordinator,
    clear_status_dirty,
    consume_tu_urgent_bypass,
    defer_tu_queries,
    initialize_status_tracking,
    looks_like_tu_status_snapshot,
    mark_status_dirty,
    parse_claim_denied_cooldown,
    record_tu_failure,
    record_tu_success,
    reconcile_shared_roll_deadline,
    rolls_usage_is_active,
    status_dirty_fields,
    status_message_addresses_identity,
    status_refresh_reasons,
    tu_cache_seconds_remaining,
    tu_retry_wait,
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

        deadline, advanced = reconcile_shared_roll_deadline(
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

        deadline, advanced = reconcile_shared_roll_deadline(
            local_boundary,
            observed,
            next_boundary,
        )

        self.assertEqual(deadline, next_boundary)
        self.assertTrue(advanced)

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
        claim_deadline = observed + datetime.timedelta(minutes=30)
        roll_deadline = observed + datetime.timedelta(minutes=15)

        snapshot, changed = coordinator.observe(
            10,
            100,
            observed,
            claim_reset_at_utc=claim_deadline,
            roll_reset_at_utc=roll_deadline,
        )
        duplicate, duplicate_changed = coordinator.observe(
            10,
            100,
            observed + datetime.timedelta(seconds=1),
            claim_reset_at_utc=observed + datetime.timedelta(hours=3),
        )

        self.assertTrue(changed)
        self.assertFalse(duplicate_changed)
        self.assertEqual(snapshot, duplicate)
        self.assertEqual(coordinator.snapshot(10).claim_reset_at_utc, claim_deadline)
        self.assertIsNone(coordinator.snapshot(11))


if __name__ == "__main__":
    unittest.main()
