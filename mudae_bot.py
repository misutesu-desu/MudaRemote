import sys
import asyncio
import discord
from discord.ext import commands
import re
import json
import threading
import datetime
from datetime import timezone # Ensure timezone is imported
import inquirer
import logging
import time # Added for auto-restart delay
import random # Added for humanization logic
from discord.utils import time_snowflake

try:
    from discord.http import Route
except ImportError:
    Route = None

# Global bot name
BOT_NAME = "MudaRemote"

# Load presets from JSON file
presets = {}
try:
    with open("presets.json", "r", encoding="utf-8") as f:
        presets = json.load(f)
except FileNotFoundError:
    print("presets.json file not found. Please create it and enter the necessary information.")
    sys.exit(1)
except json.JSONDecodeError:
    print("Error decoding presets.json. Please check the file format.")
    sys.exit(1)


# Target bot ID (Mudae's ID)
TARGET_BOT_ID = 432610292342587392

# ANSI color codes
COLORS = {
    "INFO": "\033[94m",    # Blue
    "CLAIM": "\033[92m",   # Green
    "KAKERA": "\033[93m",  # Yellow
    "ERROR": "\033[91m",    # Red
    "CHECK": "\033[95m",    # Magenta
    "RESET": "\033[36m",    # Cyan
    "ENDC": "\033[0m"      # End Color
}

# Define claim and kakera emojis at the top level
CLAIM_EMOJIS = ['💖', '💗', '💘', '❤️', '💓', '💕', '♥️', 'castle_DarkRed']
KAKERA_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP']


def color_log(message, preset_name, log_type="INFO"):
    """Formats a log message with a timestamp, preset name, and color."""
    color_code = COLORS.get(log_type.upper(), COLORS["INFO"])
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}][{preset_name}] {message}"
    print(f"{color_code}{log_message}{COLORS['ENDC']}")
    return log_message

