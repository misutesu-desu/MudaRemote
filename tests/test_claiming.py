import asyncio
import datetime
import time
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot
from mudae_core.claiming import (
    ClaimOutcome,
    basic_panic_claim_fallback_is_active,
    can_spend_restore_on_character,
    classify_claim_owner,
    classify_claim_text,
    cooldown_deadline,
    has_free_claim_button,
    is_claim_announcement_for_character,
)


class _Style:
    def __init__(self, value):
        self.value = value


class _Emoji:
    def __init__(self, name):
        self.name = name


class _Button:
    def __init__(self, emoji, style):
        self.emoji = _Emoji(emoji)
        self.style = _Style(style)


class _Row:
    def __init__(self, *children):
        self.children = children


class ClaimingTests(unittest.TestCase):
    def test_green_heart_button_is_a_free_claim(self):
        self.assertTrue(has_free_claim_button([_Row(_Button("heart", 3))], ["heart"]))

    def test_non_green_or_non_claim_button_is_not_a_free_claim(self):
        self.assertFalse(has_free_claim_button([_Row(_Button("heart", 1))], ["heart"]))
        self.assertFalse(has_free_claim_button([_Row(_Button("kakeraP", 3))], ["heart"]))

    def test_standard_confirmation_recognizes_username(self):
        evidence = classify_claim_text(
            "**Maliss** and **Satella** are now married!",
            "Satella",
            ["maliss", "Maliss Display"],
            user_id=123,
        )
        self.assertEqual(evidence.outcome, ClaimOutcome.SUCCESS)

    def test_hyperlink_confirmation_recognizes_display_name(self):
        evidence = classify_claim_text(
            "[Maliss Display](https://example.invalid/u) claimed [Shoko Ieiri](https://example.invalid/c)",
            "Shoko Ieiri",
            ["maliss", "Maliss Display"],
        )
        self.assertEqual(evidence.outcome, ClaimOutcome.SUCCESS)

    def test_confirmation_recognizes_discord_mention(self):
        evidence = classify_claim_text(
            "<@123> claimed **Satella**",
            "Satella",
            ["renamed-user"],
            user_id=123,
        )
        self.assertEqual(evidence.outcome, ClaimOutcome.SUCCESS)

    def test_other_winner_is_failure(self):
        evidence = classify_claim_text(
            "**Someone Else** and **Satella** are now married!",
            "Satella",
            ["maliss"],
        )
        self.assertEqual(evidence.outcome, ClaimOutcome.FAILURE)
        self.assertEqual(evidence.winner, "Someone Else")

    def test_claim_announcement_detection_excludes_forcedivorce_prompts(self):
        self.assertTrue(is_claim_announcement_for_character(
            "**Someone Else** and **Yoruichi Shihoin** are now married!",
            "Yoruichi Shihoin",
        ))
        self.assertFalse(is_claim_announcement_for_character(
            "Makima belongs to someone else, do you want to force the divorce?",
            "Makima",
        ))

    def test_unrelated_text_stays_inconclusive(self):
        evidence = classify_claim_text("You have 13 rolls left", "Satella", ["maliss"])
        self.assertEqual(evidence.outcome, ClaimOutcome.INCONCLUSIVE)

    def test_character_name_equal_to_display_name_is_not_false_success(self):
        evidence = classify_claim_text("**Someone Else** and **Satella** are now married!", "Satella", ["Satella"])
        self.assertEqual(evidence.outcome, ClaimOutcome.FAILURE)

    def test_edited_embed_owner_is_authoritative(self):
        self.assertEqual(
            classify_claim_owner("Maliss Display", ["maliss", "Maliss Display"]).outcome,
            ClaimOutcome.SUCCESS,
        )
        self.assertEqual(
            classify_claim_owner("Someone Else", ["maliss"]).outcome,
            ClaimOutcome.FAILURE,
        )

    def test_cooldown_deadline_does_not_truncate_seconds(self):
        now = datetime.datetime(2026, 7, 13, 14, 52, 51, tzinfo=datetime.timezone.utc)
        deadline = cooldown_deadline(now, 42)
        self.assertEqual(deadline, datetime.datetime(2026, 7, 13, 15, 34, 53, tzinfo=datetime.timezone.utc))

    def test_restore_keeps_the_base_value_floor_for_panic_only_candidates(self):
        self.assertFalse(can_spend_restore_on_character(55, 700, False, False))
        self.assertFalse(can_spend_restore_on_character(55, 700, True, False))
        self.assertTrue(can_spend_restore_on_character(55, 700, True, True))
        self.assertTrue(can_spend_restore_on_character(700, 700, False, False))

    def test_basic_panic_fallback_is_limited_to_an_enabled_final_round_with_claim_right(self):
        now = datetime.datetime(2026, 9, 2, 12, tzinfo=datetime.timezone.utc)
        self.assertTrue(basic_panic_claim_fallback_is_active(
            enabled=True,
            claim_right_available=True,
            next_claim_reset_at_utc=now + datetime.timedelta(minutes=30),
            now_utc=now,
        ))
        self.assertFalse(basic_panic_claim_fallback_is_active(
            enabled=True,
            claim_right_available=True,
            next_claim_reset_at_utc=now + datetime.timedelta(minutes=61),
            now_utc=now,
        ))
        self.assertFalse(basic_panic_claim_fallback_is_active(
            enabled=False,
            claim_right_available=True,
            next_claim_reset_at_utc=now + datetime.timedelta(minutes=30),
            now_utc=now,
        ))
        self.assertFalse(basic_panic_claim_fallback_is_active(
            enabled=True,
            claim_right_available=False,
            next_claim_reset_at_utc=now + datetime.timedelta(minutes=30),
            now_utc=now,
        ))


