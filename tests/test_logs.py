"""Log lines, kinds, redaction, daily TXT files, retention, filters (made-up data only)."""
import datetime
import os
import tempfile
import unittest
from unittest import mock

from mudae_core import logs

# Built from parts so secret scanners do not mistake the fixture for a real token.
FAKE_TOKEN = ".".join(("ZmFrZXVzZXJpZGZvcnRlc3Q", "AbCdEf", "fakefakefakefakefakefakefakefake"))
FAKE_ID = "123456789012345678"


class FakeClock:
    def __init__(self, moment):
        self.moment = moment

    def __call__(self):
        return self.moment


class LineFormatTests(unittest.TestCase):
    def test_line_has_the_shared_shape(self):
        when = datetime.datetime(2026, 11, 28, 9, 5, 7)
        line = logs.format_line(when, "Alt One", "CLAIM", "Claimed Rem")
        self.assertEqual(line, "2026-11-28 09:05:07 | Alt One | CLAIM | Claimed Rem")
        entry = logs.parse_line(line)
        self.assertEqual((entry.profile, entry.kind, entry.message), ("Alt One", "CLAIM", "Claimed Rem"))

    def test_separators_and_newlines_cannot_break_the_shape(self):
        line = logs.format_line("2026-11-28 09:05:07", "A | B", "ROLL", "first\nsecond | third")
        entry = logs.parse_line(line)
        self.assertEqual(entry.profile, "A / B")
        self.assertEqual(entry.message, "first / second / third")
        self.assertNotIn("\n", line)

    def test_unparsable_line_is_none(self):
        self.assertIsNone(logs.parse_line("[INFO] [x] old shape"))


class KindTests(unittest.TestCase):
    def test_new_features_get_their_own_kinds(self):
        cases = {
            "Fast setup: sent once to the main.": "SETUP",
            "Perk 10: spheres 12,000 -> upgrading 12 character(s).": "PERK",
            "Harem give: page(s) 1 2 given to the main.": "GIVE",
            "Auto-give: gave 5,000 kakera to the main.": "GIVE",
            "Side roll: rolling 10 for the main.": "SIDE",
            "$oh: An unveil landed on the Hidden Ourosphere.": "SPHERE",
            "Checking $tu... (reason: status-boundary)": "STATUS",
            "Claimed Rem (Re:Zero) for 450 kakera": "CLAIM",
            "Rolling 12 with $wa": "ROLL",
            "Connected to the gateway": "SYSTEM",
        }
        for message, kind in cases.items():
            self.assertEqual(logs.classify_kind(message, "INFO"), kind, message)

    def test_levels_map_to_kinds(self):
        self.assertEqual(logs.classify_kind("anything", "ERROR"), "ERROR")
        self.assertEqual(logs.classify_kind("anything", "CLAIM"), "CLAIM")
        self.assertEqual(logs.classify_kind("anything", "KAKERA"), "KAKERA")
        self.assertEqual(logs.classify_kind("anything", "CHECK"), "STATUS")
        self.assertEqual(logs.classify_kind("anything", "RESET"), "STATUS")
        self.assertEqual(logs.classify_kind("anything odd", "WARN"), "WARN")

    def test_refusal_with_the_bot_reply_is_an_error(self):
        message = "Harem give stopped: refused. Bot said: «You can't do that»"
        self.assertEqual(logs.classify_kind(message, "WARN"), "ERROR")

    def test_reply_text_is_shortened_on_one_line(self):
        reply = "line one\nline two " + "x" * 400
        short = logs.shorten_reply(reply, 60)
        self.assertLessEqual(len(short), 60)
        self.assertNotIn("\n", short)


