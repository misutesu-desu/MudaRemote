"""Sphere mini-game orchestration ($oh/$oc) for a single client.

All mutable state stays on the client instance so the board lock stays shared
with roll commands. This module only owns the orchestration flow and receives
every cross-cutting concern (logging, sending, clicking, waiting) as an
explicit callback.
"""

import asyncio
import datetime
import random
import time
from datetime import timezone

from .runtime import split_command_batches
from .spheres import (
    choose_chest_position,
    choose_harvest_position,
    count_harvest_bonus_clicks,
    harvest_reveal_is_free,
    normalize_sphere_emoji,
    sphere_click_recovery_decision,
)


def sphere_game_kind(message):
    interaction = (
        getattr(message, 'interaction_metadata', None)
        or getattr(message, 'interaction', None)
    )
    command_name = str(getattr(interaction, 'name', '') or '').strip().lower().lstrip('/')
    if command_name in {"oh", "oc"}:
        return command_name
    text = str(getattr(message, 'content', '') or '').lower()
    if "1 red sphere" in text and "never at the center" in text:
        return "oc"
    if "blue spheres unveil 3 buttons" in text and "multiplier:" in text:
        return "oh"
    return None


def sphere_game_buttons(message):
    buttons = []
    for component in getattr(message, 'components', None) or []:
        buttons.extend(getattr(component, 'children', None) or [])
    return buttons


def sphere_board_snapshot(message):
    buttons = sphere_game_buttons(message)
    emojis = [str(getattr(getattr(button, 'emoji', None), 'name', '') or '') for button in buttons]
    disabled = [bool(getattr(button, 'disabled', False)) for button in buttons]
    styles = [str(getattr(button, 'style', '')) for button in buttons]
    return buttons, emojis, disabled, tuple(zip(emojis, disabled, styles))


