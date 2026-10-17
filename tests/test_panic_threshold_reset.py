"""The panic-window Min Kakera bypass ends with the claim cycle it was for."""
import datetime
import unittest
from unittest import mock

import mudae_bot
from mudae_core.status import ResetAnchor
from tests.test_roll_window_production import _build_runtime


class PanicThresholdResetTests(unittest.TestCase):
    def test_local_claim_reset_restores_min_kakera_after_panic_window(self):
        bot = _build_runtime()
        now = datetime.datetime.now(datetime.timezone.utc)
        boundary = now + datetime.timedelta(seconds=60)
        anchor = ResetAnchor("claim", bot.claim_interval)
        anchor.observe(boundary, now)
        bot.claim_reset_anchor = anchor
        bot.next_claim_reset_at_utc = anchor.next_boundary_at_utc
        bot.min_kakera = 300
        bot.claim_right_available = True
        # Lurker Strategy's panic window dumps everything before the reset.
        bot.current_min_kakera_for_roll_claim = 0

        with mock.patch.object(mudae_bot.BotLogger, "log"):
            bot._runtime_advance_predicted_reset_cycles(boundary + datetime.timedelta(seconds=1))

        self.assertEqual(bot.next_claim_reset_at_utc, boundary + datetime.timedelta(minutes=bot.claim_interval))
        self.assertEqual(bot.current_min_kakera_for_roll_claim, 300)


if __name__ == "__main__":
    unittest.main()
