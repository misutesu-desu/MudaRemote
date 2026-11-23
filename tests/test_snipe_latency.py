import asyncio
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot
from tests.test_kakera_snipe_ownership import _build_roll_message, _create_test_client


def _closure_cell(function, name):
    return dict(zip(function.__code__.co_freevars, function.__closure__))[name]


def _add_claim_button(message, bot, on_click):
    button = SimpleNamespace(
        emoji=SimpleNamespace(name=bot.claim_emojis[0]),
        custom_id=f"{message.id}_claim",
        disabled=False,
        style=SimpleNamespace(value=2),
        click=mock.AsyncMock(side_effect=on_click),
    )
    message.components.append(SimpleNamespace(children=[button]))
    return button


def _prepare(bot, **options):
    bot.claim_right_available = True
    bot.wishlist = ["rem"]
    for key, value in options.items():
        setattr(bot, key, value)
    verify = mock.AsyncMock(return_value=mudae_bot.ClaimOutcome.FAILURE)
    _closure_cell(bot._runtime_claim_character, "verify_snipe_outcome").cell_contents = verify


class SnipeLatencyTests(unittest.IsolatedAsyncioTestCase):
    def _run_claim_clicks_for_real(self, bot):
        # The shared fake loop drops tasks; a claim click needs a real one.
        tasks = []

        def create_task(coroutine):
            task = asyncio.get_running_loop().create_task(coroutine)
            tasks.append(task)
            return task

        bot.loop.create_task = create_task

        def cancel_leftovers():
            for task in tasks:
                task.cancel()

        self.addCleanup(cancel_leftovers)

    async def test_zero_snipe_delay_claims_without_any_wait(self):
        bot, channel = _create_test_client()
        _prepare(bot)
        self._run_claim_clicks_for_real(bot)
        message, _ = _build_roll_message(channel, 3001, 9001, "someone", client=bot)
        message.components = []
        waits = []
        waits_before_click = []

        async def record_click():
            waits_before_click.extend(waits)

        claim_button = _add_claim_button(message, bot, record_click)

        async def fake_sleep(_client, seconds, abort_on_pause=False):
            waits.append(seconds)
            return True

        with mock.patch.object(mudae_bot, "pause_interruptible_sleep", side_effect=fake_sleep):
            await bot.events["on_message"](message)

        claim_button.click.assert_awaited_once()
        self.assertEqual([seconds for seconds in waits_before_click if seconds > 0], [])

    async def test_positive_snipe_delay_is_still_honoured(self):
        bot, channel = _create_test_client(snipe_delay=1.5)
        _prepare(bot)
        self._run_claim_clicks_for_real(bot)
        message, _ = _build_roll_message(channel, 3002, 9001, "someone", client=bot)
        message.components = []
        waits = []
        waits_before_click = []

        async def record_click():
            waits_before_click.extend(waits)

        _add_claim_button(message, bot, record_click)

        async def fake_sleep(_client, seconds, abort_on_pause=False):
            waits.append(seconds)
            return True

        with mock.patch.object(mudae_bot, "pause_interruptible_sleep", side_effect=fake_sleep):
            await bot.events["on_message"](message)

        self.assertEqual(len(waits_before_click), 1)
        self.assertGreaterEqual(waits_before_click[0], 1.5)

    async def test_kakera_collection_on_other_rolls_does_not_hold_back_the_character_snipe(self):
        bot, channel = _create_test_client(
            kakera_reaction_snipe_mode_preset=True,
            kakera_reaction_snipe_delay=0.75,
        )
        _prepare(bot)
        self._run_claim_clicks_for_real(bot)
        message, kakera_button = _build_roll_message(channel, 3003, 9001, "someone", client=bot)
        claim_clicked = asyncio.Event()

        async def mark_claim():
            claim_clicked.set()

        claim_button = _add_claim_button(message, bot, mark_claim)
        observed = {}

        async def fake_sleep(_client, seconds, abort_on_pause=False):
            if seconds >= 0.75 and "claim_during_kakera_delay" not in observed:
                try:
                    await asyncio.wait_for(claim_clicked.wait(), 1.0)
                    observed["claim_during_kakera_delay"] = True
                except asyncio.TimeoutError:
                    observed["claim_during_kakera_delay"] = False
            return True

        with mock.patch.object(mudae_bot, "pause_interruptible_sleep", side_effect=fake_sleep):
            await bot.events["on_message"](message)

        claim_button.click.assert_awaited_once()
        kakera_button.click.assert_awaited_once()
        self.assertTrue(observed.get("claim_during_kakera_delay"))


if __name__ == "__main__":
    unittest.main()
