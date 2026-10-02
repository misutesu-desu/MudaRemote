"""Cloud event logs keep ordinary sentences readable and still hide anything token-like."""
import unittest

from mudae_core.bot_runtime import _redact_credentials


class LogRedactionTests(unittest.TestCase):
    def test_event_log_keeps_sentences_but_still_hides_tokens(self):
        sentence = "Checking $tu... (reason: status-boundary) after the Mudae reset. Next."
        self.assertEqual(_redact_credentials(sentence), sentence)
        # Built from parts so secret scanners do not mistake this fixture for a real token.
        token = ".".join(("MTIzNDU2Nzg5MDEyMzQ1Njc4", "GabcDE", "abcdefghijklmnopqrstuvwxyz0123456789"))
        self.assertEqual(_redact_credentials(token), "[REDACTED_TOKEN]")


if __name__ == '__main__':
    unittest.main()
