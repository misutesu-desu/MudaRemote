import asyncio
import datetime
import unittest
from types import SimpleNamespace

from mudae_core.loot import LootAutomation, MUDAE_ID


def message(message_id, content, channel_id=5, author_id=MUDAE_ID, *, reply=None, embeds=(), mentions=()):
    return SimpleNamespace(
        id=message_id, content=content, channel=SimpleNamespace(id=channel_id),
        author=SimpleNamespace(id=author_id),
        created_at=datetime.datetime.now(datetime.timezone.utc),
        reference=SimpleNamespace(message_id=reply) if reply is not None else None,
        embeds=embeds, mentions=mentions,
    )


class LootTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = SimpleNamespace(
            user=SimpleNamespace(id=10, name="owner", display_name="owner"),
            mudae_prefix="$", is_paused=False, _runtime_state_event=asyncio.Event(),
            is_closed=lambda: False,
        )
        self.channel = SimpleNamespace(id=5)
        self.sent = []
        self.logs = []
        self.next_id = 100
        self.on_send = None

        async def send(channel, content):
            self.next_id += 1
            receipt = SimpleNamespace(id=self.next_id)
            self.sent.append(content)
            if self.on_send:
                self.on_send(content, receipt.id)
            return receipt

        async def wait(_seconds):
            return True

        self.send, self.wait = send, wait

    def loot(self, **settings):
        return LootAutomation(self.client, {"loot_mode": "kl", **settings},
                              self.send, self.wait, lambda text, level: self.logs.append((text, level)))

    async def test_kl_confirmation_and_duplicate_prompt(self):
        loot = self.loot()

        def on_send(content, receipt_id):
            if content.startswith("$kl"):
                prompt = message(receipt_id + 1, "Do you want to spend 1000? y/n", reply=receipt_id)
                loot.on_message(prompt)  # Response can arrive before send returns.
                loot.on_message(prompt)
            elif content == "y":
                loot.on_message(message(receipt_id + 1, "Rolls stacked", reply=receipt_id))

        self.on_send = on_send
        await loot._cycle(self.channel)
        self.assertEqual(self.sent, ["$kl 1000", "y"])
        self.assertTrue(any("completed" in text for text, _ in self.logs))

    async def test_direct_scrap_success_from_embed(self):
        loot = self.loot(loot_mode="scrap", scrap_target_id="999", scrap_amount="500")

        def on_send(_content, receipt_id):
            embed = SimpleNamespace(title="", description="Scraps have been given",
                                    author=SimpleNamespace(name=""), footer=None, fields=[])
            loot.on_message(message(receipt_id + 1, "", reply=receipt_id, embeds=[embed]))

        self.on_send = on_send
        await loot._cycle(self.channel)
        self.assertEqual(self.sent, ["$givescrap 999 500"])
        self.assertTrue(any("completed" in text for text, _ in self.logs))

    async def test_reply_to_own_givescrap_command_can_mention_recipient(self):
        loot = self.loot(loot_mode="scrap", scrap_target_id="999", scrap_amount=500)

        def on_send(_content, receipt_id):
            loot.on_message(message(receipt_id + 1, "Scraps have been given to <@999>", reply=receipt_id))

        self.on_send = on_send
        await loot._cycle(self.channel)
        self.assertEqual(self.sent, ["$givescrap 999 500"])
        self.assertTrue(any("completed" in text for text, _ in self.logs))

    async def test_pin_error_runs_arlp(self):
        loot = self.loot()

        def on_send(content, receipt_id):
            if content.startswith("$kl"):
                loot.on_message(message(receipt_id + 1, "Too many pins", reply=receipt_id))
            elif content == "$arlp":
                loot.on_message(message(receipt_id + 1, "Mudapins were released", reply=receipt_id))

        self.on_send = on_send
        await loot._cycle(self.channel)
        self.assertEqual(self.sent, ["$kl 1000", "$arlp"])
        self.assertTrue(any("Pins released" in text for text, _ in self.logs))

    async def test_foreign_messages_cannot_trigger_confirmation(self):
        loot = self.loot()

        def on_send(content, receipt_id):
            if content == "y":
                loot.on_message(message(receipt_id + 1, "Rolls stacked", reply=receipt_id))
                return
            prompt = "Do you want to spend 1000? y/n"
            loot.on_message(message(receipt_id + 1, prompt, channel_id=6, reply=receipt_id))
            loot.on_message(message(receipt_id + 2, prompt, author_id=99, reply=receipt_id))
            loot.on_message(message(receipt_id + 3, "<@11> " + prompt, reply=receipt_id))
            loot.on_message(message(receipt_id + 4, "other: " + prompt, reply=receipt_id))
            loot.on_message(message(receipt_id + 5, prompt))  # Unaddressed is ambiguous.
            loot.on_message(message(receipt_id + 6, "<@10> " + prompt))

        self.on_send = on_send
        await loot._cycle(self.channel)
        self.assertEqual(self.sent, ["$kl 1000", "y"])

    async def test_later_own_recipient_mention_does_not_authorize_y(self):
        loot = self.loot(loot_mode="scrap", scrap_target_id="10")
        original_response = loot._response

        async def fast_response(accepted, _timeout):
            return await original_response(accepted, 0.02)

        loot._response = fast_response

        def on_send(_content, receipt_id):
            loot.on_message(message(receipt_id + 1,
                                    "Do you really want to give 500 scraps to <@10>? y/n"))

        self.on_send = on_send
        await loot._cycle(self.channel)
        self.assertEqual(self.sent, ["$givescrap 10 500000000"])

    async def test_other_operation_prompt_cannot_confirm_loot(self):
        loot = self.loot()
        original_response = loot._response

        async def fast_response(accepted, _timeout):
            return await original_response(accepted, 0.02)

        loot._response = fast_response

        def on_send(_content, receipt_id):
            loot.on_message(message(receipt_id + 1,
                                    "<@10> Do you really want to give 500 scraps? y/n",
                                    reply=receipt_id))

        self.on_send = on_send
        await loot._cycle(self.channel)
        self.assertEqual(self.sent, ["$kl 1000"])

    async def test_leading_actor_identity_authorizes_y(self):
        for actor in ("<@10>", "<@!10>", "**<@10>**", "owner,", "**owner**"):
            with self.subTest(actor=actor):
                self.sent.clear()
                loot = self.loot()

                def on_send(content, receipt_id):
                    if content == "y":
                        loot.on_message(message(receipt_id + 1, "Rolls stacked", reply=receipt_id))
                    else:
                        loot.on_message(message(receipt_id + 1,
                                                f"{actor} Do you want to spend 1000? y/n"))

                self.on_send = on_send
                await loot._cycle(self.channel)
                self.assertEqual(self.sent, ["$kl 1000", "y"])

    async def test_edited_message_can_become_response(self):
        loot = self.loot()

        def on_send(_content, receipt_id):
            loot.on_message(message(receipt_id + 1, "Loading", reply=receipt_id))
            loot.on_message(message(receipt_id + 1, "Rolls stacked", reply=receipt_id))

        self.on_send = on_send
        await loot._cycle(self.channel)
        self.assertTrue(any("completed" in text for text, _ in self.logs))

    async def test_pause_and_cancellation(self):
        loot = self.loot()
        self.client.is_paused = True
        task = asyncio.create_task(loot.run(self.channel))
        await asyncio.sleep(0)
        self.assertEqual(self.sent, [])
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIsNone(loot._queue)

    async def test_missing_receipt_is_not_retried(self):
        async def uncertain(_channel, content):
            self.sent.append(content)
            return None

        loot = LootAutomation(self.client, {"loot_mode": "kl"}, uncertain, self.wait,
                              lambda text, level: self.logs.append((text, level)))
        await loot._cycle(self.channel)
        self.assertEqual(self.sent, ["$kl 1000"])

    def test_invalid_settings(self):
        for settings in (
            {"loot_mode": "scrap"}, {"kl_amount": 0},
            {"loot_mode": "scrap", "scrap_target_id": "999", "scrap_amount": "NaN"},
            {"loot_min_cooldown": 0}, {"loot_max_cooldown": float("inf")},
            {"loot_min_cooldown": True}, {"loot_max_cooldown": True},
            {"loot_min_cooldown": 40, "loot_max_cooldown": 30},
        ):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                self.loot(**settings)

    def test_inactive_amount_does_not_block_mode(self):
        self.assertEqual(self.loot(scrap_amount="bad").kl_amount, 1000)
        self.assertEqual(self.loot(loot_mode="scrap", scrap_target_id="999", kl_amount="bad").scrap_amount, 500000000)
        self.assertEqual(self.loot(loot_mode="off", kl_amount="bad", scrap_amount="bad").mode, "off")


if __name__ == "__main__":
    unittest.main()
