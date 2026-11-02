import unittest
from unittest import mock

import mudae_bot


class ConsoleColorTests(unittest.TestCase):
    def test_console_with_colors_off_gets_them_switched_on(self):
        set_mode = mock.Mock(return_value=1)
        self.assertTrue(mudae_bot._switch_on_console_colors(lambda: 0x3, set_mode))
        set_mode.assert_called_once_with(0x7)

    def test_console_with_colors_on_is_left_alone(self):
        set_mode = mock.Mock()
        self.assertTrue(mudae_bot._switch_on_console_colors(lambda: 0x7, set_mode))
        set_mode.assert_not_called()

    def test_redirected_output_is_left_alone(self):
        set_mode = mock.Mock()
        self.assertTrue(mudae_bot._switch_on_console_colors(lambda: None, set_mode))
        set_mode.assert_not_called()

    def test_console_refusing_colors_is_reported(self):
        self.assertFalse(mudae_bot._switch_on_console_colors(lambda: 0x3, lambda _mode: 0))

    def _logged_line(self, supported):
        with mock.patch.object(mudae_bot, "console_supports_colors", return_value=supported), \
                mock.patch("builtins.print") as printed, \
                mock.patch("builtins.open", mock.mock_open()):
            mudae_bot.BotLogger.log("RT: Ready", "preset", "INFO")
        return printed.call_args.args[0]

    def test_log_line_has_no_raw_codes_when_colors_are_refused(self):
        line = self._logged_line(False)
        self.assertIn("RT: Ready", line)
        self.assertNotIn("\033", line)

    def test_log_line_keeps_colors_when_supported(self):
        self.assertTrue(self._logged_line(True).startswith("\033[94m"))


if __name__ == "__main__":
    unittest.main()
