import datetime
import inspect
import unittest

from mudae_core.spheres import SphereButtonBudget
from tests.test_kakera_snipe_ownership import _create_test_client, _build_roll_message

NOW = datetime.datetime(2026, 11, 7, 12, 0, tzinfo=datetime.timezone.utc)


def _budget(clicked, limit, pending=0):
    budget = SphereButtonBudget()
    budget.clicked, budget.limit = clicked, limit
    for index in range(pending):
        budget.reserve(index, NOW)
    return budget


class NearlyUsedTests(unittest.TestCase):
    def test_off_unknown_or_full_quota_never_counts(self):
        self.assertFalse(_budget(15, 20).nearly_used(0))
        self.assertFalse(SphereButtonBudget().nearly_used(5))
        self.assertFalse(_budget(20, 20).nearly_used(5))

    def test_last_buttons_of_the_quota_count(self):
        self.assertFalse(_budget(14, 20).nearly_used(5))
        self.assertTrue(_budget(15, 20).nearly_used(5))
        self.assertTrue(_budget(19, 20).nearly_used(5))

    def test_clicks_waiting_for_tu_use_up_the_quota_too(self):
        self.assertTrue(_budget(13, 20, pending=2).nearly_used(5))
        self.assertFalse(_budget(18, 20, pending=2).nearly_used(5))


class SphereEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.bot, self.channel = _create_test_client(
            sphere_click_targets=["spR"], sphere_collect_any_last=5)
        self.details = inspect.getclosurevars(
            inspect.getclosurevars(self.bot._runtime_claim_character).nonlocals["click_kakera_with_confirmation"]
        ).nonlocals["kakera_click_details"]

    def _eligible(self, name):
        msg, btn = _build_roll_message(self.channel, 99301, 7001, "snipe-bot", kakera_emoji=name)
        return self.details(msg, btn) is not None

    def test_unselected_colour_is_skipped_while_quota_is_far(self):
        self.bot.sphere_button_budget.clicked, self.bot.sphere_button_budget.limit = 10, 20
        self.assertTrue(self._eligible("spR"))
        self.assertFalse(self._eligible("spB"))

    def test_unselected_colour_is_clicked_for_the_last_buttons(self):
        self.bot.sphere_button_budget.clicked, self.bot.sphere_button_budget.limit = 15, 20
        self.assertTrue(self._eligible("spB"))
        self.assertTrue(self._eligible("spT"))

    def test_quota_free_sphere_keeps_following_the_list(self):
        self.bot.sphere_button_budget.clicked, self.bot.sphere_button_budget.limit = 15, 20
        self.assertFalse(self._eligible("spM"))

    def test_unknown_quota_keeps_the_list(self):
        self.assertFalse(self._eligible("spB"))

    def test_setting_defaults_to_off(self):
        bot, _ = _create_test_client()
        self.assertEqual(bot.sphere_collect_any_last, 0)


if __name__ == "__main__":
    unittest.main()