class _MockLoop:
    def __init__(self):
        self._loop = asyncio.get_event_loop()
        self.created_tasks = []

    def call_later(self, delay, callback, *args):
        return self._loop.call_later(delay, callback, *args)

    def create_task(self, coro):
        task = self._loop.create_task(coro)
        self.created_tasks.append(task)
        return task


class _MockBot:
    def __init__(self, user_id=7001):
        self.loop = _MockLoop()
        self.user = SimpleNamespace(
            id=user_id,
            name=f"test-{user_id}",
            display_name=f"test-{user_id}",
        )
        self.events = {}
        self._fetched_channels = {}

    def event(self, fn):
        self.events[fn.__name__] = fn
        return fn

    def run(self, token, reconnect=True):
        return None

    def is_closed(self):
        return False

    def get_channel(self, channel_id):
        return None

    async def fetch_channel(self, channel_id):
        return None


def _build_test_bot():
    bot = _MockBot()
    mudae_bot._mobile_runtime_stop_event.clear()
    with mock.patch.object(mudae_bot.commands, "Bot", return_value=bot):
        mudae_bot.run_bot(
            token="dummy-token",
            prefix="!",
            target_channel_id=1234,
            roll_command="wa",
            min_kakera=300,
            delay_seconds=0,
            mudae_prefix="$",
            log_function=lambda *a, **k: None,
            preset_name="test-claim-interaction",
            key_mode=False,
            start_delay=0,
            snipe_mode=True,
            snipe_delay=0,
            snipe_ignore_min_kakera_reset=False,
            wishlist=[],
            series_snipe_mode=False,
            series_snipe_delay=0,
            series_wishlist=[],
            roll_speed=1.0,
            kakera_snipe_mode_preset=False,
            kakera_snipe_threshold_preset=0,
            enable_reactive_self_snipe_preset=False,
            rolling_enabled=False,
            kakera_reaction_snipe_mode_preset=False,
            kakera_reaction_snipe_delay_preset=0,
            kakera_reaction_snipe_targets=[],
        )
    bot._claim_evidence_event = asyncio.Event()
    return bot


class ClaimInteractionRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = _build_test_bot()
        self.msg = SimpleNamespace(id=5555, channel=SimpleNamespace(id=1234), embeds=[])
        self.btn = SimpleNamespace(custom_id="btn_1", disabled=False)

    async def test_send_claim_click_returns_immediately_when_gateway_evidence_arrives_during_ack_wait(self):
        click_started = asyncio.Event()
        ack_release = asyncio.get_event_loop().create_future()
        click_count = 0

        async def slow_click():
            nonlocal click_count
            click_count += 1
            click_started.set()
            await ack_release

        self.btn.click = slow_click

        pending = self.bot._runtime_prepare_pending_claim(
            self.msg, "Rem", True, 300, "Re:Zero", True, False
        )

        async def deliver():
            await click_started.wait()
            evidence_msg = SimpleNamespace(
                author=SimpleNamespace(id=mudae_bot.TARGET_BOT_ID),
                content=f"**{self.bot.user.name}** and **Rem** are now married!",
                channel=SimpleNamespace(id=1234),
                embeds=[],
            )
            self.bot._runtime_record_claim_text_evidence(evidence_msg)

        asyncio.create_task(deliver())
        try:
            click_sent, response_observed = await asyncio.wait_for(
                self.bot._runtime_send_claim_click(self.btn, pending),
                timeout=1.0,
            )
            self.assertTrue(click_sent)
            self.assertTrue(response_observed)
            self.assertFalse(ack_release.done())
            self.assertEqual(click_count, 1)
            self.assertIsNotNone(getattr(self.bot, "_claim_text_evidence", None))
            self.assertEqual(self.bot._claim_text_evidence.outcome, ClaimOutcome.SUCCESS)
        finally:
            if not ack_release.done():
                ack_release.set_result(True)

    async def test_send_claim_click_times_out_and_flags_delayed_ack_when_no_evidence_arrives(self):
        click_started = asyncio.Event()
        ack_release = asyncio.get_event_loop().create_future()
        click_count = 0

        async def slow_click():
            nonlocal click_count
            click_count += 1
            click_started.set()
            await ack_release

        self.btn.click = slow_click

        pending = self.bot._runtime_prepare_pending_claim(
            self.msg, "RemHang", True, 300, "Re:Zero", True, False
        )

        try:
            click_sent, response_observed = await asyncio.wait_for(
                self.bot._runtime_send_claim_click(self.btn, pending, timeout=0.04),
                timeout=1.0,
            )
            self.assertTrue(click_sent)
            self.assertFalse(response_observed)
            self.assertEqual(click_count, 1)
            self.assertFalse(ack_release.done())
        finally:
            if not ack_release.done():
                ack_release.set_result(True)

    async def test_send_claim_click_prioritizes_conclusive_evidence_over_click_error_to_avoid_duplicate(self):
        click_started = asyncio.Event()
        error_release = asyncio.get_event_loop().create_future()
        click_count = 0

        async def err_click():
            nonlocal click_count
            click_count += 1
            click_started.set()
            await error_release
            raise RuntimeError("Discord HTTP 500")

        self.btn.click = err_click

        pending = self.bot._runtime_prepare_pending_claim(
            self.msg, "RemErr", True, 300, "Re:Zero", True, False
        )

        async def deliver():
            await click_started.wait()
            evidence_msg = SimpleNamespace(
                author=SimpleNamespace(id=mudae_bot.TARGET_BOT_ID),
                content=f"**{self.bot.user.name}** and **RemErr** are now married!",
                channel=SimpleNamespace(id=1234),
                embeds=[],
            )
            self.bot._runtime_record_claim_text_evidence(evidence_msg)
            error_release.set_result(True)

        asyncio.create_task(deliver())
        try:
            click_sent, response_observed = await asyncio.wait_for(
                self.bot._runtime_send_claim_click(self.btn, pending),
                timeout=1.0,
            )
            self.assertTrue(click_sent)
            self.assertTrue(response_observed)
            self.assertEqual(click_count, 1)
        finally:
            if not error_release.done():
                error_release.set_result(True)

    async def test_send_claim_click_raises_click_error_when_no_evidence_so_caller_can_retry(self):
        click_count = 0

        async def err_click():
            nonlocal click_count
            click_count += 1
            raise RuntimeError("Discord HTTP 500")

        self.btn.click = err_click

        pending = self.bot._runtime_prepare_pending_claim(
            self.msg, "RemRetry", True, 300, "Re:Zero", True, False
        )
        with self.assertRaises(RuntimeError):
            await self.bot._runtime_send_claim_click(self.btn, pending)
        self.assertEqual(click_count, 1)

    async def test_send_claim_click_caller_cancellation_cleans_up_event_waiter_and_keeps_click_alive(self):
        click_started = asyncio.Event()
        click_release = asyncio.get_event_loop().create_future()
        click_cancelled = False

        async def hang_click():
            nonlocal click_cancelled
            click_started.set()
            try:
                await click_release
            except asyncio.CancelledError:
                click_cancelled = True
                raise

        self.btn.click = hang_click

        pending = self.bot._runtime_prepare_pending_claim(
            self.msg, "RemCancel", True, 300, "Re:Zero", True, False
        )
        task = asyncio.create_task(
            self.bot._runtime_send_claim_click(self.btn, pending, timeout=2.0)
        )
        await click_started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        self.assertFalse(click_cancelled)

        waiter_tasks = [t for t in self.bot.loop.created_tasks if t is not task]
        for wt in waiter_tasks:
            if wt.get_coro().__name__ != "guarded_click":
                self.assertTrue(wt.done(), f"Waiter task {wt} was not cleaned up")

        loop_exceptions = []
        loop = asyncio.get_event_loop()
        orig_handler = loop.get_exception_handler()

        def custom_handler(_loop, context):
            loop_exceptions.append(context)

        loop.set_exception_handler(custom_handler)
        click_tasks = [t for t in waiter_tasks if t.get_coro().__name__ == "guarded_click"]
        try:
            click_release.set_exception(RuntimeError("late error after cancel"))
            if click_tasks:
                await asyncio.wait(click_tasks)
                for ct in click_tasks:
                    self.assertTrue(ct.done())
                    self.assertIsInstance(ct.exception(), RuntimeError)
            self.assertEqual(loop_exceptions, [])
        finally:
            loop.set_exception_handler(orig_handler)

    async def test_send_claim_click_accepts_cooldown_rejection_as_conclusive_response_evidence(self):
        click_started = asyncio.Event()
        ack_release = asyncio.get_event_loop().create_future()

        async def slow_click():
            click_started.set()
            await ack_release

        self.btn.click = slow_click

        pending = self.bot._runtime_prepare_pending_claim(
            self.msg, "RemCD", True, 300, "Re:Zero", True, False
        )

        async def deliver_cooldown():
            await click_started.wait()
            pending["rejected_by_cooldown"] = True
            self.bot._claim_evidence_event.set()

        asyncio.create_task(deliver_cooldown())
        try:
            click_sent, response_observed = await asyncio.wait_for(
                self.bot._runtime_send_claim_click(self.btn, pending),
                timeout=1.0,
            )
            self.assertTrue(click_sent)
            self.assertTrue(response_observed)
            self.assertFalse(ack_release.done())
        finally:
            if not ack_release.done():
                ack_release.set_result(True)

    async def test_send_claim_click_ignores_spurious_event_until_real_evidence_arrives(self):
        click_started = asyncio.Event()
        ack_release = asyncio.get_event_loop().create_future()

        async def slow_click():
            click_started.set()
            await ack_release

        self.btn.click = slow_click

        pending = self.bot._runtime_prepare_pending_claim(
            self.msg, "RemSpurious", True, 300, "Re:Zero", True, False
        )

        async def deliver():
            await click_started.wait()
            # Fire spurious event without any evidence
            self.bot._claim_evidence_event.set()
            await asyncio.sleep(0)
            # Deliver real evidence
            evidence_msg = SimpleNamespace(
                author=SimpleNamespace(id=mudae_bot.TARGET_BOT_ID),
                content=f"**{self.bot.user.name}** and **RemSpurious** are now married!",
                channel=SimpleNamespace(id=1234),
                embeds=[],
            )
            self.bot._runtime_record_claim_text_evidence(evidence_msg)

        asyncio.create_task(deliver())
        try:
            click_sent, response_observed = await asyncio.wait_for(
                self.bot._runtime_send_claim_click(self.btn, pending),
                timeout=1.0,
            )
            self.assertTrue(click_sent)
            self.assertTrue(response_observed)
            self.assertFalse(ack_release.done())
        finally:
            if not ack_release.done():
                ack_release.set_result(True)

    async def test_send_claim_click_does_not_accept_evidence_for_different_pending(self):
        click_started = asyncio.Event()
        ack_release = asyncio.get_event_loop().create_future()

        async def slow_click():
            click_started.set()
            await ack_release

        self.btn.click = slow_click

        _other_pending = self.bot._runtime_prepare_pending_claim(
            self.msg, "OtherChar", True, 300, "OtherSeries", True, False
        )
        pending_target = {"character_name": "TargetChar", "finalized": False}

        async def deliver():
            await click_started.wait()
            evidence_msg = SimpleNamespace(
                author=SimpleNamespace(id=mudae_bot.TARGET_BOT_ID),
                content=f"**{self.bot.user.name}** and **OtherChar** are now married!",
                channel=SimpleNamespace(id=1234),
                embeds=[],
            )
            self.bot._runtime_record_claim_text_evidence(evidence_msg)

        asyncio.create_task(deliver())
        try:
            click_sent, response_observed = await asyncio.wait_for(
                self.bot._runtime_send_claim_click(self.btn, pending_target, timeout=0.04),
                timeout=1.0,
            )
            self.assertTrue(click_sent)
            self.assertFalse(response_observed)
        finally:
            if not ack_release.done():
                ack_release.set_result(True)

    async def test_verify_snipe_outcome_rechecks_text_evidence_after_slow_fetch_and_deadline(self):
        self.bot.claim_right_available = True
        pending = self.bot._runtime_prepare_pending_claim(
            self.msg, "RemSlow", False, 300, "Re:Zero", True, False
        )

        real_monotonic = time.monotonic
        fake_now = [real_monotonic()]

        def mock_monotonic():
            return fake_now[0]

        fetch_started = asyncio.Event()
        fetch_release = asyncio.Event()

        class _SlowChannel:
            def __init__(self):
                self.id = 1234

            async def fetch_message(self, msg_id):
                fetch_started.set()
                await fetch_release.wait()
                fake_now[0] += 2.0
                embed = SimpleNamespace(
                    footer=None,
                    author=SimpleNamespace(name="RemSlow"),
                    image=SimpleNamespace(url="http://example.com/img.png"),
                    thumbnail=None,
                    description="Re:Zero",
                )
                return SimpleNamespace(id=msg_id, embeds=[embed])

            async def history(self, limit=20):
                if False:
                    yield None

        async def deliver():
            await fetch_started.wait()
            evidence_msg = SimpleNamespace(
                author=SimpleNamespace(id=mudae_bot.TARGET_BOT_ID),
                content=f"**{self.bot.user.name}** and **RemSlow** are now married!",
                channel=SimpleNamespace(id=1234),
                embeds=[],
            )
            self.bot._runtime_record_claim_text_evidence(evidence_msg)
            fetch_release.set()

        asyncio.create_task(deliver())
        mock_time = SimpleNamespace(
            monotonic=mock_monotonic,
            time=time.time,
            sleep=time.sleep,
        )
        with mock.patch.object(mudae_bot, "time", mock_time):
            self.assertIs(time.monotonic, real_monotonic)
            outcome = await asyncio.wait_for(
                self.bot._runtime_verify_snipe_outcome(self.bot, _SlowChannel(), self.msg, pending),
                timeout=1.0,
            )
        self.assertEqual(outcome, ClaimOutcome.SUCCESS)
    async def test_verify_snipe_outcome_does_not_lose_wakeup_for_evidence_arriving_during_fetch(self):
        pending = self.bot._runtime_prepare_pending_claim(
            self.msg, "RemFast", True, 300, "Re:Zero", True, False
        )

        fetch_started = asyncio.Event()
        fetch_release = asyncio.Event()
        fetch_count = 0
        history_called = False

        class _FastChannel:
            def __init__(self):
                self.id = 1234

            async def fetch_message(self, msg_id):
                nonlocal fetch_count
                fetch_count += 1
                fetch_started.set()
                await fetch_release.wait()
                embed = SimpleNamespace(
                    footer=None,
                    author=SimpleNamespace(name="RemFast"),
                    image=SimpleNamespace(url="http://example.com/img.png"),
                    thumbnail=None,
                    description="Re:Zero",
                )
                return SimpleNamespace(id=msg_id, embeds=[embed])

            async def history(self, limit=20):
                nonlocal history_called
                history_called = True
                if False:
                    yield None

        async def deliver():
            await fetch_started.wait()
            evidence_msg = SimpleNamespace(
                author=SimpleNamespace(id=mudae_bot.TARGET_BOT_ID),
                content=f"**{self.bot.user.name}** and **RemFast** are now married!",
                channel=SimpleNamespace(id=1234),
                embeds=[],
            )
            self.bot._runtime_record_claim_text_evidence(evidence_msg)
            fetch_release.set()

        asyncio.create_task(deliver())
        outcome = await asyncio.wait_for(
            self.bot._runtime_verify_snipe_outcome(self.bot, _FastChannel(), self.msg, pending),
            timeout=2.0,
        )
        self.assertEqual(outcome, ClaimOutcome.SUCCESS)
        self.assertFalse(history_called)
        self.assertEqual(fetch_count, 1)
    async def test_verify_snipe_outcome_failure_evidence_does_not_finalize_success(self):
        pending = self.bot._runtime_prepare_pending_claim(
            self.msg, "RemFail", True, 300, "Re:Zero", True, False
        )

        fetch_started = asyncio.Event()
        fetch_release = asyncio.Event()

        class _Channel:
            def __init__(self):
                self.id = 1234

            async def fetch_message(self, msg_id):
                fetch_started.set()
                await fetch_release.wait()
                embed = SimpleNamespace(
                    footer=None,
                    author=SimpleNamespace(name="RemFail"),
                    image=SimpleNamespace(url="http://example.com/img.png"),
                    thumbnail=None,
                    description="Re:Zero",
                )
                return SimpleNamespace(id=msg_id, embeds=[embed])

            async def history(self, limit=20):
                if False:
                    yield None

        async def deliver_failure():
            await fetch_started.wait()
            evidence_msg = SimpleNamespace(
                author=SimpleNamespace(id=mudae_bot.TARGET_BOT_ID),
                content="**Someone Else** and **RemFail** are now married!",
                channel=SimpleNamespace(id=1234),
                embeds=[],
            )
            self.bot._runtime_record_claim_text_evidence(evidence_msg)
            fetch_release.set()

        asyncio.create_task(deliver_failure())
        outcome = await asyncio.wait_for(
            self.bot._runtime_verify_snipe_outcome(self.bot, _Channel(), self.msg, pending),
            timeout=1.0,
        )
        self.assertEqual(outcome, ClaimOutcome.FAILURE)
        self.assertFalse(pending.get("finalized"))
        self.assertIsNone(self.bot.pending_claim)

if __name__ == "__main__":
    unittest.main()
