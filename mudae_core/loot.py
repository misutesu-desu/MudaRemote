"""Account-scoped $kl and $givescrap automation."""

import asyncio
import datetime
import math
import random
import re

from mudae_core.runtime import wait_until_resumed
from mudae_core.status import status_message_addresses_identity


MUDAE_ID = 432610292342587392
PIN_ERRORS = ("too many pins", "release your duplicates", "tienes muchas insignias", "libera tus duplicados")
CONFIRMATIONS = {
    "kl": ("do you want to spend", "quieres gastar"),
    "scrap": ("do you really want to give", "de verdad quieres dar"),
}
ARLP_SUCCESS = ("mudapins were released", "were released", "fueron liberadas", "han sido liberadas", "fueron liberados")
KL_SUCCESS = ("rolls stacked", "obtained", "obtenido", "conseguido")
SCRAP_SUCCESS = ("scraps have been given", "scrap has been given", "se han dado")


def _positive_int(value, name):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value).strip()) or int(value) < 1:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def _message_text(message):
    parts = [str(getattr(message, "content", "") or "")]
    for embed in getattr(message, "embeds", ()) or ():
        parts.extend((str(getattr(embed, "title", "") or ""), str(getattr(embed, "description", "") or "")))
        parts.append(str(getattr(getattr(embed, "author", None), "name", "") or ""))
        parts.append(str(getattr(getattr(embed, "footer", None), "text", "") or ""))
        for field in getattr(embed, "fields", ()) or ():
            parts.extend((str(getattr(field, "name", "") or ""), str(getattr(field, "value", "") or "")))
    return "\n".join(parts).casefold()


