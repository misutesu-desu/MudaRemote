import asyncio
import datetime
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot


class _Handle:
    def __init__(self):
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def cancelled(self):
        return self._cancelled


class _Loop:
    def __init__(self):
        self.created_tasks = []

    def call_later(self, _delay, _callback, *_args):
        return _Handle()

    def create_task(self, coroutine):
        self.created_tasks.append(coroutine)
        coroutine.close()
        return None

    def create_future(self):
        return asyncio.Future()


class _Bot:
    def __init__(self, user_id=7001, user_name="snipe-bot"):
        self.loop = _Loop()
        self.user = SimpleNamespace(id=user_id, name=user_name, display_name=user_name)
        self.events = {}
        self._fetched_channels = {}

    def event(self, function):
        self.events[function.__name__] = function
        return function

    def run(self, _token, reconnect=True):
        return None

    def get_channel(self, channel_id):
        return self._fetched_channels.get(channel_id)

    async def fetch_channel(self, channel_id):
        return self._fetched_channels.get(channel_id)

    def is_closed(self):
        return False


class _Channel:
    def __init__(self, channel_id, client_getter):
        self.id = channel_id
        self.guild = SimpleNamespace(id=777)
        self.sent = []
        self._client_getter = client_getter

    async def send(self, content, **_kwargs):
        self.sent.append(content)
        return SimpleNamespace(id=8000 + len(self.sent), created_at=datetime.datetime.now(datetime.timezone.utc))

    async def history(self, limit=12, before=None):
        if False:
            yield None

    async def fetch_message(self, message_id):
        return None


def _create_test_client(
    *,
    rolling_enabled=False,
    kakera_reaction_snipe_mode_preset=False,
    kakera_reaction_snipe_targets=None,
    immediate_kakera_click_preset=True,
    enable_reactive_self_snipe_preset=False,
    **preset_options,
):
    bot = _Bot(user_id=7001, user_name="snipe-bot")
    mudae_bot._mobile_runtime_stop_event.clear()
    with mock.patch.object(mudae_bot.commands, "Bot", return_value=bot):
        mudae_bot.run_bot(
            preset_name="test-kakera-snipe-ownership",
            preset_data={
                "token": "dummy-token",
                "prefix": "!",
                "channel_id": 1234,
                "roll_command": "wa",
                "min_kakera": 300,
                "delay_seconds": 0,
                "mudae_prefix": "$",
                "key_mode": False,
                "start_delay": 0,
                "snipe_mode": True,
                "snipe_delay": 0,
                "snipe_ignore_min_kakera_reset": False,
                "wishlist": [],
                "series_snipe_mode": False,
                "series_snipe_delay": 0,
                "series_wishlist": [],
                "roll_speed": 1.0,
                "kakera_snipe_mode": False,
                "kakera_snipe_threshold": 0,
                "reactive_snipe_on_own_rolls": enable_reactive_self_snipe_preset,
                "rolling": rolling_enabled,
                "kakera_reaction_snipe_mode": kakera_reaction_snipe_mode_preset,
                "kakera_reaction_snipe_delay": 0,
                "kakera_reaction_snipe_targets": kakera_reaction_snipe_targets or [],
                "command_channel_id": "5678",
                "immediate_kakera_click": immediate_kakera_click_preset,
                "dk_power_management": True,
                "reactive_snipe_delay": 0.5,
                "auto_us_limit": 10,
                "auto_mk_enabled": False,
                "auto_rolls_limit": 10,
                **preset_options,
            },
            log_function=lambda *_args, **_kwargs: None,
        )

    client_getter = lambda: bot
    roll_channel = _Channel(1234, client_getter)
    bot._main_channel = roll_channel
    bot._fetched_channels[1234] = roll_channel
    bot.current_dk_power = 100
    bot.kakera_react_available = True
    bot.command_pacer.minimum_delay = 0
    bot.command_pacer.maximum_delay = 0
    bot.command_pacer._next_command_at = 0
    return bot, roll_channel


def _build_roll_message(channel, message_id, roll_owner_id, roll_owner_name, kakera_emoji="kakeraY", client=None):
    btn = SimpleNamespace(
        emoji=SimpleNamespace(name=kakera_emoji),
        custom_id=f"{message_id}_{kakera_emoji}",
        disabled=False,
        style=SimpleNamespace(value=2),
    )

    async def _mock_click():
        if client is not None:
            for waiters in list(client._kakera_result_waiters.values()):
                for w in list(waiters):
                    if not w.done():
                        w.set_result(150)

    btn.click = mock.AsyncMock(side_effect=_mock_click)

    embed = SimpleNamespace(
        author=SimpleNamespace(name="Rem"),
        image=SimpleNamespace(url="https://example.invalid/rem.png"),
        thumbnail=None,
        description=f"Re:Zero\n<:kakera:123> 150",
        footer=SimpleNamespace(text=None),
    )

    message = SimpleNamespace(
        id=message_id,
        channel=channel,
        author=SimpleNamespace(id=mudae_bot.TARGET_BOT_ID),
        content="",
        created_at=datetime.datetime.now(datetime.timezone.utc),
        embeds=[embed],
        components=[SimpleNamespace(children=[btn])],
        interaction=SimpleNamespace(
            user=SimpleNamespace(id=roll_owner_id, name=roll_owner_name),
            name="wa",
        ),
    )
    return message, btn


class KakeraSnipeOwnershipRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_light_breakdown_confirms_click_and_spends_power_once(self):
        bot, channel = _create_test_client()
        bot.current_dk_power = 46
        bot.dk_consumption = 15
        message, button = _build_roll_message(channel, 1008, bot.user.id, bot.user.name, "kakeraL2")
        result = SimpleNamespace(
            id=1009, channel=channel, author=message.author,
            content=("<:kakeraL:123> breaks down into <:kakera:456> + <:kakeraT:457> + "
                     "<:kakeraG:458> => **snipe-bot +1,234** ($k)"),
            created_at=message.created_at, embeds=[], components=[], interaction=None,
        )
        async def deliver_result():
            await bot.events["on_message"](result)
        button.click.side_effect = deliver_result
        with mock.patch.object(mudae_bot, "pause_interruptible_sleep", mock.AsyncMock(return_value=True)):
            await bot.events["on_message"](message)
            await bot.events["on_message"](message)
        button.click.assert_awaited_once()
        self.assertEqual(bot.current_dk_power, 31)
        self.assertFalse(bot.kakera_power_ledger.has_pending)
        self.assertFalse(bot._kakera_result_waiters)

    async def test_dk_threshold_refills_before_or_after_confirmed_click_without_tu(self):
        for power, trigger, stock, pending, enabled, management, expected in (
            (40, 30, 1, False, True, True, ["click", "$dk"]),
            (29, 30, 1, False, True, True, ["$dk", "click"]),
            (45, 30, 1, False, True, True, ["click"]),
            (25, 0, 1, False, True, True, ["click", "$dk"]),
            (40, 30, 0, False, True, True, ["click"]),
            (40, 30, 1, True, True, True, ["click"]),
            (40, 30, 1, False, False, True, ["click"]),
            (40, 30, 1, False, True, False, ["click"]),
        ):
            with self.subTest(power=power, trigger=trigger, stock=stock, pending=pending,
                              enabled=enabled, management=management):
                bot, channel = _create_test_client()
                bot.current_dk_power, bot.dk_consumption = power, 15
                bot.auto_dk_enabled, bot.dk_power_management = enabled, management
                bot.auto_dk_min_power, bot.dk_stock_count = trigger, stock
                command_channel = _Channel(5678, lambda: bot)
                bot._fetched_channels[5678] = command_channel
                if pending:
                    bot.kakera_power_ledger.reserve("kakeraW", 1)
                events = []
                send = command_channel.send
                async def record_command(content):
                    events.append(content)
                    return await send(content)
                command_channel.send = record_command
                message, button = _build_roll_message(channel, 1006, bot.user.id, bot.user.name)
                result = SimpleNamespace(
                    id=1007, channel=channel, author=message.author,
                    content="<:kakeraY:123> **snipe-bot +515** ($k)",
                    created_at=message.created_at, embeds=[], components=[], interaction=None,
                )
                async def deliver_result():
                    events.append("click")
                    await bot.events["on_message"](result)
                button.click.side_effect = deliver_result
                with mock.patch.object(mudae_bot, "pause_interruptible_sleep", mock.AsyncMock(return_value=True)):
                    await bot.events["on_message"](message)
                    await bot.events["on_message"](message)
                self.assertEqual(events, expected)
                self.assertEqual(channel.sent, [])
                self.assertEqual(bot.dk_stock_count, stock - expected.count("$dk"))
                expected_power = 100 if expected[-1] == "$dk" else (85 if expected[0] == "$dk" else power - 15)
                self.assertEqual(bot.current_dk_power, expected_power)
                button.click.assert_awaited_once()

    async def test_dark_transformation_confirms_click_without_retry(self):
        # Legacy presets may explicitly store optional collections as null.
        bot, channel = _create_test_client(
            avoid_list=None, snipe_channels=None, character_snipe_targets=None,
            auto_divorce_series=None, auto_divorce_blacklist=None,
            auto_divorce_blacklist_series=None, inactive_hours=None,
            kakera_power_thresholds=None,
        )
        message, btn = _build_roll_message(
            channel=channel,
            message_id=1010,
            roll_owner_id=bot.user.id,
            roll_owner_name=bot.user.name,
            kakera_emoji="kakeraD2",
        )
        bot.kakera_emojis = ["kakeraD"]
        bot.dk_consumption = 36
        result = SimpleNamespace(
            id=1011, channel=channel, author=message.author,
            content=(
                "<:kakeraD:123> turns into <:kakeraY:456>\n"
                "<:kakeraY:456> **snipe-bot +431** ($k)\n"
                "Consolation prize: **5%** discount on the react power used for this dark kakera."
            ),
            created_at=message.created_at, embeds=[], components=[],
            interaction=None,
        )

        async def deliver_result():
            await bot.events["on_message"](result)

        btn.click.side_effect = deliver_result
        await bot.events["on_message"](message)

        btn.click.assert_awaited_once()
        self.assertIn(message.id, bot.kakera_reaction_sniped_messages)
        self.assertFalse(bot.kakera_power_ledger.has_pending)
        self.assertEqual(bot.current_dk_power, 64)
        self.assertFalse(bot._kakera_result_waiters)
        self.assertIn("dark-kakera-result", mudae_bot.status_refresh_reasons(bot))

    async def test_1_snipe_only_disabled_auto_kakera_still_collects_own_kakera(self):
        """TEST 1: In snipe-only mode with Auto-Collect Kakera OFF, own-roll Kakera must be collected."""
        bot, channel = _create_test_client(
            rolling_enabled=False,
            kakera_reaction_snipe_mode_preset=False,
        )
        on_message = bot.events["on_message"]
        message, btn = _build_roll_message(
            channel=channel,
            message_id=1001,
            roll_owner_id=bot.user.id,
            roll_owner_name=bot.user.name,
            client=bot,
        )

        await on_message(message)

        self.assertTrue(
            btn.click.called,
            "Own-roll Kakera must be eligible and clicked even when Auto-Collect Kakera is disabled.",
        )
        self.assertIn(1001, bot.kakera_reaction_sniped_messages)

    async def test_2_snipe_only_disabled_auto_kakera_ignores_other_user_kakera(self):
        """TEST 2: In snipe-only mode with Auto-Collect Kakera OFF, other users' Kakera must NOT be collected."""
        bot, channel = _create_test_client(
            rolling_enabled=False,
            kakera_reaction_snipe_mode_preset=False,
        )
        on_message = bot.events["on_message"]
        message, btn = _build_roll_message(
            channel=channel,
            message_id=1002,
            roll_owner_id=9999,
            roll_owner_name="other-player",
            client=bot,
        )

        await on_message(message)

        self.assertFalse(
            btn.click.called,
            "Other user's Kakera must NOT be clicked when Auto-Collect Kakera is disabled.",
        )
        self.assertNotIn(1002, bot.kakera_reaction_sniped_messages)

    async def test_3_snipe_only_enabled_auto_kakera_collects_from_target_user(self):
        """TEST 3: In snipe-only mode with Auto-Collect Kakera ON, allowed target users' Kakera is collected."""
        bot, channel = _create_test_client(
            rolling_enabled=False,
            kakera_reaction_snipe_mode_preset=True,
            kakera_reaction_snipe_targets=["5555"],
        )
        on_message = bot.events["on_message"]
        message, btn = _build_roll_message(
            channel=channel,
            message_id=1003,
            roll_owner_id=5555,
            roll_owner_name="allowed-target",
            client=bot,
        )

        await on_message(message)

        self.assertTrue(
            btn.click.called,
            "Target user's Kakera must be clicked when Auto-Collect Kakera is enabled.",
        )
        self.assertIn(1003, bot.kakera_reaction_sniped_messages)

    async def test_4_normal_rolling_disabled_auto_kakera_unchanged(self):
        """TEST 4: In normal rolling mode with Auto-Collect Kakera OFF, own-roll Kakera collection is unchanged."""
        bot, channel = _create_test_client(
            rolling_enabled=True,
            kakera_reaction_snipe_mode_preset=False,
            immediate_kakera_click_preset=True,
        )
        bot.is_actively_rolling = True
        on_message = bot.events["on_message"]
        message, btn = _build_roll_message(
            channel=channel,
            message_id=1004,
            roll_owner_id=bot.user.id,
            roll_owner_name=bot.user.name,
            client=bot,
        )

        await on_message(message)

        self.assertTrue(
            btn.click.called,
            "Normal rolling own-roll Kakera collection must remain working with Auto-Collect Kakera OFF.",
        )

    async def test_5_target_user_ids_do_not_block_own_roll_kakera(self):
        """TEST 5: Target User IDs filter other users, but do NOT block the bot's own rolls."""
        bot, channel = _create_test_client(
            rolling_enabled=False,
            kakera_reaction_snipe_mode_preset=True,
            kakera_reaction_snipe_targets=["5555"],
        )
        on_message = bot.events["on_message"]

        # 5A: Other user not in targets is blocked
        message_unlisted, btn_unlisted = _build_roll_message(
            channel=channel,
            message_id=1005,
            roll_owner_id=8888,
            roll_owner_name="unlisted-player",
            client=bot,
        )
        await on_message(message_unlisted)
        self.assertFalse(
            btn_unlisted.click.called,
            "Unlisted other user's Kakera must be blocked by target filters.",
        )

        # 5B: Own roll is NOT blocked by target user filters (even though bot id 7001 is not in targets)
        message_own, btn_own = _build_roll_message(
            channel=channel,
            message_id=1006,
            roll_owner_id=bot.user.id,
            roll_owner_name=bot.user.name,
            client=bot,
        )
        await on_message(message_own)
        self.assertTrue(
            btn_own.click.called,
            "Own-roll Kakera must NOT be blocked by Target User IDs.",
        )
