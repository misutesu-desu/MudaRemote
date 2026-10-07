"""Server Reset Minute also pins the claim reset, not only the roll reset."""

import datetime
from types import SimpleNamespace
import unittest

from mudae_core.bot_config import configure_client
from mudae_core.status import ResetAnchor, snap_to_reset_minute

UTC = datetime.timezone.utc


def at(hour, minute, second=0):
    return datetime.datetime(2026, 10, 7, hour, minute, second, tzinfo=UTC)


class SnapToResetMinuteTests(unittest.TestCase):
    def test_minute_rounded_timer_snaps_to_the_configured_minute(self):
        # $tu at 17:42:05 said 3 min; the server resets at xx:44.
        self.assertEqual(snap_to_reset_minute(at(17, 45, 7), 44, now_utc=at(17, 42, 5)), at(17, 44))
        self.assertEqual(snap_to_reset_minute(at(17, 43, 30), 44, now_utc=at(17, 42, 5)), at(17, 44))

    def test_snaps_across_the_hour(self):
        self.assertEqual(snap_to_reset_minute(at(18, 1, 2), 59, now_utc=at(17, 30)), at(17, 59))
        self.assertEqual(snap_to_reset_minute(at(17, 58, 30), 0, now_utc=at(17, 30)), at(18, 0))

    def test_far_or_past_or_unset_values_are_left_alone(self):
        self.assertEqual(snap_to_reset_minute(at(17, 30), 44, now_utc=at(17, 0)), at(17, 30))
        self.assertEqual(snap_to_reset_minute(at(17, 44, 30), 44, now_utc=at(17, 44, 10)), at(17, 44, 30))
        self.assertEqual(snap_to_reset_minute(at(17, 45, 7), None, now_utc=at(17, 42)), at(17, 45, 7))


class ClaimAnchorTests(unittest.TestCase):
    def test_claim_anchor_keeps_the_configured_minute(self):
        anchor = ResetAnchor("claim", 180, snap_minute=44)
        anchor.observe(at(17, 45, 7), at(17, 42, 5))
        self.assertEqual(anchor.next_boundary_at_utc, at(17, 44))
        anchor.observe(at(17, 44, 19), at(17, 43, 17))
        self.assertEqual(anchor.next_boundary_at_utc, at(17, 44))
        self.assertEqual([b for _, b in anchor.advance_through(at(17, 44, 1))], [at(17, 44)])
        self.assertEqual(anchor.next_boundary_at_utc, at(20, 44))

    def test_without_a_configured_minute_the_timer_is_used_as_before(self):
        anchor = ResetAnchor("claim", 180)
        anchor.observe(at(17, 45, 7), at(17, 42, 5))
        self.assertEqual(anchor.next_boundary_at_utc, at(17, 45, 7))

    def test_preset_minute_reaches_the_claim_anchor(self):
        options = {"bot_name": "MudaRemote", "claim_emojis": [], "kakera_emojis": [],
                   "sphere_emojis": [], "slash_available": True}
        client = SimpleNamespace(hourly_tu_refresh=False)
        configure_client(client, "test", {"channel_id": 1, "server_reset_minute": 44}, **options)
        self.assertEqual(client.claim_reset_anchor.snap_minute, 44)
        client = SimpleNamespace(hourly_tu_refresh=False)
        configure_client(client, "test", {"channel_id": 1}, **options)
        self.assertIsNone(client.claim_reset_anchor.snap_minute)


if __name__ == "__main__":
    unittest.main()
