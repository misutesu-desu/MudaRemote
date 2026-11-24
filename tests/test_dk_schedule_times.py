import datetime
import unittest

import mudae_bot
from mudae_core.config import parse_dk_schedule_time, validate_preset


ZONE = datetime.timezone(datetime.timedelta(hours=1))


def at(hour, minute, day=24):
    return datetime.datetime(2026, 11, day, hour, minute, tzinfo=ZONE)


class SeveralDkScheduleTimesTests(unittest.TestCase):
    def test_editor_validation_accepts_a_comma_separated_list(self):
        self.assertEqual(parse_dk_schedule_time(" 18:30 , 06:00 "), ("06:00, 18:30", []))
        self.assertEqual(parse_dk_schedule_time("06:00,06:00"), ("06:00", []))
        for value in ("06:00, 9:00", "06:00,", "06:00; 18:30"):
            with self.subTest(value=value):
                self.assertTrue(parse_dk_schedule_time(value)[1])
                self.assertTrue(validate_preset({"dk_schedule_time": value}, require_runtime=False))

    def test_runtime_parser_normalizes_and_fails_closed(self):
        self.assertEqual(mudae_bot.parse_dk_schedule_time("18:30, 06:00"), "06:00, 18:30")
        self.assertIsNone(mudae_bot.parse_dk_schedule_time("18:30, later"))

    def test_each_time_opens_its_own_window(self):
        schedule = "06:00, 18:30"
        self.assertIsNone(mudae_bot.scheduled_dk_window_if_due(schedule, at(5, 59)))
        morning = mudae_bot.scheduled_dk_window_if_due(schedule, at(6, 0))
        self.assertEqual(morning, (at(6, 0).date(), "06:00"))
        self.assertIsNone(mudae_bot.scheduled_dk_window_if_due(schedule, at(12, 0), morning))
        evening = mudae_bot.scheduled_dk_window_if_due(schedule, at(18, 30), morning)
        self.assertEqual(evening, (at(18, 30).date(), "18:30"))
        self.assertIsNone(mudae_bot.scheduled_dk_window_if_due(schedule, at(23, 0), evening))

    def test_a_late_start_uses_one_dk_for_the_latest_missed_time(self):
        window = mudae_bot.scheduled_dk_window_if_due("06:00, 18:30", at(20, 0))
        self.assertEqual(window, (at(20, 0).date(), "18:30"))

    def test_next_wake_is_the_nearest_time(self):
        schedule = "06:00, 18:30"
        self.assertEqual(mudae_bot.next_dk_schedule_at(schedule, at(5, 0)), at(6, 0))
        self.assertEqual(mudae_bot.next_dk_schedule_at(schedule, at(6, 0)), at(18, 30))
        self.assertEqual(mudae_bot.next_dk_schedule_at(schedule, at(19, 0)), at(6, 0, day=25))


if __name__ == "__main__":
    unittest.main()
