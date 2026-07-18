from types import SimpleNamespace
import unittest

from mudae_core.status import (
    STATUS_FIELDS,
    clear_status_dirty,
    consume_tu_urgent_bypass,
    defer_tu_queries,
    initialize_status_tracking,
    mark_status_dirty,
    record_tu_failure,
    record_tu_success,
    status_dirty_fields,
    status_refresh_reasons,
    tu_retry_wait,
)


class StatusFreshnessTests(unittest.TestCase):
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

    def test_new_urgent_reason_bypasses_backoff_only_once(self):
        record_tu_failure(self.client, now_monotonic=100.0)
        mark_status_dirty(self.client, {"claim"}, reason="claim-inconclusive", urgent=True)
        self.assertTrue(consume_tu_urgent_bypass(self.client))
        self.assertFalse(consume_tu_urgent_bypass(self.client))
        mark_status_dirty(self.client, {"claim"}, reason="claim-inconclusive", urgent=True)
        self.assertFalse(consume_tu_urgent_bypass(self.client))
        mark_status_dirty(self.client, {"claim"}, reason="claim-reset", urgent=True)
        self.assertTrue(consume_tu_urgent_bypass(self.client))


if __name__ == "__main__":
    unittest.main()