class SphereRuntime:
    """Drive sphere boards for one client while leaving shared state in place."""

    def __init__(self, client, *, target_bot_id, log, send, click, wait,
                 maintenance_active, claim_pending, resolve_channel,
                 wake_status, ambiguous_error):
        self._client = client
        self._target_bot_id = target_bot_id
        self._log = log
        self._send = send
        self._click = click
        self._wait = wait
        self._maintenance_active = maintenance_active
        self._claim_pending = claim_pending
        self._resolve_channel = resolve_channel
        self._wake_status = wake_status
        self._ambiguous_error = ambiguous_error

    def sphere_game_belongs_to_self(self, message):
        interaction = (
            getattr(message, 'interaction', None)
            or getattr(message, 'interaction_metadata', None)
        )
        interaction_user = getattr(interaction, 'user', None)
        interaction_user_id = getattr(interaction_user, 'id', None)
        client_user_id = getattr(getattr(self._client, 'user', None), 'id', None)
        return interaction_user_id is None or interaction_user_id == client_user_id

    def capture_sphere_game_response(self, message):
        future = getattr(self._client, '_sphere_game_response_future', None)
        if future is None or future.done():
            return False
        if getattr(getattr(message, 'author', None), 'id', None) != self._target_bot_id:
            return False
        expected_channel_id = getattr(self._client, '_sphere_game_response_channel_id', None)
        if expected_channel_id is not None and getattr(message.channel, 'id', None) != expected_channel_id:
            return False
        buttons = sphere_game_buttons(message)
        if len(buttons) != 25:
            return False
        expected_kind = getattr(self._client, '_sphere_game_response_kind', None)
        detected_kind = sphere_game_kind(message)
        # Text-command boards do not expose the command name, and their
        # descriptions are localized. While a specific game response is
        # pending, a fresh 25-button Mudae board in that channel is sufficient.
        if detected_kind is not None and detected_kind != expected_kind:
            return False
        if detected_kind is None and expected_kind not in {"oh", "oc"}:
            return False
        if not self.sphere_game_belongs_to_self(message):
            return False
        future.set_result(message)
        return True

    def capture_sphere_game_bonus(self, message):
        if getattr(getattr(message, 'author', None), 'id', None) != self._target_bot_id:
            return False
        if getattr(self._client, '_sphere_game_response_kind', None) != "oh":
            return False
        expected_channel_id = getattr(self._client, '_sphere_game_response_channel_id', None)
        if expected_channel_id is not None and getattr(message.channel, 'id', None) != expected_channel_id:
            return False
        bonus_text = [str(getattr(message, 'content', '') or '')]
        for embed in getattr(message, 'embeds', ()) or ():
            bonus_text.append(str(getattr(embed, 'description', '') or ''))
            for field in getattr(embed, 'fields', ()) or ():
                bonus_text.append(str(getattr(field, 'name', '') or ''))
                bonus_text.append(str(getattr(field, 'value', '') or ''))
        total_bonus_clicks = count_harvest_bonus_clicks("\n".join(bonus_text))
        message_id = getattr(message, 'id', None)
        previous_bonus_clicks = self._client._sphere_game_bonus_counts.get(message_id, 0)
        bonus_clicks = max(0, total_bonus_clicks - previous_bonus_clicks)
        if bonus_clicks <= 0:
            return False
        self._client._sphere_game_bonus_counts[message_id] = total_bonus_clicks
        self._client._sphere_game_bonus_clicks += bonus_clicks
        bonus_event = getattr(self._client, '_sphere_game_bonus_event', None)
        if bonus_event is not None:
            bonus_event.set()
        self._log(
            f"$oh: spD turned into spP; added {bonus_clicks} extra click(s).",
            "KAKERA",
        )
        return True

    async def wait_for_sphere_board_update(self, channel, message_id, previous_snapshot, update_event=None):
        latest = None
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if self._client.is_paused or self._maintenance_active():
                return None
            if update_event is not None:
                try:
                    await asyncio.wait_for(update_event.wait(), timeout=0.75)
                    update_event.clear()
                except asyncio.TimeoutError:
                    pass
            elif not await self._wait(0.75):
                return None
            try:
                latest = await channel.fetch_message(message_id)
            except Exception:
                continue
            if sphere_board_snapshot(latest)[3] != previous_snapshot:
                return latest
        return latest

    async def play_sphere_game(self, channel, message, kind):
        clicked_positions = set()
        current = message
        game_label = "$oh" if kind == "oh" else "$oc"

        paid_clicks = 0
        total_clicks = 0
        red_found = False
        while total_clicks < 25:
            paid_limit = 5 + int(getattr(self._client, '_sphere_game_bonus_clicks', 0) or 0)
            if paid_clicks >= paid_limit:
                break
            buttons, emojis, disabled, snapshot = sphere_board_snapshot(current)
            if len(buttons) != 25:
                self._log(f"{game_label}: Expected 25 sphere buttons but received {len(buttons)}.", "WARN")
                return False
            if all(disabled):
                break

            if kind == "oc":
                position = choose_chest_position(
                    emojis,
                    disabled,
                    reward_priority_order=self._client.oc_reward_priority_order,
                )
            else:
                position = choose_harvest_position(
                    emojis,
                    disabled,
                    paid_clicks=paid_clicks,
                    priority_order=self._client.oh_priority_order,
                    unknown_explore_clicks=self._client.oh_unknown_explore_clicks,
                )
            if position is None or position < 0 or position >= len(buttons):
                self._log(f"{game_label}: No safe enabled sphere button remains.", "WARN")
                break

            if not await self._wait(random.uniform(0.45, 0.85)):
                return False
            bonus_before_click = int(getattr(self._client, '_sphere_game_bonus_clicks', 0) or 0)
            bonus_event = getattr(self._client, '_sphere_game_bonus_event', None)
            if bonus_event is not None:
                bonus_event.clear()
            refreshed = None
            current_button = buttons[position]
            for click_attempt in range(2):
                update_event = asyncio.Event()
                self._client._sphere_board_update_events[current.id] = update_event
                ack_ambiguous = False
                try:
                    if not click_attempt:
                        self._log(
                            f"{game_label}: Clicking row {position // 5 + 1}, column {position % 5 + 1} ({emojis[position]}).",
                            "INFO",
                        )
                    else:
                        self._log(f"{game_label}: No board edit received; retrying the click once.", "WARN")
                    try:
                        if not await self._click(current_button):
                            return False
                    except Exception as error:
                        if not self._ambiguous_error(error):
                            raise
                        ack_ambiguous = True
                        self._log(
                            f"{game_label}: Discord acknowledgement was ambiguous; checking the board before any retry.",
                            "WARN",
                        )
                    refreshed = await self.wait_for_sphere_board_update(
                        channel,
                        current.id,
                        snapshot,
                        update_event=update_event,
                    )
                except Exception as error:
                    self._log(f"{game_label}: Sphere click failed: {error}", "WARN")
                    return False
                finally:
                    if self._client._sphere_board_update_events.get(current.id) is update_event:
                        self._client._sphere_board_update_events.pop(current.id, None)
                delivery_decision = sphere_click_recovery_decision(
                    snapshot,
                    sphere_board_snapshot(refreshed)[3] if refreshed is not None else None,
                    click_attempt + 1,
                )
                if delivery_decision == "delivered":
                    break
                if delivery_decision == "retry":
                    # The logical position, not the stale component object,
                    # identifies the bounded retry.  Re-fetch and reacquire it
                    # only after proving the pre-click board is unchanged.
                    latest = refreshed
                    if latest is None:
                        try:
                            latest = await channel.fetch_message(current.id)
                        except Exception:
                            latest = None
                    if latest is None or sphere_board_snapshot(latest)[3] != snapshot:
                        refreshed = latest
                        break
                    retry_buttons = sphere_game_buttons(latest)
                    if position >= len(retry_buttons) or getattr(retry_buttons[position], "disabled", False):
                        refreshed = latest
                        break
                    current = latest
                    current_button = retry_buttons[position]
                    if ack_ambiguous:
                        self._log(
                            f"{game_label}: Ambiguous click was not reflected on the board; retrying the refreshed logical button once.",
                            "WARN",
                        )

            if refreshed is None or sphere_board_snapshot(refreshed)[3] == snapshot:
                self._log(f"{game_label}: Board did not update after two click attempts; stopping safely.", "WARN")
                return False

            clicked_positions.add(position)
            total_clicks += 1
            current = refreshed
            _, revealed_emojis, _, _ = sphere_board_snapshot(current)
            revealed = normalize_sphere_emoji(
                revealed_emojis[position] if position < len(revealed_emojis) else ""
            )
            if kind != "oh" or not harvest_reveal_is_free(revealed):
                paid_clicks += 1
            if kind == "oh" and revealed == "spD" and bonus_event is not None:
                if int(getattr(self._client, '_sphere_game_bonus_clicks', 0) or 0) == bonus_before_click:
                    try:
                        await asyncio.wait_for(bonus_event.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        pass
            paid_limit = 5 + int(getattr(self._client, '_sphere_game_bonus_clicks', 0) or 0)
            self._log(
                f"{game_label}: Click {total_clicks} ({paid_clicks}/{paid_limit} used) at row {position // 5 + 1}, column {position % 5 + 1}"
                + (f" revealed {revealed}." if revealed else "."),
                "INFO",
            )
            if kind == "oc" and revealed == "sp" and position in clicked_positions:
                if not red_found:
                    self._log(
                        f"$oc: Red sphere found with {5 - paid_clicks} paid click(s) remaining; collecting bonus spheres.",
                        "KAKERA",
                    )
                red_found = True
                if not self._client.oc_collect_after_red:
                    self._log("$oc: Configured to stop immediately after finding red.", "INFO")
                    break

        if kind == "oh":
            self._log(f"$oh: Harvest finished after {len(clicked_positions)} click(s).", "KAKERA")
        elif red_found:
            self._log("$oc: Chest finished after finding red and using all available clicks.", "KAKERA")
        else:
            self._log("$oc: Board finished without finding the red sphere.", "WARN")
        return bool(clicked_positions)

    async def find_recent_sphere_game(self, channel, kind, started_at):
        try:
            async for candidate in channel.history(limit=15):
                created_at = getattr(candidate, 'created_at', None)
                if created_at is not None and created_at < started_at - datetime.timedelta(seconds=1):
                    continue
                if (getattr(getattr(candidate, 'author', None), 'id', None) == self._target_bot_id
                        and sphere_game_kind(candidate) in (None, kind)
                        and self.sphere_game_belongs_to_self(candidate)
                        and len(sphere_game_buttons(candidate)) == 25):
                    return candidate
        except Exception:
            return None
        return None

    async def run_sphere_game(self, channel, kind, uses):
        # Sphere boards are administrative commands.  Resolve their channel at
        # the physical send boundary so a stale per-client Discord cache cannot
        # turn a configured command channel into the roll-channel fallback.
        channel = await self._resolve_channel(channel)
        if channel is None:
            return False
        uses = max(1, min(10, int(uses or 1)))
        if kind == "oh" and self._client.oh_use_individually:
            uses = 1
        if self._client._sphere_game_lock is None:
            self._client._sphere_game_lock = asyncio.Lock()
        async with self._client._sphere_game_lock:
            if self._claim_pending():
                self._client._deferred_independent_known_work = True
                return False
            started_at = datetime.datetime.now(timezone.utc)
            response_future = asyncio.get_running_loop().create_future()
            self._client._sphere_game_response_future = response_future
            self._client._sphere_game_response_channel_id = getattr(channel, 'id', None)
            self._client._sphere_game_response_kind = kind
            self._client._sphere_game_bonus_clicks = 0
            self._client._sphere_game_bonus_event = asyncio.Event()
            self._client._sphere_game_bonus_counts = {}
            try:
                self._log(f"{kind.upper()}: Starting with {uses} available use(s).", "INFO")
                if not await self._send(channel, f"{self._client.mudae_prefix}{kind} {uses}"):
                    return False
                try:
                    game_message = await asyncio.wait_for(asyncio.shield(response_future), timeout=8.0)
                except asyncio.TimeoutError:
                    game_message = await self.find_recent_sphere_game(channel, kind, started_at)
                if game_message is None:
                    self._log(f"${kind}: Game board did not arrive; retrying later.", "WARN")
                    return False
                # Starting the board consumes the selected stock even if the chest is lost.
                self._client.sphere_game_counts[kind] = max(0, self._client.sphere_game_counts.get(kind, 0) - uses)
                return await self.play_sphere_game(channel, game_message, kind)
            finally:
                if self._client._sphere_game_response_future is response_future:
                    self._client._sphere_game_response_future = None
                    self._client._sphere_game_response_channel_id = None
                    self._client._sphere_game_response_kind = None
                    self._client._sphere_game_bonus_clicks = 0
                    self._client._sphere_game_bonus_event = None
                    self._client._sphere_game_bonus_counts = {}
                if not response_future.done():
                    response_future.cancel()

    async def run_available_sphere_games(self, channel, status=None):
        if getattr(self._client, "_sphere_games_running", False):
            self._client._deferred_independent_known_work = True
            return
        if status is not None:
            self._client.sphere_game_counts = {
                kind: status.available_for(kind) for kind in ("oh", "oc", "oq", "ot")
            }
        if status is not None and status.refill_minutes is not None:
            previous_refill = self._client.sphere_game_refill_at_utc
            self._client.sphere_game_refill_at_utc = (
                datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=status.refill_minutes)
            ).replace(second=0, microsecond=0)
            if previous_refill != self._client.sphere_game_refill_at_utc:
                self._client.loop.call_later(max(5.0, status.refill_minutes * 60.0 + 2.0), self._wake_status)

        if (status is not None and getattr(self._client, "is_processing_cycle", False)) or self._claim_pending():
            # A reconciliation $tu may still update local sphere stock, but it
            # must not inject a board command ahead of claim-state handling.
            self._client._deferred_independent_known_work = True
            return

        self._client._sphere_games_running = True
        try:
            enabled_games = (
                ("oh", self._client.auto_oh_enabled, self._client.sphere_game_counts.get("oh", 0)),
                ("oc", self._client.auto_oc_enabled, self._client.sphere_game_counts.get("oc", 0)),
            )
            for kind, enabled, available in enabled_games:
                if not enabled or available <= 0:
                    continue
                now_monotonic = time.monotonic()
                if now_monotonic < self._client._sphere_game_retry_after.get(kind, 0.0):
                    continue
                completed_all = True
                batch_sizes = (
                    [1] * available
                    if kind == "oh" and self._client.oh_use_individually
                    else split_command_batches(available, 10)
                )
                if kind == "oh" and self._client.oh_use_individually and available > 1:
                    self._log(
                        f"OH: Individual-use mode will play {available} separate board(s).",
                        "INFO",
                    )
                for batch_size in batch_sizes:
                    if not await self.run_sphere_game(channel, kind, batch_size):
                        completed_all = False
                        break
                if completed_all:
                    refill_seconds = max(300.0, float(getattr(status, "refill_minutes", None) or 60) * 60.0)
                    self._client._sphere_game_retry_after[kind] = time.monotonic() + refill_seconds
                else:
                    for waiting_kind in ("oh", "oc"):
                        self._client._sphere_game_retry_after[waiting_kind] = time.monotonic() + 300.0
                    self._client.loop.call_later(302.0, self._wake_status)
                    return  # An unfinished board must settle before another minigame starts.
        finally:
            self._client._sphere_games_running = False
