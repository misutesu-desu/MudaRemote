"""$rt can go to the account's own command channel instead of the channel it sniped in."""
import unittest
from unittest import mock

from tests.test_kakera_snipe_ownership import _Channel, _create_test_client


def _rt_sender(bot):
    verify = bot._runtime_verify_snipe_outcome
    cells = dict(zip(verify.__code__.co_freevars, verify.__closure__))
    finalize = cells['finalize_successful_claim'].cell_contents
    cells = dict(zip(finalize.__code__.co_freevars, finalize.__closure__))
    send_rt = cells['send_rt_command'].cell_contents
    inner = dict(zip(send_rt.__code__.co_freevars, send_rt.__closure__))
    transport = mock.AsyncMock(return_value=False)
    inner['send_mudae_reaction_command'].cell_contents = transport
    return send_rt, transport


class RtCommandChannelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot, self.snipe_channel = _create_test_client()
        self.command_channel = _Channel(5678, lambda: self.bot)
        self.bot._fetched_channels[5678] = self.command_channel
        self.bot.command_channel_id_preset = '5678'

    async def test_default_keeps_rt_in_the_snipe_channel(self):
        send_rt, transport = _rt_sender(self.bot)
        self.bot.rt_in_command_channel = False
        await send_rt(self.snipe_channel)
        self.assertIs(transport.await_args.args[0], self.snipe_channel)

    async def test_toggle_sends_rt_in_the_command_channel(self):
        send_rt, transport = _rt_sender(self.bot)
        self.bot.rt_in_command_channel = True
        self.bot.command_channel = self.command_channel
        await send_rt(self.snipe_channel)
        self.assertIs(transport.await_args.args[0], self.command_channel)
        self.assertEqual(transport.await_args.args[1], self.bot.mudae_prefix + 'rt')

    async def test_toggle_without_a_command_channel_falls_back(self):
        send_rt, transport = _rt_sender(self.bot)
        self.bot.rt_in_command_channel = True
        self.bot.command_channel = None
        self.bot.command_channel_id_preset = ''
        await send_rt(self.snipe_channel)
        self.assertIs(transport.await_args.args[0], self.snipe_channel)


if __name__ == '__main__':
    unittest.main()