class LootAutomation:
    def __init__(self, client, preset_data, send, wait, log):
        self.client, self.send, self.wait, self.log = client, send, wait, log
        self.mode = str(preset_data.get("loot_mode", "off") or "off").strip().lower()
        if self.mode not in {"off", "kl", "scrap"}:
            raise ValueError("loot_mode must be off, kl, or scrap")
        self.kl_amount = _positive_int(preset_data.get("kl_amount", 1000), "kl_amount") if self.mode == "kl" else 1000
        self.scrap_amount = _positive_int(preset_data.get("scrap_amount", 500000000), "scrap_amount") if self.mode == "scrap" else 500000000
        target = str(preset_data.get("scrap_target_id", "") or "").strip()
        if self.mode == "scrap":
            self.scrap_target_id = str(_positive_int(target, "scrap_target_id"))
        else:
            self.scrap_target_id = target
        try:
            if isinstance(preset_data.get("loot_min_cooldown", 30), bool) or isinstance(preset_data.get("loot_max_cooldown", 40), bool):
                raise ValueError
            self.min_cooldown = float(preset_data.get("loot_min_cooldown", 30))
            self.max_cooldown = float(preset_data.get("loot_max_cooldown", 40))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("loot cooldowns must be finite numbers >= 1") from exc
        if (not math.isfinite(self.min_cooldown) or not math.isfinite(self.max_cooldown)
                or self.min_cooldown < 1 or self.max_cooldown < self.min_cooldown):
            raise ValueError("loot cooldowns must be finite numbers >= 1 with max >= min")
        self._queue = None
        self._channel_id = None
        self._sent_at = None
        self._sent_ids = set()
        self._seen = set()

    def _arm(self, channel):
        self._queue = asyncio.Queue()
        self._channel_id = channel.id
        self._sent_at = datetime.datetime.now(datetime.timezone.utc)
        self._sent_ids = set()
        self._seen = set()

    async def _send_once(self, channel, content):
        try:
            receipt = await self.send(channel, content)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.log(f"Loot send uncertain for {content!r}: {exc}", "ERROR")
            return False
        message_id = getattr(receipt, "id", None)
        if message_id is None:
            self.log(f"Loot send has no receipt for {content!r}; waiting for cooldown", "WARN")
            return False
        self._sent_ids.add(message_id)
        return True

    def _belongs_to_self(self, message, text):
        own = getattr(getattr(self.client, "user", None), "id", None)
        if own is None:
            return False
        own_names = {str(name).casefold() for name in (
            getattr(self.client.user, "name", None),
            getattr(self.client.user, "display_name", None),
            getattr(self.client.user, "global_name", None),
        ) if name}
        leading_mention = re.match(r"^\s*(?:\*\*)?<@!?(\d+)>(?:\*\*)?", text)
        if leading_mention and int(leading_mention.group(1)) != own:
            return False
        leading_name = re.match(r"^\s*(?:\*\*([^*]+)\*\*|([\w.-]{2,32})(?:\s*[,!:—-]|'s\b))", text)
        addressed_by_name = status_message_addresses_identity(text, own_names, user_id=None)
        if leading_name and not leading_mention and not addressed_by_name:
            return False
        reference = getattr(message, "reference", None)
        if getattr(reference, "message_id", None) in self._sent_ids:
            return True
        return bool(leading_mention) or addressed_by_name

    def on_message(self, message):
        if self._queue is None or getattr(getattr(message, "author", None), "id", None) != MUDAE_ID:
            return
        if getattr(getattr(message, "channel", None), "id", None) != self._channel_id:
            return
        message_id = getattr(message, "id", None)
        created_at = getattr(message, "created_at", None)
        if (message_id is None or message_id in self._seen or not isinstance(created_at, datetime.datetime)
                or created_at.tzinfo is None or created_at < self._sent_at):
            return
        text = _message_text(message)
        if any(pattern in text for pattern in ARLP_SUCCESS):
            signal = "ARLP_OK"
        elif any(pattern in text for pattern in PIN_ERRORS):
            signal = "PIN_ERROR"
        elif any(pattern in text for pattern in CONFIRMATIONS.get(self.mode, ())) and ("y/n" in text or "yes/no" in text):
            signal = "CONFIRM"
        elif any(pattern in text for pattern in (KL_SUCCESS if self.mode == "kl" else SCRAP_SUCCESS)):
            signal = "SUCCESS"
        else:
            return
        self._seen.add(message_id)
        self._queue.put_nowait((signal, message, text))

    async def _response(self, accepted, timeout):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not self.client.is_closed() and not self.client.is_paused:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            try:
                signal, message, text = await asyncio.wait_for(self._queue.get(), min(remaining, 0.5))
            except asyncio.TimeoutError:
                continue
            if signal not in accepted or not self._belongs_to_self(message, text):
                continue
            if any(message.id <= sent_id for sent_id in self._sent_ids):
                continue
            return signal
        return None

    async def _arlp(self, channel):
        self.log("Pin limit detected; sending arlp", "WARN")
        self._arm(channel)
        if not await self.wait(random.uniform(1.2, 2.5)) or self.client.is_paused:
            return
        if not await self._send_once(channel, f"{self.client.mudae_prefix}arlp"):
            return
        if await self._response({"ARLP_OK"}, 12) == "ARLP_OK":
            self.log("Pins released", "SUCCESS")
            await self.wait(random.uniform(2, 4))
        else:
            self.log("Timed out waiting for arlp confirmation", "WARN")

    async def _cycle(self, channel):
        self._arm(channel)
        prefix = self.client.mudae_prefix
        command = (f"{prefix}kl {self.kl_amount}" if self.mode == "kl" else
                   f"{prefix}givescrap {self.scrap_target_id} {self.scrap_amount}")
        if not await self._send_once(channel, command):
            return
        signal = await self._response({"CONFIRM", "SUCCESS", "PIN_ERROR"}, 8)
        if signal == "PIN_ERROR":
            await self._arlp(channel)
        elif signal == "SUCCESS":
            self.log("Loot action completed", "SUCCESS")
        elif signal == "CONFIRM":
            if not await self.wait(random.uniform(1.1, 2.8)) or self.client.is_paused:
                return
            if not await self._send_once(channel, "y"):
                return
            signal = await self._response({"SUCCESS", "PIN_ERROR"}, 7)
            if signal == "SUCCESS":
                self.log("Loot action completed", "SUCCESS")
            elif signal == "PIN_ERROR":
                await self._arlp(channel)
            else:
                self.log("No final loot confirmation after y", "WARN")
        else:
            self.log("Mudae did not respond to loot command in time", "WARN")

    async def run(self, channel):
        if self.mode == "off":
            return
        try:
            while not self.client.is_closed():
                await wait_until_resumed(self.client)
                if self.client.is_closed():
                    break
                try:
                    await self._cycle(channel)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.log(f"Loot cycle failed: {type(exc).__name__}: {exc}", "ERROR")
                finally:
                    self._queue = None
                if self.client.is_closed():
                    break
                cooldown = random.uniform(self.min_cooldown, self.max_cooldown)
                self.log(f"Next loot cycle in {cooldown:.1f}s", "INFO")
                while not self.client.is_closed():
                    if await self.wait(cooldown):
                        break
                    await wait_until_resumed(self.client)
        finally:
            self._queue = None