class RedactionTests(unittest.TestCase):
    def test_token_is_removed_fully(self):
        out = logs.redact_text("login with " + FAKE_TOKEN + " done")
        self.assertNotIn(FAKE_TOKEN, out)
        self.assertNotIn("fakefake", out)
        self.assertIn(logs.TOKEN_REMOVED, out)

    def test_known_secret_is_removed(self):
        out = logs.redact_text("secret=hunter2-hunter2", secrets=["hunter2-hunter2"])
        self.assertNotIn("hunter2", out)

    def test_ids_keep_the_last_four_digits(self):
        out = logs.redact_text("channel " + FAKE_ID + " ok")
        self.assertEqual(out, "channel …5678 ok")

    def test_mentions_are_shortened(self):
        out = logs.redact_text("hi <@{0}> and <@!{0}> in <#{0}> role <@&{0}>".format(FAKE_ID))
        self.assertNotIn(FAKE_ID, out)
        self.assertIn("<@…5678>", out)
        self.assertIn("<@!…5678>", out)
        self.assertIn("<#…5678>", out)
        self.assertIn("<@&…5678>", out)

    def test_sentences_numbers_and_running_twice_are_safe(self):
        text = "Claimed Rem for 1,250 kakera at 12.30 (rank 123)"
        self.assertEqual(logs.redact_text(text), text)
        once = logs.redact_text("id " + FAKE_ID)
        self.assertEqual(logs.redact_text(once), once)

    def test_build_line_redacts_before_anything_else(self):
        line = logs.build_line(datetime.datetime(2026, 11, 28, 1, 2, 3), "Main", "ERROR",
                               "failed for <@{}> with {}".format(FAKE_ID, FAKE_TOKEN))
        self.assertNotIn(FAKE_ID, line)
        self.assertNotIn(FAKE_TOKEN, line)
        self.assertEqual(logs.parse_line(line).kind, "ERROR")


class FilterTests(unittest.TestCase):
    LINES = [
        "2026-11-28 10:00:00 | Main | ROLL | Rolling 12",
        "2026-11-28 10:00:05 | Main | CLAIM | Claimed Rem",
        "2026-11-28 10:01:00 | Alt | GIVE | Gave 5,000 kakera",
        "2026-11-28 10:02:00 | Alt | ERROR | Give stopped. Bot said: «no»",
        "[INFO] [old] leftover",
    ]

    def test_by_profile_kind_search_and_errors_only(self):
        self.assertEqual(len(logs.filter_lines(self.LINES, profile="alt")), 2)
        self.assertEqual(len(logs.filter_lines(self.LINES, kind="claim")), 1)
        self.assertEqual(len(logs.filter_lines(self.LINES, search="KAKERA")), 1)
        self.assertEqual(len(logs.filter_lines(self.LINES, errors_only=True)), 1)
        self.assertEqual(len(logs.filter_lines(self.LINES, profile="Alt", kind="GIVE", search="gave")), 1)

    def test_no_filter_keeps_everything_and_unparsed_lines_drop_with_filters(self):
        self.assertEqual(logs.filter_lines(self.LINES), self.LINES)
        self.assertNotIn(self.LINES[-1], logs.filter_lines(self.LINES, profile="Main"))
        self.assertEqual(logs.profiles_in(self.LINES), ["Alt", "Main"])