def write_log_to_file(log_message):
    """Writes a log message to the logs.txt file."""
    try:
        with open("logs.txt", "a", encoding='utf-8') as log_file:
            log_file.write(log_message + "\n")
    except Exception as e:
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\033[91m[{timestamp}][System] Error writing to log file: {e}\033[0m")


def print_log(message, preset_name, log_type="INFO"):
    """Prints a colored log message to the console and writes it to a file."""
    log_message_formatted = color_log(message, preset_name, log_type)
    write_log_to_file(log_message_formatted)

def is_character_embed(embed):
    """
    Positively identifies if an embed is a character roll using the most reliable structural check.
    - A true character embed uses the main 'image' field for the portrait and has no 'thumbnail'.
    - Profile, list, and status embeds use the 'thumbnail' field and have no 'image'.
    """
    if not embed:
        return False
    
    # Check for the presence of a main image URL.
    has_image = embed.image and embed.image.url
    
    # Check for the presence of a thumbnail URL.
    has_thumbnail = embed.thumbnail and embed.thumbnail.url

    # A message is a character roll if and only if it has an image and does NOT have a thumbnail.
    return has_image and not has_thumbnail


def run_bot(token, prefix, target_channel_id, roll_command, min_kakera, delay_seconds, mudae_prefix,
            log_function, preset_name, key_mode, start_delay, snipe_mode, snipe_delay,
            snipe_ignore_min_kakera_reset, wishlist,
            series_snipe_mode, series_snipe_delay, series_wishlist, roll_speed,
            kakera_snipe_mode_preset, kakera_snipe_threshold_preset,
            enable_reactive_self_snipe_preset, rolling_enabled,
            kakera_reaction_snipe_mode_preset, kakera_reaction_snipe_delay_preset,
            humanization_enabled, humanization_window_minutes, humanization_inactivity_seconds,
            dk_power_management, skip_initial_commands, use_slash_rolls):

    client = commands.Bot(command_prefix=prefix, chunk_guilds_at_startup=False, self_bot=True)

    # Suppress discord.py's default logging to avoid console clutter
    discord_logger = logging.getLogger('discord')
    discord_logger.propagate = False
    handlers = [h for h in discord_logger.handlers if isinstance(h, logging.StreamHandler)]
    for h in handlers: discord_logger.removeHandler(h)

    # Initialize client attributes from preset data
    client.preset_name = preset_name; client.min_kakera = min_kakera
    client.snipe_mode = snipe_mode; client.snipe_delay = snipe_delay
    client.snipe_ignore_min_kakera_reset = snipe_ignore_min_kakera_reset
    client.wishlist = [w.lower() for w in wishlist]
    client.series_snipe_mode = series_snipe_mode; client.series_snipe_delay = series_snipe_delay
    client.series_wishlist = [sw.lower() for sw in series_wishlist]
    client.muda_name = BOT_NAME; client.claim_right_available = False
    client.target_channel_id = target_channel_id; client.roll_speed = roll_speed
    client.mudae_prefix = mudae_prefix; client.key_mode = key_mode
    client.delay_seconds = delay_seconds
    client.sniped_messages = set(); client.snipe_happened = False
    client.series_sniped_messages = set(); client.series_snipe_happened = False
    client.kakera_value_sniped_messages = set()
    client.is_actively_rolling = False; client.interrupt_rolling = False
    client.current_min_kakera_for_roll_claim = client.min_kakera
    client.kakera_snipe_mode_active = kakera_snipe_mode_preset
    client.kakera_snipe_threshold = kakera_snipe_threshold_preset
    client.enable_reactive_self_snipe = enable_reactive_self_snipe_preset
    client.rolling_enabled = rolling_enabled
    client.rt_available = False  # Updated after parsing $tu

    client.kakera_reaction_snipe_mode_active = kakera_reaction_snipe_mode_preset
    client.kakera_reaction_snipe_delay_value = kakera_reaction_snipe_delay_preset
    client.kakera_reaction_sniped_messages = set()
    client.kakera_react_available = True
    client.kakera_react_cooldown_until_utc = None

    # Humanization settings
    client.humanization_enabled = humanization_enabled
    client.humanization_window_minutes = humanization_window_minutes
    client.humanization_inactivity_seconds = humanization_inactivity_seconds
    
    # NEW: DK Power Management setting
    client.dk_power_management = dk_power_management
    client.skip_initial_commands = skip_initial_commands

    # NEW: Claim tracking and sniping state
    client.next_claim_reset_at_utc = None  # Parsed from $tu: "next claim reset in"
    client.claim_cooldown_until_utc = None  # When we believe the claim right becomes available again
    client.snipe_watch = {}  # message_id -> { 'channel_id': int, 'char_name': str, 'ts': float }
    client.snipe_watch_expiry_seconds = 180  # auto-expire watch entries after this many seconds
    client.snipe_globally_disabled_until = None  # safety valve to temporarily disable character sniping

    client.use_slash_rolls = bool(use_slash_rolls and Route is not None)
    client.mudae_slash_cache = {}
    client.mudae_slash_missing = set()
    client.mudae_session_id = None
    client.slash_fail_streak = 0
    client.slash_fail_threshold = 3
    client.slash_min_interval = max(1.0, float(roll_speed)) if roll_speed else 1.0
    client.slash_max_backoff = 6.0
    client.last_slash_attempt = 0.0
    client.slash_rate_limited_until = 0.0

    async def health_monitor_task():
        """Monitors gateway connection and forces a restart if disconnected for too long."""
        unhealthy_streak = 0
        max_streak = 3
        while not client.is_closed():
            await asyncio.sleep(60)
            if client.latency == float('inf'):
                unhealthy_streak += 1
                log_function(f"[{client.muda_name}] Health Check: Gateway disconnected (Streak: {unhealthy_streak}/{max_streak}).", preset_name, "ERROR")
            else:
                if unhealthy_streak > 0:
                    log_function(f"[{client.muda_name}] Health Check: Gateway reconnected. Latency: {client.latency * 1000:.0f}ms.", preset_name, "INFO")
                unhealthy_streak = 0
            if unhealthy_streak >= max_streak:
                log_function(f"[{client.muda_name}] Health Check: Gateway disconnected for {max_streak} consecutive minutes. Forcing shutdown.", preset_name, "ERROR")
                try:
                    await client.close()
                except Exception as e:
                    log_function(f"[{client.muda_name}] Health Check: Exception during client.close(): {e}. The bot will now exit.", preset_name, "ERROR")
                return

    def is_character_snipe_allowed() -> bool:
        """Returns True if character sniping should be attempted based on local cooldown state."""
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if client.snipe_globally_disabled_until and now_utc < client.snipe_globally_disabled_until:
                return False
            if client.claim_cooldown_until_utc and now_utc < client.claim_cooldown_until_utc:
                return False
            return True
        except Exception:
            return True

    def is_kakera_reaction_allowed() -> bool:
        """Returns True if kakera reactions should be attempted based on local cooldown state."""
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if client.kakera_react_available:
                return True
            if client.kakera_react_cooldown_until_utc and now_utc >= client.kakera_react_cooldown_until_utc:
                client.kakera_react_available = True
                client.kakera_react_cooldown_until_utc = None
                return True
            return False
        except Exception:
            return True

    async def snipe_watch_cleanup_task():
        """Periodically cleans up stale snipe watches so we don't leak memory."""
        while not client.is_closed():
            try:
                now_ts = time.time()
                stale = [mid for mid, info in client.snipe_watch.items() if now_ts - info.get('ts', now_ts) > client.snipe_watch_expiry_seconds]
                for mid in stale:
                    client.snipe_watch.pop(mid, None)
                await asyncio.sleep(30)
            except Exception:
                await asyncio.sleep(30)

    def _refresh_session_id():
        try:
            ws = getattr(client, "ws", None)
            sid = getattr(ws, "session_id", None)
            if sid:
                client.mudae_session_id = sid
        except Exception:
            pass

    async def _fetch_mudae_slash_commands(guild_id):
        if guild_id in client.mudae_slash_cache:
            return client.mudae_slash_cache[guild_id]
        http = getattr(client, "http", None)
        if not http or Route is None:
            return None

        commands_map = {}
        data = []
        try:
            route = Route(
                "GET",
                "/applications/{application_id}/commands",
                application_id=TARGET_BOT_ID,
            )
            data = await http.request(route)
        except discord.Forbidden:
            data = []
        except Exception as e:
            log_function(f"[{client.muda_name}] SlashCmd fetch fail (global): {e}", preset_name, "ERROR")
            data = []

        for cmd in data:
            name = str(cmd.get("name", "")).lower()
            if name:
                commands_map[name] = cmd

        client.mudae_slash_cache[guild_id] = commands_map
        return commands_map

    async def _trigger_mudae_slash(channel, command_text):
        if not client.use_slash_rolls:
            return False
        if not channel or not getattr(channel, "guild", None):
            return False

        stripped = command_text.strip()
        if not stripped:
            return False
        now_ts = time.time()
        if client.slash_rate_limited_until and now_ts < client.slash_rate_limited_until:
            return False
        if client.last_slash_attempt:
            elapsed = now_ts - client.last_slash_attempt
            if elapsed < client.slash_min_interval:
                await asyncio.sleep(client.slash_min_interval - elapsed)
        client.last_slash_attempt = time.time()
        if " " in stripped:
            key = f"mixed:{stripped.split(' ', 1)[0].lower()}"
            if key not in client.mudae_slash_missing:
                log_function(
                    f"[{client.muda_name}] SlashCmd fallback: arguments unsupported for '{command_text}'.",
                    preset_name,
                    "WARN",
                )
                client.mudae_slash_missing.add(key)
            return False
        base_name = stripped.lstrip("/").lower()

        guild = channel.guild
        command_map = await _fetch_mudae_slash_commands(guild.id)
        if not command_map:
            return False

        command_data = command_map.get(base_name)
        if not command_data:
            key = f"missing:{base_name}"
            if key not in client.mudae_slash_missing:
                log_function(
                    f"[{client.muda_name}] SlashCmd missing: '{base_name}'. Fallback to text.",
                    preset_name,
                    "WARN",
                )
                client.mudae_slash_missing.add(key)
            return False

        _refresh_session_id()
        session_id = None
        ws = getattr(client, "ws", None)
        if ws and getattr(ws, "session_id", None):
            session_id = ws.session_id
        elif client.mudae_session_id:
            session_id = client.mudae_session_id

        if not session_id:
            log_function(f"[{client.muda_name}] SlashCmd fallback: session id unavailable.", preset_name, "WARN")
            return False

        payload = {
            "type": 2,
            "application_id": str(TARGET_BOT_ID),
            "guild_id": str(guild.id),
            "channel_id": str(channel.id),
            "session_id": session_id,
            "data": {
                "version": str(command_data.get("version", "")),
                "id": str(command_data.get("id", "")),
                "name": command_data.get("name"),
                "type": command_data.get("type", 1),
            },
            "nonce": str(time_snowflake(datetime.datetime.now(datetime.timezone.utc))),
        }

        invalidate_cache = False
        try:
            await client.http.request(Route("POST", "/interactions"), json=payload)
            client.slash_fail_streak = 0
            client.slash_rate_limited_until = 0.0
            return True
        except discord.HTTPException as e:
            retry_after = getattr(e, "retry_after", None)
            if retry_after:
                client.slash_rate_limited_until = time.time() + min(retry_after, client.slash_max_backoff)
                log_function(
                    f"[{client.muda_name}] SlashCmd rate limit {retry_after:.2f}s for '{base_name}'.",
                    preset_name,
                    "WARN",
                )
                await asyncio.sleep(retry_after)
            else:
                log_function(f"[{client.muda_name}] SlashCmd HTTP {e.status} for '{base_name}'.", preset_name, "ERROR")
                invalidate_cache = True
            client.slash_fail_streak += 1
        except Exception as e:
            log_function(f"[{client.muda_name}] SlashCmd err '{base_name}': {e}", preset_name, "ERROR")
            client.slash_fail_streak += 1
            invalidate_cache = True

        if invalidate_cache:
            client.mudae_slash_cache.pop(guild.id, None)
        if client.slash_fail_streak >= client.slash_fail_threshold:
            client.use_slash_rolls = False
            log_function(
                f"[{client.muda_name}] SlashCmd disabled after repeated failures; reverting to text commands.",
                preset_name,
                "WARN",
            )
        return False

    async def send_roll_command(channel, command_name):
        cmd = (command_name or "").strip()
        if not cmd:
            return

        normalized = cmd.lstrip('/')

        # Normalize to always call slash handler with leading slash for clarity
        if client.use_slash_rolls:
            slash_target = normalized
            slash_override_map = {"w": "wx", "h": "hx", "m": "mx"}
            slash_target = slash_override_map.get(slash_target.lower(), slash_target)
            slash_name = slash_target if slash_target.startswith("/") else f"/{slash_target}"
            sent = await _trigger_mudae_slash(channel, slash_name)
            if sent:
                return
            if not client.use_slash_rolls:
                # Slash mode toggled off due to failures; fall through to text command
                await channel.send(f"{client.mudae_prefix}{normalized}")
                return

        await channel.send(f"{client.mudae_prefix}{normalized}")

    @client.event
    async def on_ready():
        """Event triggered when the bot is ready and connected."""
        log_function(f"[{client.muda_name}] Bot ready: {client.user}", preset_name, "INFO")
        client.loop.create_task(health_monitor_task())
        client.loop.create_task(snipe_watch_cleanup_task())
        _refresh_session_id()
        log_function(f"[{client.muda_name}] Target Channel: {target_channel_id}", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Rolling Enabled: {'On' if client.rolling_enabled else 'Off (SNIPE-ONLY MODE)'}", preset_name, "INFO")
        if client.rolling_enabled:
            log_function(f"[{client.muda_name}] Delay: {delay_seconds}s", preset_name, "INFO")
            log_function(f"[{client.muda_name}] Key Mode: {'On' if key_mode else 'Off'}", preset_name, "INFO")
            log_function(f"[{client.muda_name}] Skip Initial Cmds: {'On' if client.skip_initial_commands else 'Off'}", preset_name, "INFO")
            log_function(f"[{client.muda_name}] Start Delay: {start_delay}s", preset_name, "INFO")
            log_function(f"[{client.muda_name}] Ext. WL Snipe: {'On' if snipe_mode else 'Off'}", preset_name, "INFO")
            if snipe_mode:
                log_function(f"[{client.muda_name}]   Ext. WL Snipe Delay: {snipe_delay}s", preset_name, "INFO")
                log_function(f"[{client.muda_name}] Wishlist (Size): {len(client.wishlist)}", preset_name, "INFO")
            log_function(f"[{client.muda_name}] Ext. Series Snipe: {'On' if series_snipe_mode else 'Off'}", preset_name, "INFO")
            if series_snipe_mode:
                log_function(f"[{client.muda_name}]   Ext. Series Snipe Delay: {series_snipe_delay}s", preset_name, "INFO")
                log_function(f"[{client.muda_name}] Series WL (Size): {len(client.series_wishlist)}", preset_name, "INFO")
            log_function(f"[{client.muda_name}] Ext. Kakera Value Snipe: {'On' if client.kakera_snipe_mode_active else 'Off'}", preset_name, "INFO")
            if client.kakera_snipe_mode_active:
                log_function(f"[{client.muda_name}]   Ext. Kakera Val. Threshold: {client.kakera_snipe_threshold}", preset_name, "INFO")
                log_function(f"[{client.muda_name}]   Ext. Kakera Val. Snipe Delay: {client.snipe_delay}s (uses general snipe_delay)", preset_name, "INFO")
            log_function(f"[{client.muda_name}] Ext. Kakera Reaction Snipe: {'On' if client.kakera_reaction_snipe_mode_active else 'Off'}", preset_name, "INFO")
            if client.kakera_reaction_snipe_mode_active:
                log_function(f"[{client.muda_name}]   Ext. Kakera React. Snipe Delay: {client.kakera_reaction_snipe_delay_value}s", preset_name, "INFO")
        
        # Retrieve target channel and validate
        channel = client.get_channel(target_channel_id)
        if not channel:
            log_function(f"[{client.muda_name}] Err: No channel {target_channel_id}", preset_name, "ERROR"); await client.close(); return
        if not isinstance(channel, discord.TextChannel):
            log_function(f"[{client.muda_name}] Err: Not text channel {target_channel_id}", preset_name, "ERROR"); await client.close(); return

        # Check permissions
        can_send = channel.permissions_for(channel.guild.me).send_messages
        can_read_history = channel.permissions_for(channel.guild.me).read_message_history
        can_react = channel.permissions_for(channel.guild.me).add_reactions
        if not can_read_history: log_function(f"[{client.muda_name}] Err: No history perm in {channel.name}", preset_name, "ERROR"); await client.close(); return
        if not can_react: log_function(f"[{client.muda_name}] Warn: No reaction perm in {channel.name}", preset_name, "ERROR")
        
        if client.rolling_enabled:
            if not can_send: log_function(f"[{client.muda_name}] Err: No send perm in {channel.name} (Rolling Enabled)", preset_name, "ERROR"); await client.close(); return
        else:
             if not can_send: log_function(f"[{client.muda_name}] Warn: No send perm in {channel.name} (Snipe-Only Mode, fallback react might be affected if it uses commands)", preset_name, "INFO")
        
        log_function(f"[{client.muda_name}] Initial delay: {start_delay}s...", preset_name, "INFO")
        await asyncio.sleep(start_delay)

        if client.rolling_enabled:
            try:
                if client.skip_initial_commands:
                    log_function(f"[{client.muda_name}] Skipping limroul/dk/daily; going straight to $tu.", preset_name, "INFO")
                    await check_status(client, channel, client.mudae_prefix)
                else:
                    log_function(f"[{client.muda_name}] Initial commands (rolling enabled)...", preset_name, "INFO")
                    await channel.send(f"{client.mudae_prefix}limroul 1 1 1 1"); await asyncio.sleep(1.0)
                    # NEW: Conditionally send $dk based on the new setting
                    if not client.dk_power_management:
                        await channel.send(f"{client.mudae_prefix}dk"); await asyncio.sleep(1.0)
                    else:
                        log_function(f"[{client.muda_name}] Skipping initial $dk due to DK Power Management.", preset_name, "INFO")
                    await channel.send(f"{client.mudae_prefix}daily"); await asyncio.sleep(1.0)
                    await check_status(client, channel, client.mudae_prefix)
            except discord.errors.Forbidden as e: log_function(f"[{client.muda_name}] Err: Forbidden in setup (rolling) {e}", preset_name, "ERROR"); await client.close()
            except Exception as e: log_function(f"[{client.muda_name}] Err: Unexpected in setup (rolling) {e}", preset_name, "ERROR"); await client.close()
        else:
            log_function(f"[{client.muda_name}] Snipe-Only Mode active. Performing single $tu to initialize cooldown timers. Listening for snipes...", preset_name, "INFO")
            try:
                me = channel.guild.me if channel.guild else None
                can_send = channel.permissions_for(me).send_messages if me else True
                if can_send:
                    await check_status(client, channel, client.mudae_prefix, proceed_to_rolls=False)
                else:
                    log_function(f"[{client.muda_name}] Snipe-Only: No send permission to run initial $tu.", preset_name, "WARN")
            except Exception as e:
                log_function(f"[{client.muda_name}] Error during initial $tu in snipe-only mode: {e}", preset_name, "ERROR")

    async def handle_dk_power_management(client, channel, tu_content):
        """
        NEW: Analyzes $tu output to decide if $dk needs to be sent.
        """
        # Minimal logging: only log on action or errors
        # Support EN and PT-BR variants for "$dk is ready!" / "$dk está pronto!"
        content_lower = tu_content.lower()
        if not ("$dk is ready!" in content_lower or "$dk está pronto!" in content_lower or "$dk esta pronto!" in content_lower):
            return

        try:
            # Power line is language-agnostic ("Power: **100%**"), allow any case
            power_match = re.search(r"power:\s*\*\*(\d+)%\*\*", content_lower)
            # EN exact and PT-BR exact as provided
            # EN: "Each kakera reaction consumes 40%"
            # PT-BR: "Cada reação de kakera consume 36% de seu reaction power."
            consumption_match = re.search(r"(?:each kakera reaction consumes|cada reação de kakera consume)\s*(\d+)%", content_lower)
            
            if not power_match or not consumption_match:
                log_function(f"[{client.muda_name}] DK Power Management: Could not parse power/consumption values. Skipping.", preset_name, "WARN")
                return
            
            current_power = int(power_match.group(1))
            consumption_cost = int(consumption_match.group(1))
            
            if current_power < consumption_cost:
                log_function(f"[{client.muda_name}] DK: activate ({current_power}%<{consumption_cost}%)", preset_name, "KAKERA")
                await channel.send(f"{client.mudae_prefix}dk")
                await asyncio.sleep(1.5) # Wait a bit after sending command
            else:
                pass

        except Exception as e:
            log_function(f"[{client.muda_name}] DK error: {e}", preset_name, "ERROR")

    async def check_status(client, channel, mudae_prefix, proceed_to_rolls: bool = True):
        """Checks the user's status ($tu) to determine claim/cooldown and rolls availability.
        When proceed_to_rolls is False (e.g., snipe-only refresh), only parses and updates timestamps.
        """
        log_function(f"[{client.muda_name}] Checking $tu...", client.preset_name, "CHECK")
        error_count = 0; max_retries = 5
        tu_message_content = None

        while True:
            await channel.send(f"{mudae_prefix}tu"); await asyncio.sleep(2.5)
            tu_message_content = None
            async for msg in channel.history(limit=10):
                if msg.author.id == TARGET_BOT_ID and msg.content:
                    content_lower = msg.content.lower()
                    # Check for keywords in both English and Portuguese to identify the correct message
                    has_rolls_info_en = re.search(r"rolls?.*left", content_lower)
                    has_rolls_info_pt = re.search(r"rolls?.*restantes", content_lower)
                    has_claim_info_en = re.search(r"you __can__ claim|can't claim for another", content_lower)
                    # PT exact phrases from Mudae
                    has_claim_info_pt = re.search(r"você __pode__ se casar agora mesmo!|calma aí, falta um tempo antes que você possa se casar novamente", content_lower)
                    if (has_rolls_info_en and has_claim_info_en) or \
                       (has_rolls_info_pt and has_claim_info_pt):
                        tu_message_content = msg.content
                        break
            
            if not tu_message_content:
                error_count += 1
                log_function(f"[{client.muda_name}] Err $tu ({error_count}/{max_retries}): Response not found/identified.", preset_name, "ERROR")
                if error_count >= max_retries:
                    if client.rolling_enabled and proceed_to_rolls:
                        log_function(f"[{client.muda_name}] Max $tu retries. Wait 30m.", preset_name, "ERROR")
                        await asyncio.sleep(1800)
                        error_count = 0
                    else:
                        log_function(f"[{client.muda_name}] Max $tu retries reached in snipe-only init. Skipping initialization for now.", preset_name, "WARN")
                        return
                else:
                    log_function(f"[{client.muda_name}] Retry $tu in 7s.", preset_name, "ERROR")
                    await asyncio.sleep(7)
                continue
            else:
                break

        # NEW: Handle DK Power Management logic here, after getting the $tu message
        if client.dk_power_management and client.rolling_enabled:
            await handle_dk_power_management(client, channel, tu_message_content)

        parse_source = tu_message_content
        try:
            own_names = set()
            if client.user:
                try:
                    if getattr(client.user, "name", None):
                        own_names.add(client.user.name.lower())
                except Exception:
                    pass
                try:
                    dn = getattr(client.user, "display_name", None)
                    if dn:
                        own_names.add(dn.lower())
                except Exception:
                    pass
                try:
                    gn = getattr(client.user, "global_name", None)
                    if gn:
                        own_names.add(gn.lower())
                except Exception:
                    pass
            guild_me = None
            try:
                guild_me = channel.guild.me if channel.guild else None
            except Exception:
                guild_me = None
            if guild_me:
                try:
                    if getattr(guild_me, "display_name", None):
                        own_names.add(guild_me.display_name.lower())
                except Exception:
                    pass
                try:
                    if getattr(guild_me, "name", None):
                        own_names.add(guild_me.name.lower())
                except Exception:
                    pass

            def find_personal_section(text, names):
                if not names:
                    return None
                pattern = re.compile(r"^\*\*([^*]+)\*\*,", re.MULTILINE)
                matches = list(pattern.finditer(text))
                if not matches:
                    return None
                for idx, match in enumerate(matches):
                    candidate = match.group(1).strip().lower()
                    if candidate in names:
                        start = match.start()
                        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
                        return text[start:end].strip()
                return None

            personal_section = find_personal_section(tu_message_content, own_names)
            if personal_section:
                parse_source = personal_section
        except Exception:
            parse_source = tu_message_content

        content_lower = parse_source.lower()
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        # Parse $rt availability from $tu
        try:
            # Support EN "$rt is available!" and PT-BR "$rt está pronto!"
            if ("$rt is available!" in content_lower) or ("$rt está pronto!" in content_lower) or ("$rt esta pronto!" in content_lower):
                client.rt_available = True
                log_function(f"[{client.muda_name}] RT: Yes.", preset_name, "INFO")
            else:
                # Example: "The cooldown of $rt is not over. Time left: **2h 03** min. ($rtu)"
                match_rt_cd_en = re.search(r"the cooldown of \$rt is not over\. time left: \*\*(\d+h)?\s*(\d+)\*\* min", content_lower)
                # PT-BR exact: "A recarga do $rt ainda não acabou. Tempo restante: **20h 00** min. ($rtu)"
                match_rt_cd_pt = re.search(r"a recarga do \$rt ainda não acabou\. tempo restante: \*\*(\d+h)?\s*(\d+)\*\* min", content_lower)
                match_rt_cd = match_rt_cd_en or match_rt_cd_pt
                if match_rt_cd:
                    h_s = match_rt_cd.group(1); h_rt = int(h_s[:-1]) if h_s else 0; m_rt = int(match_rt_cd.group(2))
                    client.rt_available = False
                    log_function(f"[{client.muda_name}] RT: No. Reset: {h_rt}h {m_rt}m.", preset_name, "INFO")
                else:
                    # If ambiguous, assume not available
                    client.rt_available = False
                    log_function(f"[{client.muda_name}] RT: Unknown status in $tu. Assume No.", preset_name, "WARN")
        except Exception as e:
            log_function(f"[{client.muda_name}] RT parse error: {e}", preset_name, "ERROR")
        claim_reset_proceed = False
        lang_log_suffix = ""

        # Regex for both English and Portuguese claim statuses
        match_can_claim_en = re.search(r"you __can__ claim.*?next claim reset .*?\*\*(\d+h)?\s*(\d+)\*\* min\.?", content_lower)
        # PT exact phrase: "você __pode__ se casar agora mesmo! A próxima reinicialização é em **1h 36** min."
        match_can_claim_pt = re.search(r"você __pode__ se casar agora mesmo!.*?a próxima reinicialização é em .*?\*\*(\d+h)?\s*(\d+)\*\* min\.?", content_lower)
        match_cant_claim_en = re.search(r"can't claim for another \*\*(\d+h)?\s*(\d+)\*\* min\.?", content_lower)
        # PT exact phrase: "Calma aí, falta um tempo antes que você possa se casar novamente **59** min."
        match_cant_claim_pt = re.search(r"calma aí, falta um tempo antes que você possa se casar novamente \*\*(\d+)\*\* min\.?", content_lower)

        match_c = None; match_c_wait = None
        if match_can_claim_en: client.claim_right_available = True; match_c = match_can_claim_en; lang_log_suffix = " (EN)"
        elif match_can_claim_pt: client.claim_right_available = True; match_c = match_can_claim_pt; lang_log_suffix = " (PT)"
        elif match_cant_claim_en: client.claim_right_available = False; match_c_wait = match_cant_claim_en; lang_log_suffix = " (EN)"
        elif match_cant_claim_pt: client.claim_right_available = False; match_c_wait = match_cant_claim_pt; lang_log_suffix = " (PT)"

        if match_c:
            h_s = match_c.group(1); h = int(h_s[:-1]) if h_s else 0; m = int(match_c.group(2))
            log_function(f"[{client.muda_name}] Claim: Yes. Reset: {h}h {m}m.{lang_log_suffix}", preset_name, "INFO")
            if (h * 60 + m) * 60 <= 3600 and client.snipe_ignore_min_kakera_reset: client.current_min_kakera_for_roll_claim = 0
            else: client.current_min_kakera_for_roll_claim = client.min_kakera
            claim_reset_proceed = True
            try:
                # Update next claim reset absolute timestamp from relative time (no extra log for minimal output)
                minutes_to_reset = h * 60 + m
                client.next_claim_reset_at_utc = now_utc + datetime.timedelta(minutes=minutes_to_reset)
                client.claim_cooldown_until_utc = None  # claim is currently available
            except Exception as e:
                log_function(f"[{client.muda_name}] Failed to compute next claim reset timestamp: {e}", preset_name, "ERROR")
        elif match_c_wait:
            h_s = match_c_wait.group(1); h = int(h_s[:-1]) if h_s else 0; m = int(match_c_wait.group(2))
            log_function(f"[{client.muda_name}] Claim: No. Reset: {h}h {m}m.{lang_log_suffix}", preset_name, "INFO")
            client.current_min_kakera_for_roll_claim = client.min_kakera

            immediate_roll_allowed = client.rolling_enabled and proceed_to_rolls and (client.key_mode or client.rt_available)
            if immediate_roll_allowed:
                reason_txt = "KeyMode on" if client.key_mode else "$rt available"
                log_function(f"[{client.muda_name}] {reason_txt}. Check rolls.", preset_name, "INFO")
                claim_reset_proceed = True
            elif client.rolling_enabled and proceed_to_rolls:
                await humanized_wait_and_proceed(client, channel, (h * 60 + m), "claim reset")
                await check_status(client, channel, mudae_prefix)
                return
            else:
                return
            try:
                # Store our personal claim cooldown absolute timestamp
                minutes_to_claim = h * 60 + m
                client.claim_cooldown_until_utc = now_utc + datetime.timedelta(minutes=minutes_to_claim)
            except Exception as e:
                log_function(f"[{client.muda_name}] Failed to compute personal claim cooldown timestamp: {e}", preset_name, "ERROR")
        else:
            log_function(f"[{client.muda_name}] Ambiguous/Unknown claim status in $tu. Assume No. Check rolls.", preset_name, "WARN")
            client.claim_right_available = False; client.current_min_kakera_for_roll_claim = client.min_kakera
            claim_reset_proceed = client.rolling_enabled and proceed_to_rolls

        # Parse kakera reaction availability
        try:
            kakera_ready_en = re.search(r"you __can__ react to kakera right now!", content_lower)
            kakera_ready_pt = re.search(r"(?:você|voce) __pode__ (?:reagir a|pegar) kakera agora(?: mesmo)?!", content_lower)
            kakera_wait_en = re.search(r"can't react to kakera.*?\*\*(\d+h)?\s*(\d+)\*\* min", content_lower)
            kakera_wait_pt = re.search(r"(?:você|voce) (?:não|nao) pode (?:reagir a|pegar) kakera.*?\*\*(\d+h)?\s*(\d+)\*\* min", content_lower)
            if kakera_ready_en or kakera_ready_pt:
                client.kakera_react_available = True
                client.kakera_react_cooldown_until_utc = None
                log_function(f"[{client.muda_name}] Kakera React: Yes.", preset_name, "KAKERA")
            elif kakera_wait_en or kakera_wait_pt:
                match_kr = kakera_wait_en or kakera_wait_pt
                h_s = match_kr.group(1)
                h = int(h_s[:-1]) if h_s else 0
                m = int(match_kr.group(2)) if match_kr.group(2) else 0
                minutes_to_reset = h * 60 + m
                client.kakera_react_available = False
                client.kakera_react_cooldown_until_utc = now_utc + datetime.timedelta(minutes=minutes_to_reset)
                log_function(f"[{client.muda_name}] Kakera React: No. Reset: {h}h {m}m.", preset_name, "KAKERA")
            elif "can't react to kakera" in content_lower or "não pode reagir a kakera" in content_lower or "nao pode reagir a kakera" in content_lower or "não pode pegar kakera" in content_lower or "nao pode pegar kakera" in content_lower:
                client.kakera_react_available = False
                log_function(f"[{client.muda_name}] Kakera React: No (Cooldown, time unknown).", preset_name, "KAKERA")
        except Exception as e:
            log_function(f"[{client.muda_name}] Kakera parse error: {e}", preset_name, "ERROR")

        # Independently attempt to parse the "next claim reset" relative time anywhere in the message and store absolute timestamp
        try:
            match_next_reset_en = re.search(r"next claim reset .*?\*\*(\d+h)?\s*(\d+)\*\* min", content_lower)
            match_next_reset_pt = re.search(r"a próxima reinicialização .*?\*\*(\d+h)?\s*(\d+)\*\* min", content_lower)
            match_next_reset = match_next_reset_en or match_next_reset_pt
            if match_next_reset:
                h_s2 = match_next_reset.group(1); h2 = int(h_s2[:-1]) if h_s2 else 0; m2 = int(match_next_reset.group(2))
                client.next_claim_reset_at_utc = now_utc + datetime.timedelta(minutes=(h2 * 60 + m2))
                # Minimal: do not log this secondary parse to avoid duplication
        except Exception as e:
            log_function(f"[{client.muda_name}] Error parsing 'next claim reset' timestamp: {e}", preset_name, "ERROR")

        if claim_reset_proceed and client.rolling_enabled and proceed_to_rolls:
            await check_rolls_left_tu(client, channel, mudae_prefix, log_function, preset_name,
                                        tu_message_content_for_rolls=tu_message_content,
                                        ignore_limit_for_post_roll=(client.current_min_kakera_for_roll_claim == 0),
                                        key_mode_only_kakera_for_post_roll=(((client.key_mode) or client.rt_available) and not client.claim_right_available))
            return
        if client.rolling_enabled and proceed_to_rolls:
            log_function(f"[{client.muda_name}] Unexp. state in $tu parse. Retry check_status.", preset_name, "ERROR")
            await asyncio.sleep(7)
            await check_status(client, channel, mudae_prefix)
        return

    async def check_rolls_left_tu(client, channel, mudae_prefix, log_function, preset_name,
                                  tu_message_content_for_rolls, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll):
        """Parses the number of rolls left from the $tu message content."""
        content_lower = tu_message_content_for_rolls.lower()
        rolls_left = 0
        us_rolls_left = 0
        reset_time_r = 0
        lang_log_suffix_rolls = ""
        parsed_rolls_info = False

        # Regex for both English and Portuguese roll counts
        main_match_en = re.search(r"you have \*\*(\d+)\*\* rolls?(.*?)left", content_lower)
        # PT exact phrase: "Você tem **15** rolls restantes."
        main_match_pt = re.search(r"você tem \*\*(\d+)\*\* rolls?(.*?)restantes", content_lower)

        main_match = None
        if main_match_en:
            main_match = main_match_en
            lang_log_suffix_rolls = " (EN)"
            parsed_rolls_info = True
        elif main_match_pt:
            main_match = main_match_pt
            lang_log_suffix_rolls = " (PT)"
            parsed_rolls_info = True

        if parsed_rolls_info:
            rolls_left = int(main_match.group(1))
            
            # Check for bonus rolls from $us
            middle_text = main_match.group(2)
            us_match = re.search(r"\(\+\*\*(\d+)\*\* \$us\)", middle_text)
            if us_match:
                us_rolls_left = int(us_match.group(1))

            # Find the roll reset time
            match_reset_en = re.search(r"next rolls? reset in \*\*(\d+h)?\s*(\d+)\*\* min", content_lower)
            match_reset_pt = None
            try:
                # PT message often omits the word 'rolls', so search after the rolls-count segment
                pt_search_zone = content_lower[main_match.end():]
                match_reset_pt = re.search(r"a próxima reinicialização é em \*\*(\d+h)?\s*(\d+)\*\* min", pt_search_zone)
            except Exception:
                match_reset_pt = None
            reset_match = match_reset_en or match_reset_pt
            if reset_match:
                h_s = reset_match.group(1); h_r = int(h_s[:-1]) if h_s else 0; m_r = int(reset_match.group(2))
                reset_time_r = h_r * 60 + m_r
            else:
                log_function(f"[{client.muda_name}] Warn: Roll reset time not found.{lang_log_suffix_rolls}", preset_name, "WARN");
                reset_time_r = 0
            
            total_rolls = rolls_left + us_rolls_left

            if total_rolls == 0:
                if reset_time_r <= 0:
                    log_function(f"[{client.muda_name}] Invalid roll reset time ({reset_time_r}m), using 60m.", preset_name, "INFO"); reset_time_r = 60
                
                await humanized_wait_and_proceed(client, channel, reset_time_r, "rolls reset")
                await check_status(client, channel, mudae_prefix); return
            else:
                # Minimal rollout summary
                log_detail = f" (+{us_rolls_left} $us)" if us_rolls_left > 0 else ""
                log_function(f"[{client.muda_name}] Rolls: {total_rolls}{log_detail}. Reset: {reset_time_r}m", preset_name, "INFO")
                await start_roll_commands(client, channel, total_rolls, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll)
                return
        else:
            log_function(f"[{client.muda_name}] CRITICAL: Roll parse fail from $tu. Re-check status.", preset_name, "ERROR")
            await asyncio.sleep(30); await check_status(client, channel, mudae_prefix); return

    async def start_roll_commands(client, channel, rolls_left, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll):
        """Starts sending roll commands and initiates post-roll processing."""
        log_text = f"Starting {rolls_left} rolls"
        if client.enable_reactive_self_snipe: log_text += " (Reactive Snipe ON)"
        else: log_text += " (Reactive Snipe OFF)"
        log_function(f"[{client.muda_name}] {log_text}", client.preset_name, "INFO")
        start_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=0.5)
        client.is_actively_rolling = True; client.interrupt_rolling = False
        for i in range(rolls_left):
            if client.interrupt_rolling:
                log_function(f"[{client.muda_name}] Rolling interrupted. {i}/{rolls_left} sent.", client.preset_name, "INFO")
                client.interrupt_rolling = False; break
            try:
                await send_roll_command(channel, roll_command)
                await asyncio.sleep(max(client.roll_speed, 0.2 if client.use_slash_rolls else 0))
            except discord.errors.HTTPException as e: log_function(f"[{client.muda_name}] Error sending roll: {e}. Skip.", preset_name, "ERROR"); await asyncio.sleep(1)
        client.is_actively_rolling = False
        log_function(f"[{client.muda_name}] Rolls sent/interrupted. Wait Mudae msgs...", client.preset_name, "INFO")
        
        await asyncio.sleep(5) # Wait for messages to populate
        mudae_messages_to_process = []; fetch_limit = rolls_left * 2 + 10; processed_count = 0
        try:
            # Fetch messages after the rolling started
            async for msg in channel.history(limit=fetch_limit, after=start_time, oldest_first=False):
                processed_count += 1
                if msg.author.id == TARGET_BOT_ID and msg.embeds:
                    mudae_messages_to_process.append(msg)
            mudae_messages_to_process.reverse() # Process in chronological order
            log_function(f"[{client.muda_name}] Fetched {processed_count} msgs. Processing {len(mudae_messages_to_process)} post-roll.", client.preset_name, "INFO")
            if mudae_messages_to_process:
                 await handle_mudae_messages(client, channel, mudae_messages_to_process, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll)
            else: log_function(f"[{client.muda_name}] No further char msgs for post-roll.", client.preset_name, "INFO")
        except Exception as e: log_function(f"[{client.muda_name}] Err fetch/process post-roll: {e}", preset_name, "ERROR")
        
        await asyncio.sleep(2)
        if client.snipe_happened or client.series_snipe_happened:
            log_function(f"[{client.muda_name}] Claim/Snipe occurred. Re-check status.", client.preset_name, "INFO")
            client.snipe_happened = False; client.series_snipe_happened = False
        else: log_function(f"[{client.muda_name}] Rolls done. Re-check status.", client.preset_name, "INFO")
        await asyncio.sleep(1); await check_status(client, channel, client.mudae_prefix)


    async def handle_mudae_messages(client, channel, mudae_messages, ignore_limit_param, key_mode_only_kakera_param):
        """Handles a batch of messages after rolling to decide what to claim or react to."""
        kakera_claims = []
        char_claims_post = []
        wl_claims_post = []
        min_kak_post = 0 if ignore_limit_param else client.min_kakera
        log_function(f"[{client.muda_name}] Post-Roll Handle. MinKak(gen):{min_kak_post} (IgnLmtP:{ignore_limit_param},KeyMNoClaimP:{key_mode_only_kakera_param})", preset_name, "CHECK")

        for msg in mudae_messages:
            if not msg.embeds:
                continue

            embed = msg.embeds[0]
            # Only process messages that are identified as characters.
            if not is_character_embed(embed):
                continue
            
            # Check for kakera buttons first.
            is_kakera_message = msg.components and any(hasattr(b.emoji, 'name') and b.emoji.name in KAKERA_EMOJIS for c in msg.components for b in c.children)
            if is_kakera_message:
                kakera_claims.append(msg)
            # If it's not a kakera message, check if it's a claimable character.
            # This prevents processing embeds that look like characters but have no claim buttons (e.g., special event messages).
            elif (client.claim_right_available or key_mode_only_kakera_param):
                is_claimable_char = msg.components and any(hasattr(b.emoji, 'name') and b.emoji.name in CLAIM_EMOJIS for c in msg.components for b in c.children)
                if is_claimable_char:
                    char_n = embed.author.name.lower()
                    desc = embed.description or ""
                    k_v = 0
                    # Updated regex to handle markdown (e.g., **123**) around kakera value.
                    match_k = re.search(r"\**(\d{1,3}(?:,\d{3})*|\d+)\**<:kakera:", desc)
                    if match_k:
                        try:
                            k_v = int(match_k.group(1).replace(",", ""))
                        except ValueError:
                            pass
                    
                    is_wl = any(w == char_n for w in client.wishlist)
                    
                    if is_wl:
                        wl_claims_post.append((msg, char_n, k_v))
                    elif k_v >= min_kak_post:
                        char_claims_post.append((msg, char_n, k_v))

        # Process Kakera claims first, as they don't use the claim right
        for msg_k in kakera_claims:
            await claim_character(client, channel, msg_k, is_kakera=True)
            await asyncio.sleep(0.3)
        
        # Process Character/Wishlist claims
        claimed_post = False
        msg_claimed_id = -1
        if client.claim_right_available and wl_claims_post and is_character_snipe_allowed():
            msg_c, n, v = wl_claims_post[0]
            log_function(f"[{client.muda_name}] (Post) Gen. WL: {n}", preset_name, "CLAIM")
            if await claim_character(client, channel, msg_c, is_kakera=False):
                claimed_post = True
                client.claim_right_available = False
                msg_claimed_id = msg_c.id
        elif client.claim_right_available and char_claims_post and is_character_snipe_allowed():
            char_claims_post.sort(key=lambda x: x[2], reverse=True)
            msg_c, n, v = char_claims_post[0]
            log_function(f"[{client.muda_name}] (Post) Gen. HV: {n} ({v})", preset_name, "CLAIM")
            if await claim_character(client, channel, msg_c, is_kakera=False):
                claimed_post = True
                client.claim_right_available = False
                msg_claimed_id = msg_c.id
        
        # Process Roll-back ($rt) if applicable (Key Mode or after a successful claim)
        if key_mode_only_kakera_param or claimed_post:
            rt_targets = [i for i in wl_claims_post if i[0].id != msg_claimed_id] + [i for i in char_claims_post if i[0].id != msg_claimed_id]
            rt_targets.sort(key=lambda x: x[2], reverse=True)
            if rt_targets:
                msg_rt, n_rt, v_rt = rt_targets[0]
                if v_rt >= client.min_kakera:
                    log_function(f"[{client.muda_name}] (Post) RT: {n_rt} ({v_rt}) vs MinKakRT: {client.min_kakera}", preset_name, "CLAIM")
                    try:
                        await channel.send(f"{client.mudae_prefix}rt")
                        # Mark RT as consumed to avoid multiple attempts until next $tu
                        client.rt_available = False
                        await asyncio.sleep(0.7)
                        await claim_character(client, channel, msg_rt, is_rt_claim=True)
                    except Exception as e:
                        log_function(f"[{client.muda_name}] (Post) RT Err: {e}", preset_name, "ERROR")
                elif v_rt >= min_kak_post:
                    log_function(f"[{client.muda_name}] (Post) RT Skipped: {n_rt} ({v_rt}) < MinKakRT: {client.min_kakera} (but was >= Gen. Post-Roll MinKak: {min_kak_post})", preset_name, "INFO")


    async def claim_character(client, channel, msg, is_kakera=False, is_rt_claim=False):
        """Clicks a button or adds a reaction to claim a character or kakera."""
        if not msg or not msg.embeds:
            log_function(f"[{client.muda_name}] Invalid msg to claim_character.", preset_name, "ERROR")
            return False
        embed = msg.embeds[0]
        char_name = embed.author.name if embed.author and embed.author.name else "Unknown"
        log_px = f"[{client.muda_name}]"

        # Gate character snipes by our local cooldown awareness (kakera is not gated; RT claims bypass this gate)
        if not is_kakera and not is_rt_claim and not is_character_snipe_allowed():
            log_function(f"{log_px} Claim blocked by local cooldown for {char_name}.", client.preset_name, "RESET")
            return False

        # Kakera logic: click all available kakera buttons
        if is_kakera:
            if not is_kakera_reaction_allowed():
                log_function(f"{log_px} Kakera blocked by cooldown: {char_name}", client.preset_name, "KAKERA")
                return False
            log_sx = f": {char_name}"
            any_button_clicked = False
            if msg.components:
                for comp in msg.components:
                    for btn in comp.children:
                        if hasattr(btn.emoji, 'name') and btn.emoji and btn.emoji.name in KAKERA_EMOJIS:
                            try:
                                emoji_name = btn.emoji.name
                                log_function(f"{log_px} Kakera ({emoji_name}){log_sx}", client.preset_name, "KAKERA")
                                await btn.click()
                                any_button_clicked = True
                                await asyncio.sleep(0.5)  # Small delay between clicks on the same message
                            except discord.errors.NotFound:
                                log_function(f"{log_px} Kakera ({emoji_name}) Click Fail (NotFound){log_sx}", preset_name, "ERROR")
                            except discord.errors.HTTPException as e:
                                log_function(f"{log_px} Kakera ({emoji_name}) Click Fail (HTTP {e.status}){log_sx}", preset_name, "ERROR")
                            except Exception as e:
                                log_function(f"{log_px} Kakera ({emoji_name}) Click Fail (Unexp {e}){log_sx}", preset_name, "ERROR")
            return any_button_clicked

        # Logic for normal claims and RT claims (click once and exit)
        log_ty = "CLAIM"
        btns_to_click = CLAIM_EMOJIS
        log_action_desc = "Claim"
        log_sx = f": {char_name}"
        if is_rt_claim:
            log_action_desc = "RT Claim"

        btn_clicked_ok = False
        if msg.components:
            for comp in msg.components:
                if btn_clicked_ok: break
                for btn in comp.children:
                    if hasattr(btn.emoji, 'name') and btn.emoji and btn.emoji.name in btns_to_click:
                        try:
                            log_function(f"{log_px} {log_action_desc}{log_sx}", client.preset_name, log_ty)
                            await btn.click()
                            btn_clicked_ok = True
                            await asyncio.sleep(1.5)
                            # Register snipe watch to track the outcome
                            try:
                                client.snipe_watch[msg.id] = {
                                    'channel_id': msg.channel.id,
                                    'char_name': char_name,
                                    'ts': time.time(),
                                }
                            except Exception:
                                pass
                            return True
                        except discord.errors.NotFound:
                            log_function(f"{log_px} {log_action_desc} Fail (NotFound){log_sx}", preset_name, "ERROR")
                            return False
                        except discord.errors.HTTPException as e:
                            log_function(f"{log_px} {log_action_desc} Fail (HTTP {e.status}){log_sx}", preset_name, "ERROR")
                            return False
                        except Exception as e:
                            log_function(f"{log_px} {log_action_desc} Fail (Unexp {e}){log_sx}", preset_name, "ERROR")
                            return False
        
        # Fallback to reaction if no button was found or clicked (and it's not an RT attempt)
        if not btn_clicked_ok and not is_rt_claim:
            log_function(f"{log_px} No btn for {char_name}. Fallback react.", preset_name, "INFO")
            try:
                log_function(f"{log_px} {log_action_desc}{log_sx} (react)", client.preset_name, log_ty)
                await msg.add_reaction("💖")
                await asyncio.sleep(1.5)
                # Register snipe watch to track the outcome
                try:
                    client.snipe_watch[msg.id] = {
                        'channel_id': msg.channel.id,
                        'char_name': char_name,
                        'ts': time.time(),
                    }
                except Exception:
                    pass
                return True
            except Exception as e:
                log_function(f"{log_px} {log_action_desc} React Fail{log_sx}: {e}", preset_name, "ERROR")
                return False
        elif not btn_clicked_ok:
            log_function(f"{log_px} No btn for {log_action_desc} on {char_name}", preset_name, "INFO")
        
        return False

    async def humanized_wait_and_proceed(client, channel, base_reset_minutes, reason="reset"):
        """
        Waits for a reset using a more human-like pattern.
        If humanization is disabled, it performs a simple wait.
        Otherwise, it picks a random time within a window, then waits for channel inactivity.
        """
        if not client.humanization_enabled:
            # Fallback to the old, simple wait logic if humanization is disabled
            wait_seconds = (base_reset_minutes * 60) + client.delay_seconds
            if wait_seconds <= 0:
                wait_seconds = max(client.delay_seconds + 60, 240)
            end_time = datetime.datetime.now() + datetime.timedelta(seconds=wait_seconds)
            log_function(
                f"[{client.muda_name}] Wait {reason}: {wait_seconds:.0f}s (~{wait_seconds/60:.1f}m) | starts at {end_time.strftime('%Y-%m-%d %H:%M:%S')}",
                preset_name,
                "RESET",
            )
            await asyncio.sleep(wait_seconds)
            log_function(f"[{client.muda_name}] {reason} done.", preset_name, "RESET")
            return

        # Humanized wait logic
        # Minimal log: choose a random time after reset and then ensure brief inactivity
        
        # 1. Calculate the random wait time
        min_wait_sec = max(0.0, base_reset_minutes * 60)
        window_sec = max(0.0, client.humanization_window_minutes * 60)

        if min_wait_sec <= 0:
            inferred_wait = None
            if reason and reason.lower().startswith("claim") and client.next_claim_reset_at_utc:
                try:
                    inferred_wait = (client.next_claim_reset_at_utc - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
                except Exception:
                    inferred_wait = None
            if inferred_wait and inferred_wait > 0:
                min_wait_sec = inferred_wait
            if min_wait_sec <= 0:
                min_wait_sec = max(client.delay_seconds + 60, 240)

        max_wait_sec = min_wait_sec + window_sec
        if window_sec <= 0:
            random_wait_seconds = min_wait_sec
        else:
            random_wait_seconds = random.uniform(min_wait_sec, max_wait_sec)
        
        end_time = datetime.datetime.now() + datetime.timedelta(seconds=random_wait_seconds)
        log_function(
            f"[{client.muda_name}] Humanized {reason}: ~{random_wait_seconds/60:.1f}m | starts at {end_time.strftime('%Y-%m-%d %H:%M:%S')}",
            preset_name,
            "RESET",
        )
        await asyncio.sleep(random_wait_seconds)

        # 2. Wait for channel inactivity
        while True:
            try:
                # Correctly get the last message from the async iterator
                last_message = None
                async for msg in channel.history(limit=1):
                    last_message = msg
                
                if not last_message: # Should be rare, but handle if channel is empty
                    break

                now_utc = datetime.datetime.now(timezone.utc)
                time_since_last_message = (now_utc - last_message.created_at).total_seconds()
                
                if time_since_last_message >= client.humanization_inactivity_seconds:
                    break
                else:
                    wait_needed = client.humanization_inactivity_seconds - time_since_last_message + 0.5 # Add small buffer
                    await asyncio.sleep(wait_needed)

            except Exception as e:
                # Minimal: avoid noisy logs here; just back off briefly if needed
                await asyncio.sleep(client.humanization_inactivity_seconds)
                break

    @client.event
    async def on_message(message):
        """The main event handler for all incoming messages from Mudae."""
        # --- Initial filtering ---
        if message.author.id != TARGET_BOT_ID or message.channel.id != client.target_channel_id:
            if client.rolling_enabled: await client.process_commands(message)
            return
        if not message.embeds: return
        embed = message.embeds[0]
        
        # --- Handle non-character embeds (e.g., $daily) for kakera reactions ---
        if not is_character_embed(embed):
            if client.kakera_reaction_snipe_mode_active and message.id not in client.kakera_reaction_sniped_messages:
                # Check for the presence of a kakera button.
                if message.components and any(hasattr(b.emoji, 'name') and b.emoji.name in KAKERA_EMOJIS for c in message.components for b in c.children):
                    client.kakera_reaction_sniped_messages.add(message.id)
                    log_subject_name = "Kakera Event"
                    if embed.author and embed.author.name: log_subject_name = embed.author.name
                    elif embed.description: log_subject_name = embed.description.splitlines()[0][:30]
                    log_function(f"[{client.muda_name}] Ext.KakeraReact Snipe: {log_subject_name} (Delay {client.kakera_reaction_snipe_delay_value}s)", client.preset_name, "KAKERA")
                    await asyncio.sleep(client.kakera_reaction_snipe_delay_value)
                    await claim_character(client, message.channel, message, is_kakera=True)
            
            if client.rolling_enabled:
                await client.process_commands(message) # Still allow bot commands to be processed
            return

        # --- From this point on, we are sure it's a character embed ---

        process_further = True
        # --- Logic for reactive self-snipe during own rolls ---
        if client.rolling_enabled and client.enable_reactive_self_snipe and client.is_actively_rolling and client.claim_right_available and is_character_snipe_allowed():
            char_name_l = embed.author.name.lower(); desc = embed.description or ""; series_l=(desc.splitlines()[0] if desc else "").lower(); k_val=0
            match_k = re.search(r"\**(\d{1,3}(?:,\d{3})*|\d+)\**<:kakera:", desc)
            if match_k:
                try: k_val = int(match_k.group(1).replace(",",""))
                except ValueError: pass
            is_wl = any(w == char_name_l for w in client.wishlist)
            is_series_wl = client.series_wishlist and any(sw in series_l for sw in client.series_wishlist)
            is_k_snipe_criterion = client.kakera_snipe_mode_active and k_val >= client.kakera_snipe_threshold
            
            if is_wl or is_series_wl or is_k_snipe_criterion:
                # Also ensure a claim button is present before attempting to snipe.
                if message.components and any(hasattr(b.emoji, 'name') and b.emoji.name in CLAIM_EMOJIS for c in message.components for b in c.children):
                    if await claim_character(client, message.channel, message, is_kakera=False):
                        client.claim_right_available=False; client.interrupt_rolling=True; client.snipe_happened=True; process_further=False
                        # If a character is claimed, also check for and click any kakera buttons.
                        if any(hasattr(b.emoji,'name') and b.emoji.name in KAKERA_EMOJIS for comp in message.components for b in comp.children):
                            await asyncio.sleep(0.2); await claim_character(client, message.channel, message, is_kakera=True)
        
        # --- Logic for sniping other users' rolls (when not actively rolling) ---
        if process_further and not client.is_actively_rolling:
            # Series Snipe
            if client.series_snipe_mode and client.series_wishlist and message.id not in client.series_sniped_messages and is_character_snipe_allowed():
                desc = embed.description or "";
                first_line = desc.splitlines()[0].lower()
                if any(kw in first_line for kw in client.series_wishlist):
                    if message.components and any(hasattr(b.emoji, 'name') and b.emoji.name in CLAIM_EMOJIS for c in message.components for b in c.children):
                        client.series_sniped_messages.add(message.id); s_name = embed.author.name
                        log_function(f"[{client.muda_name}] Ext.Series Snipe: {s_name} (Delay {client.series_snipe_delay}s)", preset_name, "CLAIM")
                        await asyncio.sleep(client.series_snipe_delay)
                        if is_character_snipe_allowed() and await claim_character(client, message.channel, message): client.series_snipe_happened=True; process_further=False
            
            # Wishlist Character Snipe
            if process_further and client.snipe_mode and client.wishlist and message.id not in client.sniped_messages and is_character_snipe_allowed():
                char_name_l = embed.author.name.lower()
                if any(w == char_name_l for w in client.wishlist):
                    if message.components and any(hasattr(b.emoji, 'name') and b.emoji.name in CLAIM_EMOJIS for c in message.components for b in c.children):
                        client.sniped_messages.add(message.id)
                        log_function(f"[{client.muda_name}] Ext.Char Snipe: {embed.author.name} (Delay {client.snipe_delay}s)", preset_name, "CLAIM")
                        await asyncio.sleep(client.snipe_delay)
                        if is_character_snipe_allowed() and await claim_character(client, message.channel, message): client.snipe_happened=True; process_further=False

            # Kakera Value Snipe
            if process_further and client.kakera_snipe_mode_active and message.id not in client.kakera_value_sniped_messages and is_character_snipe_allowed():
                desc = embed.description or ""; k_val=0
                match_k_ext = re.search(r"\**(\d{1,3}(?:,\d{3})*|\d+)\**<:kakera:", desc)
                if match_k_ext:
                    try: k_val = int(match_k_ext.group(1).replace(",",""))
                    except ValueError: pass
                if k_val >= client.kakera_snipe_threshold:
                    if message.components and any(hasattr(b.emoji, 'name') and b.emoji.name in CLAIM_EMOJIS for c in message.components for b in c.children):
                        client.kakera_value_sniped_messages.add(message.id)
                        log_function(f"[{client.muda_name}] Ext.Kakera Val. Snipe: {embed.author.name} ({k_val}) (Delay {client.snipe_delay}s)", preset_name, "CLAIM")
                        await asyncio.sleep(client.snipe_delay)
                        if is_character_snipe_allowed() and await claim_character(client, message.channel, message):
                            client.snipe_happened = True; process_further = False
            
            # Kakera Reaction Snipe on Character Embeds (if no other snipe was triggered)
            if process_further and client.kakera_reaction_snipe_mode_active and message.id not in client.kakera_reaction_sniped_messages:
                if message.components and any(hasattr(b.emoji, 'name') and b.emoji.name in KAKERA_EMOJIS for c in message.components for b in c.children):
                    client.kakera_reaction_sniped_messages.add(message.id)
                    char_name = embed.author.name if embed.author and embed.author.name else "Unknown Character"
                    log_function(f"[{client.muda_name}] Ext.KakeraReact Snipe on Char: {char_name} (Delay {client.kakera_reaction_snipe_delay_value}s)", client.preset_name, "KAKERA")
                    await asyncio.sleep(client.kakera_reaction_snipe_delay_value)
                    await claim_character(client, message.channel, message, is_kakera=True)
        
        # --- During own rolls, automatically click kakera if conditions are met. ---
        if client.rolling_enabled and client.enable_reactive_self_snipe and client.is_actively_rolling and process_further:
            desc = embed.description or ""; k_val=0
            match_k = re.search(r"\**(\d{1,3}(?:,\d{3})*|\d+)\**<:kakera:", desc)
            if match_k:
                try: k_val = int(match_k.group(1).replace(",",""))
                except ValueError: pass
            kakera_button_present = any(hasattr(b.emoji,'name') and b.emoji.name in KAKERA_EMOJIS for comp in message.components for b in comp.children)
            should_click_kakera = kakera_button_present and \
                                    (not client.kakera_snipe_mode_active or k_val >= client.kakera_snipe_threshold or client.kakera_snipe_threshold == 0)
            if should_click_kakera:
                if await claim_character(client, message.channel, message, is_kakera=True): pass
        
        if process_further and client.rolling_enabled: await client.process_commands(message)

    @client.event
    async def on_message_edit(before, after):
        """Monitors edits on watched messages to confirm snipe outcomes and update cooldown state."""
        try:
            if after.author.id != TARGET_BOT_ID or after.channel.id != client.target_channel_id:
                return
            if not after.embeds:
                return
            if after.id not in client.snipe_watch:
                return

            embed = after.embeds[0]
            footer_text = (embed.footer.text or "") if embed.footer else ""
            ft_lower = footer_text.lower()
            if ("belongs to" not in ft_lower) and ("pertence a" not in ft_lower):
                # Not an ownership update yet; keep watching
                return

            # Determine if the owner is us
            owner_is_us = False
            own_names = set()
            try:
                if client.user and getattr(client.user, 'name', None):
                    own_names.add(client.user.name.lower())
            except Exception:
                pass
            try:
                dn = getattr(client.user, 'display_name', None)
                if dn:
                    own_names.add(dn.lower())
            except Exception:
                pass
            try:
                gn = getattr(client.user, 'global_name', None)
                if gn:
                    own_names.add(gn.lower())
            except Exception:
                pass
            if any(n in ft_lower for n in own_names):
                owner_is_us = True

            watch = client.snipe_watch.pop(after.id, None)
            char_name = watch.get('char_name') if watch else 'Unknown'

            if owner_is_us:
                log_function(f"[{client.muda_name}] Snipe success: {char_name}", preset_name, "CLAIM")
                try:
                    # Reflect that our claim was just used
                    client.claim_right_available = False
                    # Update next claim reset timestamp by adding 3 hours, per spec
                    if client.next_claim_reset_at_utc:
                        client.next_claim_reset_at_utc = client.next_claim_reset_at_utc + datetime.timedelta(hours=3)
                    else:
                        client.next_claim_reset_at_utc = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)

                    # Our claim is on cooldown until the next reset; temporarily disable sniping
                    client.claim_cooldown_until_utc = client.next_claim_reset_at_utc
                    client.snipe_globally_disabled_until = client.claim_cooldown_until_utc
                    try:
                        ts_str = client.next_claim_reset_at_utc.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
                    except Exception:
                        ts_str = str(client.next_claim_reset_at_utc)
                    log_function(f"[{client.muda_name}] Claim cooldown. Next reset {ts_str}", preset_name, "RESET")
                except Exception as e:
                    log_function(f"[{client.muda_name}] Error updating cooldown after snipe: {e}", preset_name, "ERROR")
            else:
                # Stolen/failed snipe
                log_function(f"[{client.muda_name}] Snipe lost: {char_name}", preset_name, "INFO")
        except Exception as e:
            log_function(f"[{client.muda_name}] on_message_edit error: {e}", preset_name, "ERROR")

    try:
        client.run(token)
    except discord.errors.LoginFailure:
        log_function(f"[{BOT_NAME}] Login failed for preset '{preset_name}'. Please check the token.", preset_name, "ERROR")
    except Exception as e:
        log_function(f"[{BOT_NAME}] An unexpected error occurred in preset '{preset_name}': {e}", preset_name, "ERROR")

def bot_lifecycle_wrapper(preset_name, preset_data):
    """A wrapper to run a bot instance and automatically restart it on exit."""
    # Load all optional settings with defaults
    key_mode=preset_data.get("key_mode",False); start_delay=preset_data.get("start_delay",0)
    snipe_mode=preset_data.get("snipe_mode",False); snipe_delay=preset_data.get("snipe_delay",2)
    snipe_ignore_min_kakera_reset=preset_data.get("snipe_ignore_min_kakera_reset",False)
    wishlist=preset_data.get("wishlist",[]); series_snipe_mode=preset_data.get("series_snipe_mode",False)
    series_snipe_delay=preset_data.get("series_snipe_delay",3); series_wishlist=preset_data.get("series_wishlist",[])
    roll_speed=preset_data.get("roll_speed",0.4)
    kakera_snipe_mode_preset=preset_data.get("kakera_snipe_mode",False)
    kakera_snipe_threshold_preset=preset_data.get("kakera_snipe_threshold",0)
    enable_reactive_self_snipe_preset = preset_data.get("reactive_snipe_on_own_rolls", True)
    rolling_enabled_preset = preset_data.get("rolling", True)
    kakera_reaction_snipe_mode_p = preset_data.get("kakera_reaction_snipe_mode", False)
    kakera_reaction_snipe_delay_p = preset_data.get("kakera_reaction_snipe_delay", 0.75)
    
    # Load humanization settings
    humanization_enabled_p = preset_data.get("humanization_enabled", False)
    humanization_window_p = preset_data.get("humanization_window_minutes", 40)
    humanization_inactivity_p = preset_data.get("humanization_inactivity_seconds", 5)
    
    # NEW: Load DK Power Management setting
    dk_power_management_p = preset_data.get("dk_power_management", False)
    # NEW: Load Skip Initial Commands setting
    skip_initial_commands_p = preset_data.get("skip_initial_commands", False)
    # NEW: Slash roll dispatch toggle
    use_slash_rolls_p = preset_data.get("use_slash_rolls", False)

    restart_delay = 60 # Seconds to wait before restarting a bot instance
    while True:
        try:
            run_bot(
                preset_data["token"], preset_data["prefix"], preset_data["channel_id"],
                preset_data["roll_command"], preset_data["min_kakera"], preset_data["delay_seconds"],
                preset_data["mudae_prefix"], print_log, preset_name, key_mode, start_delay,
                snipe_mode, snipe_delay, snipe_ignore_min_kakera_reset, wishlist,
                series_snipe_mode, series_snipe_delay, series_wishlist, roll_speed,
                kakera_snipe_mode_preset, kakera_snipe_threshold_preset,
                enable_reactive_self_snipe_preset, rolling_enabled_preset,
                kakera_reaction_snipe_mode_p, kakera_reaction_snipe_delay_p,
                humanization_enabled_p, humanization_window_p, humanization_inactivity_p,
                dk_power_management_p, skip_initial_commands_p, use_slash_rolls_p
            )
            print_log(f"Bot instance for '{preset_name}' has stopped normally. Restarting in {restart_delay} seconds...", preset_name, "RESET")
        except Exception as e:
            print_log(f"Bot instance for '{preset_name}' crashed with an unhandled exception: {e}. Restarting in {restart_delay} seconds...", preset_name, "ERROR")
        
        time.sleep(restart_delay)


def start_preset_thread(preset_name, preset_data):
     """Validates a preset and starts its lifecycle manager in a new thread."""
     if not validate_preset(preset_name, preset_data):
         print(f"\033[91mSkipping preset '{preset_name}' due to configuration error.\033[0m"); return None
     print(f"\033[92mSpawning manager thread for preset: {preset_name}\033[0m")
     thread = threading.Thread(target=bot_lifecycle_wrapper, args=(preset_name, preset_data), daemon=True)
     thread.start()
     return thread

def show_banner():
    """Displays the application banner."""
    banner = r"""
  __  __ _    _ _____          _____  ______ __  __  ____ _______ ______
 |  \/  | |  | |  __ \   /\   |  __ \|  ____|  \/  |/ __ \__   __|  ____|
 | \  / | |  | | |  | | /  \  | |__) | |__  | \  / | |  | | | |  | |__
 | |\/| | |  | | |  | |/ /\ \ |  _  /|  __| | |\/| | |  | | | |  |  __|
 | |  | | |__| | |__| / ____ \| | \ \| |____| |  | | |__| | | |  | |____
 |_|  |_|\____/|_____/_/    \_\_|  \_\______|_|  |_|\____/  |_|  |______|
"""
    print("\033[1;36m" + banner + "\033[0m"); print("\033[1;33mWelcome to MudaRemote - Your Remote Mudae Assistant\033[0m\n")

def validate_preset(preset_name, preset_data):
    """Validates that a preset contains all necessary keys and correct data types."""
    req_k = ["token","prefix","channel_id","roll_command","min_kakera","delay_seconds","mudae_prefix"]
    miss_k = [k for k in req_k if k not in preset_data]
    if miss_k: print(f"\033[91mErr '{preset_name}': Missing: {','.join(miss_k)}\033[0m"); return False
    if not isinstance(preset_data["token"],str) or not preset_data["token"]: print(f"\033[91mErr '{preset_name}': 'token' must be a non-empty string.\033[0m"); return False
    if not isinstance(preset_data["channel_id"],int): print(f"\033[91mErr '{preset_name}': 'channel_id' must be an integer.\033[0m"); return False
    if not isinstance(preset_data["min_kakera"],int) or preset_data["min_kakera"]<0: print(f"\033[91mErr '{preset_name}': 'min_kakera' must be a non-negative integer.\033[0m"); return False
    if not isinstance(preset_data["delay_seconds"],(int,float)) or preset_data["delay_seconds"]<0: print(f"\033[91mErr '{preset_name}': 'delay_seconds' must be a non-negative number.\033[0m"); return False
    # Validate optional keys
    if "rolling" in preset_data and not isinstance(preset_data["rolling"], bool):
        print(f"\033[91mErr '{preset_name}': 'rolling' field, if present, must be a boolean (true or false).\033[0m")
        return False
    if "key_mode" in preset_data and not isinstance(preset_data["key_mode"],bool): print(f"\033[91mWarn '{preset_name}': 'key_mode' should be a boolean.\033[0m")
    if "start_delay" in preset_data and (not isinstance(preset_data["start_delay"],(int,float)) or preset_data["start_delay"]<0): print(f"\033[91mWarn '{preset_name}': 'start_delay' should be a non-negative number.\033[0m")
    if "snipe_mode" in preset_data and not isinstance(preset_data["snipe_mode"],bool): print(f"\033[91mWarn '{preset_name}': 'snipe_mode' should be a boolean.\033[0m")
    if "snipe_delay" in preset_data and (not isinstance(preset_data["snipe_delay"], (int,float)) or preset_data["snipe_delay"] < 0): print(f"\033[91mWarn '{preset_name}': 'snipe_delay' should be a non-negative number.\033[0m")
    if "wishlist" in preset_data and not isinstance(preset_data["wishlist"],list): print(f"\033[91mWarn '{preset_name}': 'wishlist' should be a list of strings.\033[0m")
    if "kakera_snipe_mode" in preset_data and not isinstance(preset_data["kakera_snipe_mode"],bool): print(f"\033[91mWarn '{preset_name}': 'kakera_snipe_mode' should be a boolean.\033[0m")
    if "kakera_snipe_threshold" in preset_data and (not isinstance(preset_data["kakera_snipe_threshold"],int) or preset_data["kakera_snipe_threshold"]<0): print(f"\033[91mWarn '{preset_name}': 'kakera_snipe_threshold' should be a non-negative integer.\033[0m")
    if "reactive_snipe_on_own_rolls" in preset_data and not isinstance(preset_data["reactive_snipe_on_own_rolls"], bool):
        print(f"\033[91mWarn in preset '{preset_name}': 'reactive_snipe_on_own_rolls' should be a boolean.\033[0m")
    if "kakera_reaction_snipe_mode" in preset_data and not isinstance(preset_data["kakera_reaction_snipe_mode"], bool):
        print(f"\033[91mWarn in preset '{preset_name}': 'kakera_reaction_snipe_mode' should be a boolean.\033[0m")
    if "kakera_reaction_snipe_delay" in preset_data and (not isinstance(preset_data["kakera_reaction_snipe_delay"], (int, float)) or preset_data["kakera_reaction_snipe_delay"] < 0):
        print(f"\033[91mWarn in preset '{preset_name}': 'kakera_reaction_snipe_delay' should be a non-negative number.\033[0m")
    if "humanization_enabled" in preset_data and not isinstance(preset_data["humanization_enabled"], bool):
        print(f"\033[91mWarn in preset '{preset_name}': 'humanization_enabled' should be a boolean.\033[0m")
    if "humanization_window_minutes" in preset_data and (not isinstance(preset_data["humanization_window_minutes"], int) or preset_data["humanization_window_minutes"] < 0):
        print(f"\033[91mWarn in preset '{preset_name}': 'humanization_window_minutes' should be a non-negative integer.\033[0m")
    if "humanization_inactivity_seconds" in preset_data and (not isinstance(preset_data["humanization_inactivity_seconds"], (int, float)) or preset_data["humanization_inactivity_seconds"] < 0):
        print(f"\033[91mWarn in preset '{preset_name}': 'humanization_inactivity_seconds' should be a non-negative number.\033[0m")
    if "use_slash_rolls" in preset_data and not isinstance(preset_data["use_slash_rolls"], bool):
        print(f"\033[91mWarn in preset '{preset_name}': 'use_slash_rolls' should be a boolean.\033[0m")
    # NEW: Validate DK Power Management key
    if "dk_power_management" in preset_data and not isinstance(preset_data["dk_power_management"], bool):
        print(f"\033[91mWarn in preset '{preset_name}': 'dk_power_management' should be a boolean.\033[0m")
    # NEW: Validate Skip Initial Commands key
    if "skip_initial_commands" in preset_data and not isinstance(preset_data["skip_initial_commands"], bool):
        print(f"\033[91mWarn in preset '{preset_name}': 'skip_initial_commands' should be a boolean.\033[0m")
    return True

def main_menu():
    """Displays the main interactive menu for selecting and running bots."""
    show_banner(); active_threads = []
    while True:
        active_threads = [t for t in active_threads if t.is_alive()]
        questions = [inquirer.List('option',message=f"Select an option ({len(active_threads)} bots running):",choices=['Select and Run Preset','Select and Run Multiple Presets','Exit'])]
        try:
            answers = inquirer.prompt(questions)
            if not answers: print("\nExiting..."); break # Handle Ctrl+C on menu
            option = answers['option']
            if option == 'Select and Run Preset':
                preset_list = list(presets.keys())
                if not preset_list: print("\033[91mNo presets found in presets.json.\033[0m"); continue
                preset_answers = inquirer.prompt([inquirer.List('preset',message="Select a preset to run:",choices=preset_list)])
                if preset_answers:
                    thread = start_preset_thread(preset_answers['preset'], presets[preset_answers['preset']])
                    if thread: active_threads.append(thread)
            elif option == 'Select and Run Multiple Presets':
                preset_list = list(presets.keys())
                if not preset_list: print("\033[91mNo presets found in presets.json.\033[0m"); continue
                multi_preset_answers = inquirer.prompt([inquirer.Checkbox('presets',message="Select presets to run (use Spacebar to select, Enter to confirm):",choices=preset_list)])
                if multi_preset_answers:
                    for preset_name in multi_preset_answers['presets']:
                        thread = start_preset_thread(preset_name, presets[preset_name])
                        if thread: active_threads.append(thread)
            elif option == 'Exit': print("\033[1;32mExiting MudaRemote...\033[0m"); break
        except KeyboardInterrupt: print("\nCtrl+C detected. Exiting..."); break
        except Exception as e: print(f"\033[91mAn error occurred in the main menu: {e}\033[0m")

if __name__ == "__main__":
    try:
        # Initialize log file
        with open("logs.txt", "a", encoding='utf-8') as f: f.write(f"\n--- MudaRemote Log Start: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    except Exception as e: print(f"\033[91mCould not initialize log file: {e}\033[0m")
    main_menu()
