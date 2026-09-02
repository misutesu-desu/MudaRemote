import asyncio
import datetime
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot
from mudae_core.coordinator import GlobalIntervalCoordinator
from mudae_core.runtime import is_tu_still_required


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


class _Bot:
    def __init__(self):
        self.loop = _Loop()
        self.user = SimpleNamespace(id=7001, name="snipe-only", display_name="snipe-only")
        self.events = {}
        self._fetched_channels = {}

    def event(self, function):
        self.events[function.__name__] = function
        return function

    def run(self, _token, reconnect=True):
        return None

    def get_channel(self, _channel_id):
        # Exercise the configured administrative-channel cache-miss path.
        return None

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
        client = self._client_getter()
        if content == "$tu":
            response = getattr(client, "_tu_response_future", None)
            if response is not None and not response.done():
                response.set_result(
                    "You can claim now!\n"
                    "Next claim reset in **30** min.\n"
                    "You have **0** rolls left. Next rolls reset in **45** min.\n"
                    "$rt is available!\n"
                    "Power: **100%**\n"
                    "$dk is ready!"
                )
        elif content.startswith(("$oh", "$oc")):
            response = getattr(client, "_sphere_game_response_future", None)
            if response is not None and not response.done():
                response.set_result(SimpleNamespace(id=9001, components=[]))
        return SimpleNamespace(id=8000 + len(self.sent), created_at=datetime.datetime.now(datetime.timezone.utc))

    async def history(self, limit=1):
        if False:
            yield limit


class _SphereStatus:
    refill_minutes = None

    def available_for(self, kind):
        return {"oh": 0, "oc": 1, "oq": 0, "ot": 0}[kind]


def _create_snipe_only_client():
    bot = _Bot()
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
            log_function=lambda *_args, **_kwargs: None,
            preset_name="snipe-startup-production",
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
            command_channel_id_preset="5678",
            auto_oc_enabled_preset=True,
        )

    client_getter = lambda: bot
    roll_channel = _Channel(1234, client_getter)
    command_channel = _Channel(5678, client_getter)
    bot._main_channel = roll_channel
    bot._fetched_channels[5678] = command_channel
    bot.command_pacer.minimum_delay = 0
    bot.command_pacer.maximum_delay = 0
    bot.command_pacer._next_command_at = 0
    return bot, roll_channel, command_channel


class SnipeStartupProductionTests(unittest.IsolatedAsyncioTestCase):
    async def test_snipe_only_handshake_hydrates_once_then_unblocks_configured_spheres(self):
        client, roll_channel, command_channel = _create_snipe_only_client()
        old_coordinator = mudae_bot._tu_interval_coordinator
        mudae_bot._tu_interval_coordinator = GlobalIntervalCoordinator()
        self.addCleanup(setattr, mudae_bot, "_tu_interval_coordinator", old_coordinator)

        required, reason = is_tu_still_required(client, proceed_to_rolls=False)
        self.assertTrue(required)
        self.assertEqual(reason, "required")

        await client._runtime_check_status(
            client,
            roll_channel,
            client.mudae_prefix,
            proceed_to_rolls=False,
        )

        self.assertEqual(command_channel.sent, ["$tu"])
        self.assertEqual(roll_channel.sent, [])
        self.assertEqual(client.tu_query_count, 1)
        self.assertTrue(client.last_tu_snapshot_complete)
        self.assertTrue(client.claim_right_available)
        self.assertTrue(client.rt_available)

        # The completed authoritative startup snapshot suppresses the old
        # rolling-disabled loop instead of producing another physical $tu.
        required, reason = is_tu_still_required(client, proceed_to_rolls=False)
        self.assertFalse(required)
        self.assertEqual(reason, "rolling-disabled")
        await client._runtime_check_status(
            client,
            roll_channel,
            client.mudae_prefix,
            proceed_to_rolls=False,
        )
        self.assertEqual(command_channel.sent, ["$tu"])

        # Existing administrative routing remains intact after handshake.
        await client._runtime_run_available_sphere_games(roll_channel, _SphereStatus())
        self.assertEqual(command_channel.sent, ["$tu", "$oc 1"])
        self.assertEqual(roll_channel.sent, [])


if __name__ == "__main__":
    unittest.main()
