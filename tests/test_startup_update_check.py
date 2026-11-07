import io
import unittest
from unittest import mock

import mudae_bot


class _StopAfterUpdateStep(Exception):
    pass


class ConsoleStartupUpdateCheckTests(unittest.TestCase):
    def _run_cli_until_args(self, check_enabled):
        with mock.patch.object(mudae_bot, "load_desktop_presets"), \
                mock.patch.object(mudae_bot, "console_supports_colors"), \
                mock.patch.object(mudae_bot, "cleanup_after_update") as cleanup, \
                mock.patch.object(mudae_bot, "check_for_updates", return_value=None) as check, \
                mock.patch.object(mudae_bot, "load_startup_update_check_setting", return_value=check_enabled), \
                mock.patch.object(mudae_bot, "print_system_log"), \
                mock.patch.object(mudae_bot, "parse_args", side_effect=_StopAfterUpdateStep):
            with self.assertRaises(_StopAfterUpdateStep):
                mudae_bot.run_cli([])
        return cleanup, check

    def test_startup_skips_the_update_check_when_it_is_turned_off(self):
        cleanup, check = self._run_cli_until_args(check_enabled=False)
        check.assert_not_called()
        cleanup.assert_called_once()

    def test_startup_checks_for_updates_by_default(self):
        _, check = self._run_cli_until_args(check_enabled=True)
        check.assert_called_once()

    def _answer(self, text):
        stdin = mock.Mock()
        stdin.isatty.return_value = True
        with mock.patch.object(mudae_bot.sys, "stdin", stdin), \
                mock.patch("builtins.input", return_value=text), \
                mock.patch("sys.stdout", new_callable=io.StringIO), \
                mock.patch.object(mudae_bot, "print_system_log"), \
                mock.patch.object(mudae_bot, "save_startup_update_check_setting") as save:
            result = mudae_bot._confirm_update_in_console("9.9.9", "notes")
        return result, save

    def test_answering_off_skips_the_update_and_turns_the_check_off(self):
        result, save = self._answer("off")
        self.assertFalse(result)
        save.assert_called_once_with(False)

    def test_other_answers_leave_the_setting_alone(self):
        result, save = self._answer("y")
        self.assertTrue(result)
        save.assert_not_called()
        result, save = self._answer("")
        self.assertFalse(result)
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
