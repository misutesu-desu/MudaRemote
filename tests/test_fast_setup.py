import asyncio
import os
import tempfile
import unittest

from mudae_core.account_state import AccountStateStore
from mudae_core.config import ensure_profile_ids, rename_profile
from mudae_core.fast_setup import (
    FAST_SETUP_MESSAGE, FastSetup, fast_setup_message, rearm, validate_fast_setup_settings,
)
from mudae_core.totals import account_key


class _Sender:
    def __init__(self, result=True):
        self.sent = []
        self.result = result

    async def __call__(self, channel, text):
        if isinstance(self.result, Exception):
            raise self.result
        self.sent.append((channel, text))
        return self.result


def run(coro):
    return asyncio.run(coro)


class FastSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "state.json")
        self.presets = {"Main": {"fast_setup": True}}
        ensure_profile_ids(self.presets)
        self.key = account_key(self.presets["Main"]["profile_id"], 1)

    def tearDown(self):
        self.tmp.cleanup()

    def test_message_is_the_owners_exact_text(self):
        self.assertEqual(
            FAST_SETUP_MESSAGE,
            "$ta claim rolls daily jump kakerareact kakerapower kakerainfo kakerastock jump rt dk vote "
            "jump oh spherestock perk9b perk8 perk8b perk9 omegakeys shop6",
        )
        self.assertEqual(fast_setup_message("$"), FAST_SETUP_MESSAGE)
        self.assertTrue(fast_setup_message("!").startswith("!ta claim rolls"))

    def test_sent_once_then_off(self):
        setup = FastSetup(AccountStateStore(self.path), self.key)
        send = _Sender()
        self.assertTrue(run(setup.run(True, 0, send, "chan")))
        self.assertFalse(run(setup.run(True, 0, send, "chan")))
        self.assertEqual(send.sent, [("chan", FAST_SETUP_MESSAGE)])
        self.assertFalse(setup.effective_enabled(True, 0))

    def test_off_setting_sends_nothing(self):
        send = _Sender()
        self.assertFalse(run(FastSetup(AccountStateStore(self.path), self.key).run(False, 0, send, "c")))
        self.assertEqual(send.sent, [])

    def test_survives_restart_and_reload(self):
        run(FastSetup(AccountStateStore(self.path), self.key).run(True, 0, _Sender(), "c"))
        send = _Sender()
        fresh = FastSetup(AccountStateStore(self.path), self.key)  # a new process
        self.assertFalse(run(fresh.run(True, 0, send, "c")))
        self.assertEqual(send.sent, [])

    def test_survives_rename(self):
        run(FastSetup(AccountStateStore(self.path), self.key).run(True, 0, _Sender(), "c"))
        rename_profile(self.presets, "Main", "Renamed")
        key = account_key(self.presets["Renamed"]["profile_id"], 1)
        self.assertEqual(key, self.key)
        send = _Sender()
        self.assertFalse(run(FastSetup(AccountStateStore(self.path), key).run(True, 0, send, "c")))
        self.assertEqual(send.sent, [])

    def test_each_account_of_a_profile_is_separate(self):
        store = AccountStateStore(self.path)
        run(FastSetup(store, self.key).run(True, 0, _Sender(), "c"))
        second = account_key(self.presets["Main"]["profile_id"], 2)
        self.assertTrue(FastSetup(store, second).is_due(True, 0))

    def test_send_again_rearms_once(self):
        store = AccountStateStore(self.path)
        setup = FastSetup(store, self.key)
        send = _Sender()
        run(setup.run(True, 0, send, "c"))
        data = rearm({"fast_setup": False, "fast_setup_round": 0})
        self.assertEqual(data, {"fast_setup": True, "fast_setup_round": 1})
        self.assertTrue(run(setup.run(data["fast_setup"], data["fast_setup_round"], send, "c")))
        self.assertFalse(run(setup.run(data["fast_setup"], data["fast_setup_round"], send, "c")))
        self.assertEqual(len(send.sent), 2)

    def test_not_sent_now_is_retried_later(self):
        setup = FastSetup(AccountStateStore(self.path), self.key)
        self.assertFalse(run(setup.run(True, 0, _Sender(result=False), "c")))
        self.assertTrue(setup.is_due(True, 0))
        self.assertTrue(run(setup.run(True, 0, _Sender(), "c")))

    def test_uncertain_send_is_never_repeated(self):
        setup = FastSetup(AccountStateStore(self.path), self.key)
        self.assertFalse(run(setup.run(True, 0, _Sender(result=RuntimeError("net")), "c")))
        self.assertFalse(setup.is_due(True, 0))

    def test_validation(self):
        self.assertEqual(validate_fast_setup_settings({"fast_setup_round": 2}), [])
        self.assertTrue(validate_fast_setup_settings({"fast_setup_round": -1}))
        self.assertTrue(validate_fast_setup_settings({"fast_setup_round": True}))


if __name__ == "__main__":
    unittest.main()