class SettingsTests(unittest.TestCase):
    def test_defaults(self):
        settings = logs.LogSettings.from_data({})
        self.assertEqual(tuple(settings), (True, 14, 50))

    def test_values_are_clamped_and_bad_values_fall_back(self):
        settings = logs.LogSettings.from_data({"save_logs_txt": False, "logs_keep_days": "0", "logs_max_mb": "abc"})
        self.assertEqual(tuple(settings), (False, 1, 50))

    def test_validation_messages(self):
        self.assertEqual(logs.validate_log_settings({}), [])
        self.assertEqual(len(logs.validate_log_settings({"logs_keep_days": 0, "logs_max_mb": "x"})), 2)


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = os.path.join(self.tmp.name, "logs")
        self.addCleanup(self.tmp.cleanup)

    def writer(self, moment, **settings):
        data = {"logs_keep_days": 14, "logs_max_mb": 50}
        data.update(settings)
        return logs.DailyLogWriter(self.folder, logs.LogSettings.from_data(data), clock=FakeClock(moment))

    def test_safe_file_names(self):
        self.assertEqual(logs.safe_file_part("Main/Alt: *1*"), "Main_Alt_ _1")
        self.assertEqual(logs.safe_file_part("..."), "profile")
        self.assertEqual(logs.safe_file_part("con"), "con_")
        self.assertEqual(logs.day_file_name("Main", datetime.date(2026, 11, 28)), "Main_2026-11-28.txt")

    def test_one_file_per_profile_per_day_utf8_appended(self):
        moment = datetime.datetime(2026, 11, 28, 23, 59, 0)
        clock = FakeClock(moment)
        writer = logs.DailyLogWriter(self.folder, logs.LogSettings.from_data({}), clock=clock)
        writer.write("Main", "line one", moment)
        writer.write("Main", "سطر عربي", moment)
        writer.write("Alt", "alt line", moment)
        clock.moment = datetime.datetime(2026, 11, 29, 0, 0, 1)
        writer.write("Main", "next day", clock.moment)
        writer.flush()
        names = sorted(os.listdir(self.folder))
        self.assertEqual(names, ["Alt_2026-11-28.txt", "Main_2026-11-28.txt", "Main_2026-11-29.txt"])
        with open(os.path.join(self.folder, "Main_2026-11-28.txt"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "line one\nسطر عربي\n")

    def test_disabled_writes_nothing(self):
        writer = self.writer(datetime.datetime(2026, 11, 28, 1, 0, 0), save_logs_txt=False)
        writer.write("Main", "line")
        writer.flush()
        self.assertFalse(os.path.exists(self.folder))

    def test_rename_moves_and_merges_files(self):
        writer = self.writer(datetime.datetime(2026, 11, 28, 1, 0, 0))
        writer.write("Old", "a")
        writer.flush()
        os.makedirs(self.folder, exist_ok=True)
        with open(os.path.join(self.folder, "New_2026-11-28.txt"), "w", encoding="utf-8") as handle:
            handle.write("b\n")
        self.assertEqual(writer.rename_profile("Old", "New"), 1)
        self.assertEqual(os.listdir(self.folder), ["New_2026-11-28.txt"])
        with open(os.path.join(self.folder, "New_2026-11-28.txt"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "b\na\n")

    def _make(self, name, day, size):
        os.makedirs(self.folder, exist_ok=True)
        path = os.path.join(self.folder, "{}_{}.txt".format(name, day))
        with open(path, "wb") as handle:
            handle.write(b"x" * size)
        return path

    def test_keep_days_deletes_old_files_only(self):
        old = self._make("Main", "2026-11-01", 10)
        kept = self._make("Main", "2026-11-20", 10)
        removed = logs.prune_logs(self.folder, 14, 50, today=datetime.date(2026, 11, 28))
        self.assertEqual(removed, [old])
        self.assertTrue(os.path.exists(kept))

    def test_size_cap_deletes_oldest_first_and_spares_today(self):
        mb = 1024 * 1024
        oldest = self._make("Main", "2026-11-25", mb)
        middle = self._make("Main", "2026-11-26", mb)
        today = self._make("Main", "2026-11-28", mb)
        removed = logs.prune_logs(self.folder, 14, 1, today=datetime.date(2026, 11, 28))
        self.assertEqual(removed, [oldest, middle])
        self.assertTrue(os.path.exists(today))

    def test_write_failure_does_not_raise_and_is_reported_once(self):
        blocked = os.path.join(self.tmp.name, "blocker")
        with open(blocked, "w") as handle:
            handle.write("a file where the folder should be")
        messages = []
        writer = logs.DailyLogWriter(os.path.join(blocked, "logs"), logs.LogSettings.from_data({}),
                                     clock=FakeClock(datetime.datetime(2026, 11, 28, 1, 0, 0)),
                                     on_error=messages.append)
        writer.write("Main", "one")
        writer.flush()
        writer.write("Main", "two")
        writer.flush()
        self.assertEqual(len(messages), 1)

    def test_error_callback_failure_is_swallowed(self):
        def boom(_text):
            raise RuntimeError("callback")
        writer = logs.DailyLogWriter(os.path.join(self.tmp.name, "x"), logs.LogSettings.from_data({}),
                                     on_error=boom)
        with mock.patch("os.makedirs", side_effect=OSError("nope")):
            writer.write("Main", "one")
            writer.flush()

    def test_read_and_export_round_trip(self):
        writer = self.writer(datetime.datetime(2026, 11, 28, 1, 0, 0))
        line = logs.format_line("2026-11-28 01:00:00", "Main", "ROLL", "Rolling 5")
        writer.write("Main", line)
        writer.flush()
        lines = logs.read_log_lines(self.folder, profile="Main", days=1, today=datetime.date(2026, 11, 28))
        self.assertEqual(lines, [line])
        target = os.path.join(self.tmp.name, "export.txt")
        self.assertTrue(logs.save_export(target, logs.filter_lines(lines, kind="ROLL")))
        with open(target, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), line + "\n")


if __name__ == "__main__":
    unittest.main()
