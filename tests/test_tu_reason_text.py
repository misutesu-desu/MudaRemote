import datetime
import unittest
from types import SimpleNamespace

from mudae_core.runtime import describe_tu_demand


class TuReasonTextTests(unittest.TestCase):
    """The $tu log line names why the status is checked, not just "required"."""

    def setUp(self):
        self.now = datetime.datetime(2026, 10, 6, 12, 0, tzinfo=datetime.timezone.utc)

    def _client(self, reasons=()):
        return SimpleNamespace(_status_refresh_reasons=set(reasons))

    def test_dirty_fields_name_what_triggered_them(self):
        reason = describe_tu_demand(
            self._client({"claim-verification-inconclusive"}), {"claim", "rt"},
            False, True, self.now, self.now,
        )
        self.assertEqual(reason, "refresh claim, rt after claim-verification-inconclusive")

    def test_scheduled_roll_is_named(self):
        reason = describe_tu_demand(self._client(), set(), True, True, self.now, self.now)
        self.assertEqual(reason, "scheduled roll due")

    def test_expired_cache_is_named(self):
        old = self.now - datetime.timedelta(minutes=31)
        reason = describe_tu_demand(self._client(), set(), False, True, old, self.now)
        self.assertEqual(reason, "last $tu older than 30m")

    def test_pending_work_with_fresh_cache_is_named(self):
        recent = self.now - datetime.timedelta(minutes=2)
        reason = describe_tu_demand(self._client(), set(), False, True, recent, self.now)
        self.assertEqual(reason, "roll, $us or sphere work waiting")


if __name__ == "__main__":
    unittest.main()
