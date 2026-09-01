import asyncio
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot


class _MockHandle:
    def __init__(self):
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def cancelled(self):
        return self._cancelled


class _MockLoop:
    def call_later(self, _delay, _callback, *_args):
        return _MockHandle()

    def create_task(self, coroutine):
        coroutine.close()
        return None


class _MockBot:
    def __init__(self, user_id):
        self.loop = _MockLoop()
        self.user = SimpleNamespace(
            id=user_id,
            name=f"side-{user_id}",
            display_name=f"side-{user_id}",
        )
        self.events = {}
        self._fetched_channels = {}

    def event(self, function):
        self.events[function.__name__] = function
        return function

    def run(self, _token, reconnect=True):
        return None

    def get_channel(self, _channel_id):
        # Reproduce the per-client cache-miss path that formerly fell back to
        # the roll channel before the configured command channel was fetched.
        return None

    async def fetch_channel(self, channel_id):
        return self._fetched_channels.get(channel_id)

    def is_closed(self):
        return False


class _Channel:
    def __init__(self, channel_id, guild_id, client_getter):
        self.id = channel_id
        self.guild = SimpleNamespace(id=guild_id)
        self.sent = []
        self._client_getter = client_getter

    async def send(self, content):
        self.sent.append(content)
        client = self._client_getter()
        future = getattr(client, "_sphere_game_response_future", None)
        if future is not None and not future.done() and content.startswith(("$oh", "$oc")):
            # A malformed board finishes the real command path immediately;
            # its shape is irrelevant to this routing regression.
            future.set_result(SimpleNamespace(id=9981, components=[]))
        return SimpleNamespace(id=7000 + len(self.sent))


class _SphereStatus:
    refill_minutes = None

    def __init__(self, *, oh=0, oc=0):
        self._available = {"oh": oh, "oc": oc, "oq": 0, "ot": 0}

    def available_for(self, kind):
        return self._available[kind]


def _create_client(*, user_id, command_channel_id, auto_oh=False, auto_oc=False):
    bot = _MockBot(user_id)
    mudae_bot._mobile_runtime_stop_event.clear()
    with mock.patch.object(mudae_bot.commands, "Bot", return_value=bot):
        mudae_bot.run_bot(
            token="dummy_token",
            prefix="!",
            target_channel_id=1467081796364537949,
            roll_command="wa",
            min_kakera=100,
            delay_seconds=0,
            mudae_prefix="$",
            log_function=lambda *_args, **_kwargs: None,
            preset_name="shared-side-preset",
            key_mode=False,
            start_delay=0,
            snipe_mode=False,
            snipe_delay=0,
            snipe_ignore_min_kakera_reset=False,
            wishlist=[],
            series_snipe_mode=False,
            series_snipe_delay=0,
            series_wishlist=[],
            roll_speed=1.5,
            kakera_snipe_mode_preset=False,
            kakera_snipe_threshold_preset=0,
            enable_reactive_self_snipe_preset=False,
            rolling_enabled=True,
            kakera_reaction_snipe_mode_preset=False,
            kakera_reaction_snipe_delay_preset=0,
            kakera_reaction_snipe_targets=[],
            command_channel_id_preset=command_channel_id,
            auto_oh_enabled_preset=auto_oh,
            auto_oc_enabled_preset=auto_oc,
            oh_use_individually_preset=False,
            oc_collect_after_red_preset=True,
        )

    client_ref = lambda: bot
    roll_channel = _Channel(1467081796364537949, 14670817, client_ref)
    command_channel = _Channel(1467081710788415498, 14670817, client_ref)
    bot._main_channel = roll_channel
    if command_channel_id:
        bot._fetched_channels[int(command_channel_id)] = command_channel
    return bot, roll_channel, command_channel


class CommandChannelRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_auto_oh_uses_configured_command_channel_after_cache_miss(self):
        client, roll_channel, command_channel = _create_client(
            user_id=1101,
            command_channel_id="1467081710788415498",
            auto_oh=True,
        )

        await client._runtime_run_available_sphere_games(roll_channel, _SphereStatus(oh=2))

        self.assertEqual(command_channel.sent, ["$oh 2"])
        self.assertEqual(roll_channel.sent, [])

    async def test_auto_oc_uses_configured_command_channel_after_cache_miss(self):
        client, roll_channel, command_channel = _create_client(
            user_id=1102,
            command_channel_id="1467081710788415498",
            auto_oc=True,
        )

        await client._runtime_run_available_sphere_games(roll_channel, _SphereStatus(oc=1))

        self.assertEqual(command_channel.sent, ["$oc 1"])
        self.assertEqual(roll_channel.sent, [])

    async def test_empty_command_channel_keeps_existing_roll_channel_fallback(self):
        client, roll_channel, command_channel = _create_client(
            user_id=1103,
            command_channel_id="",
            auto_oh=True,
        )

        await client._runtime_run_available_sphere_games(roll_channel, _SphereStatus(oh=1))

        self.assertEqual(roll_channel.sent, ["$oh 1"])
        self.assertEqual(command_channel.sent, [])

    async def test_shared_preset_side_accounts_resolve_independently(self):
        clients = [
            _create_client(
                user_id=1200 + index,
                command_channel_id="1467081710788415498",
                auto_oh=True,
            )
            for index in range(3)
        ]

        await asyncio.gather(*(
            client._runtime_run_available_sphere_games(roll_channel, _SphereStatus(oh=1))
            for client, roll_channel, _command_channel in clients
        ))

        for _client, roll_channel, command_channel in clients:
            self.assertEqual(command_channel.sent, ["$oh 1"])
            self.assertEqual(roll_channel.sent, [])
