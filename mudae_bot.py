import sys
import asyncio
import discord
from discord.ext import commands
import re
import json
import threading
import datetime
from datetime import timezone
import inquirer
import logging
import time
import random
import os
import shutil
import requests
import subprocess
from discord.utils import time_snowflake

try:
    from discord.http import Route
except ImportError:
    Route = None

# Bot Identification
BOT_NAME = "MudaRemote"
CURRENT_VERSION = "3.4.0"

# --- UPDATE CONFIGURATION ---
# Replace this URL with your GitHub RAW URL for version.json and the script itself
UPDATE_URL = "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/refs/heads/main/" 

def check_for_updates():
    if not UPDATE_URL:
        return
    
    print(f"[{BOT_NAME}] Checking for updates... (Current: v{CURRENT_VERSION})")
    try:
        # Check version.json
        # Format: {"version": "2.6.0", "download_url": "..."}
        response = requests.get(f"{UPDATE_URL}version.json", timeout=10)
        if response.status_code == 200:
            data = response.json()
            latest_version = data.get("version")
            download_url = data.get("download_url")
            
            if latest_version and latest_version > CURRENT_VERSION:
                print(f"[{BOT_NAME}] New version found: v{latest_version}")
                print(f"[{BOT_NAME}] Downloading update...")
                
                # Download new script
                update_res = requests.get(download_url, timeout=30)
                if update_res.status_code == 200:
                    current_script = os.path.abspath(__file__)
                    backup_script = current_script + ".bak"
                    
                    # Create backup
                    shutil.copy2(current_script, backup_script)
                    
                    # Replace current script
                    with open(current_script, "wb") as f:
                        f.write(update_res.content)
                    
                    print(f"[{BOT_NAME}] Update applied. Starting new version in a fresh window...")
                    # Restart process
                    if os.name == 'nt':
                        # On Windows, launch in a new console window
                        subprocess.Popen([sys.executable] + sys.argv, creationflags=subprocess.CREATE_NEW_CONSOLE)
                    else:
                        os.execv(sys.executable, [sys.executable] + sys.argv)
                    sys.exit()
                else:
                    print(f"[{BOT_NAME}] Failed to download update file.")
            else:
                print(f"[{BOT_NAME}] You are up to date.")
    except Exception as e:
        print(f"[{BOT_NAME}] Update check failed: {e}")

def cleanup_after_update():
    """Removes the backup file created during the update process."""
    current_script = os.path.abspath(__file__)
    backup_file = current_script + ".bak"
    if os.path.exists(backup_file):
        try:
            os.remove(backup_file)
            print(f"[{BOT_NAME}] Previous version backup (.bak) cleaned up.")
        except Exception:
            pass

# Load config
presets = {}
try:
    with open("presets.json", "r", encoding="utf-8") as f:
        presets = json.load(f)
except FileNotFoundError:
    print("presets.json not found. Create it first.")
    sys.exit(1)
except json.JSONDecodeError:
    print("presets.json is malformed.")
    sys.exit(1)

# Mudae's User ID
TARGET_BOT_ID = 432610292342587392

# Console Colors
COLORS = {
    "INFO": "\033[94m",    # Blue
    "CLAIM": "\033[92m",   # Green
    "KAKERA": "\033[93m",  # Yellow
    "ERROR": "\033[91m",   # Red
    "CHECK": "\033[95m",   # Magenta
    "RESET": "\033[36m",   # Cyan
    "ENDC": "\033[0m"      # End
}

# Heart buttons
CLAIM_EMOJIS = ['💖', '💗', '💘', '❤️', '💓', '💕', '♥️']

# Standard Kakera
KAKERA_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC']

# Chaos Kakera (for characters with 10+ keys)
CHAOS_KAKERA_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC']

# Sphere Emojis (Do not consume power)
SPHERE_EMOJIS = ['SpU', 'SpD', 'SpL', 'SpW', 'SpR', 'SpO', 'SpY', 'SpG', 'SpT', 'SpB', 'SpP']


def color_log(message, preset_name, log_type="INFO"):
    color_code = COLORS.get(log_type.upper(), COLORS["INFO"])
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}][{preset_name}] {message}"
    print(f"{color_code}{log_message}{COLORS['ENDC']}")
    return log_message

def write_log_to_file(log_message):
    try:
        with open("logs.txt", "a", encoding='utf-8') as log_file:
            log_file.write(log_message + "\n")
    except Exception as e:
        print(f"Log file error: {e}")

def print_log(message, preset_name, log_type="INFO"):
    log_message_formatted = color_log(message, preset_name, log_type)
    write_log_to_file(log_message_formatted)

def is_character_embed(embed):
    # Reliable check: Characters have an author name, an image, and NO thumbnail
    if not embed or not embed.author or not embed.author.name:
        return False
    
    has_image = embed.image and embed.image.url
    has_thumbnail = embed.thumbnail and embed.thumbnail.url

    return has_image and not has_thumbnail

def is_free_event(embed):
    """
    Detects special Mudae event characters (like Christmas Art Contest) 
    that do not consume claim rights.
    """
    if not embed or not embed.description:
        return False
    desc = embed.description.lower()
    # "on me, it's free!" is the standard indicator for these event cards.
    free_keywords = ["it's free!", "é de graça!", "¡es gratis!", "christmas art contest", "new year's contest"]
    return any(k in desc for k in free_keywords)

def has_claim_option(message, embed, claim_emojis):
    if not message.components:
        # If no buttons are present, check if the character is already owned via the footer.
        # If it belongs to someone, we ignore it as it's not a claimable roll.
        if get_character_owner(embed):
            return False
        return True
    for comp in message.components:
        for btn in comp.children:
            if hasattr(btn.emoji, 'name') and btn.emoji and btn.emoji.name in claim_emojis:
                return True
    return False

def count_chaos_keys(embed):
    # Extracts key count from description. Format: <:key:ID> (**N**)
    if not embed or not embed.description:
        return 0
    
    desc = embed.description
    key_pattern = r'<:(?:chaos)?key:\d+>\s*\(\*\*([\d,.]+)\*\*\)'
    matches = re.findall(key_pattern, desc, re.IGNORECASE)
    
    chaos_count = 0
    for match in matches:
        try:
            val = int(re.sub(r"[^\d]", "", match))
            if val >= 10:
                chaos_count += 1
        except ValueError:
            continue
    
    return chaos_count

def get_character_owner(embed):
    if not embed or not embed.footer or not embed.footer.text:
        return None
    
    footer_text = embed.footer.text
    # Patterns for: English, Portuguese, Spanish, French
    belongs_pattern = r'(?:[Bb]elongs to|[Pp]ertence a|[Pp]ertenece a|[Aa]ppartient [àa])\s+(.+?)$'
    match = re.search(belongs_pattern, footer_text)
    
    if match:
        return match.group(1).strip().rstrip().lower()
    
    return None

def is_wished_by_self(message, client_user_id: int) -> bool:
    """
    Checks if the Mudae message indicates this character is wished by the bot's user.
    Mudae format: "Wished by @user1, @user2" in message.content with users in mentions.
    
    This provides authoritative wishlist detection directly from Mudae, complementing
    the local wishlist. Characters detected this way are treated as wishlist characters
    for claiming purposes.
    
    Args:
        message: The Discord message object from Mudae
        client_user_id: The bot user's Discord ID
        
    Returns:
        True if the bot user is mentioned in a "Wished by" context
    """
    if not message or not message.content:
        return False
    
    content_lower = message.content.lower()
    if "wished by" not in content_lower:
        return False
    
    # Check if the bot user is among the mentioned users
    return client_user_id in [m.id for m in message.mentions]

def run_bot(token, prefix, target_channel_id, roll_command, min_kakera, delay_seconds, mudae_prefix,
            log_function, preset_name, key_mode, start_delay, snipe_mode, snipe_delay,
            snipe_ignore_min_kakera_reset, wishlist,
            series_snipe_mode, series_snipe_delay, series_wishlist, roll_speed,
            kakera_snipe_mode_preset, kakera_snipe_threshold_preset,
            enable_reactive_self_snipe_preset, rolling_enabled,
            kakera_reaction_snipe_mode_preset, kakera_reaction_snipe_delay_preset,
            kakera_reaction_snipe_targets,
            humanization_enabled, humanization_window_minutes, humanization_inactivity_seconds,
            dk_power_management, skip_initial_commands, use_slash_rolls, only_chaos,
            reactive_snipe_delay, time_rolls_to_claim_reset_preset,
            rt_ignore_min_kakera_for_wishlist_preset,
            claim_emojis_preset, kakera_emojis_preset, chaos_emojis_preset,
            rt_only_self_rolls_preset, reactive_kakera_delay_range_preset,
            claim_interval_preset, roll_interval_preset):

    client = commands.Bot(command_prefix=prefix, chunk_guilds_at_startup=False, self_bot=True)

    # Clean up console logging
    discord_logger = logging.getLogger('discord')
    discord_logger.propagate = False
    handlers = [h for h in discord_logger.handlers if isinstance(h, logging.StreamHandler)]
    for h in handlers: discord_logger.removeHandler(h)

    # Config init
    client.preset_name = preset_name
    client.min_kakera = min_kakera
    client.snipe_mode = snipe_mode
    client.snipe_delay = snipe_delay
    client.snipe_ignore_min_kakera_reset = snipe_ignore_min_kakera_reset
    client.wishlist = set([w.lower() for w in wishlist])
    client.series_snipe_mode = series_snipe_mode
    client.series_snipe_delay = series_snipe_delay
    client.series_wishlist = set([sw.lower() for sw in series_wishlist])
    client.muda_name = BOT_NAME
    client.claim_right_available = False
    client.target_channel_id = target_channel_id
    client.roll_speed = roll_speed
    client.mudae_prefix = mudae_prefix
    client.key_mode = key_mode
    client.delay_seconds = delay_seconds
    client.sniped_messages = set()
    client.snipe_happened = False
    client.series_sniped_messages = set()
    client.series_snipe_happened = False
    client.kakera_value_sniped_messages = set()
    client.is_actively_rolling = False
    client.interrupt_rolling = False
    client.current_min_kakera_for_roll_claim = client.min_kakera
    client.kakera_snipe_mode_active = kakera_snipe_mode_preset
    client.kakera_snipe_threshold = kakera_snipe_threshold_preset
    client.enable_reactive_self_snipe = enable_reactive_self_snipe_preset
    client.reactive_snipe_delay = reactive_snipe_delay
    client.rolling_enabled = rolling_enabled
    client.rt_available = False # $rt (Reset Timer) status
    client.kakera_reaction_snipe_mode_active = kakera_reaction_snipe_mode_preset
    client.kakera_reaction_snipe_delay_value = kakera_reaction_snipe_delay_preset
    client.kakera_reaction_snipe_targets = set([t.lower() for t in kakera_reaction_snipe_targets])
    client.kakera_reaction_sniped_messages = set()
    client.kakera_react_available = True
    client.kakera_react_cooldown_until_utc = None

    # Humanization config
    client.humanization_enabled = humanization_enabled
    client.humanization_window_minutes = humanization_window_minutes
    client.humanization_inactivity_seconds = humanization_inactivity_seconds
    
    # Power and key settings
    client.dk_power_management = dk_power_management
    client.skip_initial_commands = skip_initial_commands
    client.dk_stock_count = 0 
    client.only_chaos = only_chaos

    # State tracking
    client.next_claim_reset_at_utc = None
    client.claim_cooldown_until_utc = None
    client.snipe_watch = {} 
    client.snipe_watch_expiry_seconds = 180 
    client.snipe_globally_disabled_until = None

    # Slash command internal state
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
    client.key_limit_hit = False
    client.time_rolls_to_claim_reset = time_rolls_to_claim_reset_preset
    client.rt_ignore_min_kakera_for_wishlist = rt_ignore_min_kakera_for_wishlist_preset
    
    # RT Self-Roll Only Mode: Prevents RT usage on external snipes
    client.rt_only_self_rolls = rt_only_self_rolls_preset
    
    # Reactive Kakera Delay: Humanized delay before clicking kakera on own rolls
    # Default: [0.3, 1.0] seconds (300ms to 1000ms)
    if reactive_kakera_delay_range_preset and isinstance(reactive_kakera_delay_range_preset, (list, tuple)) and len(reactive_kakera_delay_range_preset) == 2:
        client.reactive_kakera_delay_range = (float(reactive_kakera_delay_range_preset[0]), float(reactive_kakera_delay_range_preset[1]))
    else:
        client.reactive_kakera_delay_range = (0.3, 1.0)

    # Manual Intervals (in minutes) for minimized $tu usage
    client.claim_interval = claim_interval_preset if claim_interval_preset else 180
    client.roll_interval = roll_interval_preset if roll_interval_preset else 60
    
    # Custom Emojis
    # Use explicit None check to respect intentionally empty lists.
    # - None: user never configured -> use defaults
    # - []: user explicitly set blank -> use empty (no buttons clicked)
    # - [...]: user set custom -> use their values
    client.claim_emojis = claim_emojis_preset if claim_emojis_preset is not None else ['💖', '💗', '💘', '❤️', '💓', '💕', '♥️']
    client.kakera_emojis = kakera_emojis_preset if kakera_emojis_preset is not None else ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC']
    client.chaos_emojis = chaos_emojis_preset if chaos_emojis_preset is not None else ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL', 'kakeraP', 'kakeraD', 'kakeraC']
    client.sphere_emojis = SPHERE_EMOJIS


    async def health_monitor_task():
        # Reconnect if gateway drops
        unhealthy_streak = 0
        max_streak = 3
        while not client.is_closed():
            await asyncio.sleep(60)
            if client.latency == float('inf'):
                unhealthy_streak += 1
                log_function(f"[{client.muda_name}] Connection lost ({unhealthy_streak}/{max_streak}).", preset_name, "ERROR")
            else:
                if unhealthy_streak > 0:
                    log_function(f"[{client.muda_name}] Reconnected. Ping: {client.latency * 1000:.0f}ms.", preset_name, "INFO")
                unhealthy_streak = 0
            if unhealthy_streak >= max_streak:
                log_function(f"[{client.muda_name}] Connection dead. Restarting.", preset_name, "ERROR")
                try:
                    await client.close()
                except Exception:
                    pass
                return

    def is_character_snipe_allowed(is_external_snipe: bool = False) -> bool:
        # If rt_only_self_rolls is enabled, don't count RT as available for external snipes
        rt_usable = client.rt_available and not (is_external_snipe and client.rt_only_self_rolls)
        return client.claim_right_available or rt_usable or client.key_mode

    def is_key_mode_kakera_only() -> bool:
        """
        Returns True when key_mode is active but neither claim nor RT is available.
        In this state, the bot should ONLY click kakera buttons and NOT claim characters.
        This prevents wasting keys on characters we cannot actually claim.
        """
        return client.key_mode and not client.claim_right_available and not client.rt_available

    def parse_hours_minutes(match_obj):
        if not match_obj: return 0, 0
        groups = match_obj.groups(default="")
        h_str = groups[0] if len(groups) >= 1 else ""
        m_str = groups[1] if len(groups) >= 2 else ""
        
        def get_val(s):
            d = re.sub(r"\D", "", s or "")
            return int(d) if d else 0
        return get_val(h_str), get_val(m_str)

    def is_kakera_reaction_allowed() -> bool:
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
            route = Route("GET", "/applications/{application_id}/commands", application_id=TARGET_BOT_ID)
            data = await http.request(route)
        except Exception:
            data = []

        for cmd in data:
            name = str(cmd.get("name", "")).lower()
            if name:
                commands_map[name] = cmd

        client.mudae_slash_cache[guild_id] = commands_map
        return commands_map

    async def _trigger_mudae_slash(channel, command_text):
        """
        Trigger a Mudae slash command. Returns True on success, False on failure.
        All failure points are logged with detailed reasons for debugging.
        """
        cmd_display = f"/{command_text.strip().lstrip('/')}" if command_text else "/?"
        
        if not client.use_slash_rolls:
            log_function(f"[{client.muda_name}] Slash {cmd_display}: SKIP - Slash mode disabled", preset_name, "INFO")
            return False
        
        if not channel:
            log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - No channel provided", preset_name, "ERROR")
            return False
        
        if not getattr(channel, "guild", None):
            log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - Channel has no guild (DM or invalid)", preset_name, "ERROR")
            return False

        stripped = command_text.strip()
        if not stripped:
            log_function(f"[{client.muda_name}] Slash: FAIL - Empty command text", preset_name, "ERROR")
            return False
        
        now_ts = time.time()
        if client.slash_rate_limited_until and now_ts < client.slash_rate_limited_until:
            remaining = client.slash_rate_limited_until - now_ts
            log_function(f"[{client.muda_name}] Slash {cmd_display}: SKIP - Rate limited ({remaining:.1f}s remaining)", preset_name, "WARN")
            return False
        
        if client.last_slash_attempt:
            elapsed = now_ts - client.last_slash_attempt
            if elapsed < client.slash_min_interval:
                await asyncio.sleep(client.slash_min_interval - elapsed)
        client.last_slash_attempt = time.time()
        
        # We don't support arguments in this slash impl yet
        if " " in stripped:
            key = f"mixed:{stripped.split(' ', 1)[0].lower()}"
            if key not in client.mudae_slash_missing:
                client.mudae_slash_missing.add(key)
                log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - Commands with arguments not supported", preset_name, "WARN")
            return False
            
        base_name = stripped.lstrip("/").lower()
        guild = channel.guild
        command_map = await _fetch_mudae_slash_commands(guild.id)
        
        if not command_map:
            log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - Could not fetch Mudae slash commands for guild {guild.id}. Check bot permissions or Mudae availability.", preset_name, "ERROR")
            return False

        command_data = command_map.get(base_name)
        if not command_data:
            key = f"missing:{base_name}"
            if key not in client.mudae_slash_missing:
                client.mudae_slash_missing.add(key)
                available_cmds = list(command_map.keys())[:10]  # Show first 10 available
                log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - Command '{base_name}' not found. Available: {available_cmds}...", preset_name, "ERROR")
            return False

        _refresh_session_id()
        session_id = None
        ws = getattr(client, "ws", None)
        if ws and getattr(ws, "session_id", None):
            session_id = ws.session_id
        elif client.mudae_session_id:
            session_id = client.mudae_session_id

        if not session_id:
            log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - No Discord session ID. WebSocket may be disconnected.", preset_name, "ERROR")
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
            status = getattr(e, "status", "?")
            code = getattr(e, "code", "?")
            text = getattr(e, "text", str(e))
            retry_after = getattr(e, "retry_after", None)
            
            if retry_after:
                client.slash_rate_limited_until = time.time() + min(retry_after, client.slash_max_backoff)
                log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - Rate limited by Discord. Retry after {retry_after}s", preset_name, "WARN")
                await asyncio.sleep(retry_after)
            else:
                invalidate_cache = True
                log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - HTTP {status} (code: {code}): {text[:100]}", preset_name, "ERROR")
            client.slash_fail_streak += 1
        except Exception as e:
            client.slash_fail_streak += 1
            invalidate_cache = True
            log_function(f"[{client.muda_name}] Slash {cmd_display}: FAIL - Unexpected error: {type(e).__name__}: {str(e)[:100]}", preset_name, "ERROR")

        if invalidate_cache:
            client.mudae_slash_cache.pop(guild.id, None)
        if client.slash_fail_streak >= client.slash_fail_threshold:
            # Log the failure streak but do NOT switch to text mode.
            # Stealth is paramount: we never expose the bot with text commands.
            log_function(f"[{client.muda_name}] Slash: WARNING - {client.slash_fail_streak} consecutive failures. Slash mode remains active (no text fallback).", preset_name, "WARN")
        return False

    async def send_roll_command(channel, command_name):
        cmd = (command_name or "").strip()
        if not cmd:
            return

        normalized = cmd.lstrip('/')

        if client.use_slash_rolls:
            # STEALTH MODE: When slash is enabled, NEVER fall back to text.
            # If slash fails, we stay silent rather than exposing the bot.
            slash_target = normalized
            slash_override_map = {"w": "wx", "h": "hx", "m": "mx"}
            slash_target = slash_override_map.get(slash_target.lower(), slash_target)
            slash_name = slash_target if slash_target.startswith("/") else f"/{slash_target}"
            await _trigger_mudae_slash(channel, slash_name)
            # Always return here - no text fallback
            return

        # Text mode: Only used when slash is explicitly disabled
        await channel.send(f"{client.mudae_prefix}{normalized}")

    async def send_tu_command(channel):
        """
        Send $tu command via slash (if enabled) or text.
        If slash is enabled, retries up to 3 times on failure.
        If all slash attempts fail, waits 30 minutes before returning.
        Never falls back to text when slash is enabled.
        """
        if client.use_slash_rolls:
            max_attempts = 3
            retry_delay = 5.0  # seconds between retries
            
            for attempt in range(1, max_attempts + 1):
                # _trigger_mudae_slash logs detailed failure reasons
                sent = await _trigger_mudae_slash(channel, "tu")
                if sent:
                    return True
                
                if attempt < max_attempts:
                    log_function(f"[{client.muda_name}] Retrying /tu in {retry_delay}s... (attempt {attempt}/{max_attempts})", preset_name, "WARN")
                    await asyncio.sleep(retry_delay)
            
            # All attempts failed - wait 30 minutes
            log_function(f"[{client.muda_name}] /tu failed after {max_attempts} attempts. Entering 30-minute cooldown before next retry.", preset_name, "ERROR")
            await asyncio.sleep(30 * 60)
            return False
        
        # Slash not enabled - use text command
        await channel.send(f"{client.mudae_prefix}tu")
        return True

    @client.event
    async def on_ready():
        log_function(f"[{client.muda_name}] Ready: {client.user}", preset_name, "INFO")
        client.loop.create_task(health_monitor_task())
        _refresh_session_id()
        
        # Retrieve target channel and validate
        try:
            target_channel_id_int = int(target_channel_id)
        except (ValueError, TypeError):
            log_function(f"[{client.muda_name}] Err: Invalid channel ID format: {target_channel_id}", preset_name, "ERROR"); await client.close(); return

        channel = client.get_channel(target_channel_id_int)
        if not channel:
            log_function(f"[{client.muda_name}] Channel {target_channel_id_int} not in cache, fetching...", preset_name, "INFO")
            try:
                channel = await client.fetch_channel(target_channel_id_int)
            except discord.NotFound:
                log_function(f"[{client.muda_name}] Channel {target_channel_id_int} not found via API", preset_name, "ERROR"); await client.close(); return
            except discord.Forbidden:
                log_function(f"[{client.muda_name}] No access to channel {target_channel_id_int}", preset_name, "ERROR"); await client.close(); return
            except Exception as e:
                log_function(f"[{client.muda_name}] Err fetching channel {target_channel_id_int}: {e}", preset_name, "ERROR"); await client.close(); return
        
        if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            log_function(f"[{client.muda_name}] Err: Channel {target_channel_id_int} is not a messageable channel", preset_name, "ERROR"); await client.close(); return
        
        if client.rolling_enabled:
             # Permissions check
            can_send = channel.permissions_for(channel.guild.me).send_messages
            if not can_send: log_function(f"[{client.muda_name}] No Send Permissions", preset_name, "ERROR"); await client.close(); return
        
        log_function(f"[{client.muda_name}] Starting in {start_delay}s...", preset_name, "INFO")
        await asyncio.sleep(start_delay)

        if client.rolling_enabled:
            try:
                if client.skip_initial_commands:
                    await check_status(client, channel, client.mudae_prefix)
                else:
                    await channel.send(f"{client.mudae_prefix}limroul 1 1 1 1"); await asyncio.sleep(1.0)
                    if not client.dk_power_management:
                        await channel.send(f"{client.mudae_prefix}dk"); await asyncio.sleep(1.0)
                    else:
                        pass # Managed later in $tu
                    await channel.send(f"{client.mudae_prefix}daily"); await asyncio.sleep(1.0)
                    await check_status(client, channel, client.mudae_prefix)
            except Exception as e:
                log_function(f"[{client.muda_name}] Setup error: {e}", preset_name, "ERROR"); await client.close()
        else:
            # Snipe only logic: Start a background loop to periodically check $tu
            client.loop.create_task(snipe_only_status_loop(client, channel))

    async def handle_dk_power_management(client, channel, tu_content):
        # Manage $dk usage. Check if power is low and we have stock.
        content_lower = tu_content.lower()
        
        # Check stock
        dk_stock_match = re.search(r"\*\*(\d+)\*\*\s*\$dk\s*(?:available|dispon[ií]ve(?:l|is)|no estoque|disponible|en stock|disponibles?)", content_lower)
        if dk_stock_match:
            client.dk_stock_count = int(dk_stock_match.group(1))
            log_function(f"[{client.muda_name}] DK Stock: {client.dk_stock_count}", preset_name, "INFO")
        elif "¡$dk está listo!" in content_lower or "$dk está listo" in content_lower or "$dk est prêt" in content_lower:
            # Fallback for Spanish and French where it might say ready without a number
            client.dk_stock_count = 1
            log_function(f"[{client.muda_name}] DK Stock: 1 (Derived)", preset_name, "INFO")
        else:
            client.dk_stock_count = 0
        
        if client.dk_stock_count == 0:
            return
        
        try:
            power_match = re.search(r"(?:power|poder):\s*\*{0,2}(\d+)%\*{0,2}", content_lower)
            
            # Handling PT-BR translation variance: "reação" vs "botão", Spanish/French: "botón"/"bouton"
            consumption_match = re.search(r"(?:each kakera reaction consumes|cada (?:reação|botão|botón) de kakera consume|chaque bouton kakera consomme)\s*(\d+)%", content_lower)
            
            if not power_match or not consumption_match:
                log_function(f"[{client.muda_name}] DK: Parse failed (power/consumption).", preset_name, "WARN")
                return
            
            current_power = int(power_match.group(1))
            consumption_cost = int(consumption_match.group(1))
            
            # Use item if power is too low for a reaction
            if current_power < consumption_cost:
                log_function(f"[{client.muda_name}] DK: Activating. ({current_power}% < {consumption_cost}%)", preset_name, "KAKERA")
                await channel.send(f"{client.mudae_prefix}dk")
                await asyncio.sleep(1.5) 
                client.dk_stock_count = max(0, client.dk_stock_count - 1)
            else:
                pass

        except Exception as e:
            log_function(f"[{client.muda_name}] DK logic error: {e}", preset_name, "ERROR")


    async def snipe_only_status_loop(client, channel):
        """
        Ghost Mode Loop:
        1. Initial Handshake: Check $tu ONCE to sync minute/status.
        2. Silent Phase: Sleep until next calculated reset. Never send commands automatically.
        """
        log_function(f"[{client.muda_name}] Snipe-only: Performing initial handshake...", client.preset_name, "INFO")
        
        # --- INITIAL HANDSHAKE ---
        handshake_success = False
        while not client.is_closed():
            try:
                # Proceed to rolls=False, we just want data
                await check_status(client, channel, client.mudae_prefix, proceed_to_rolls=False)
                if client.next_claim_reset_at_utc:
                    handshake_success = True
                    break
                log_function(f"[{client.muda_name}] Snipe-only: Handshake incomplete. Retrying in 30s...", client.preset_name, "WARN")
                await asyncio.sleep(30)
            except Exception as e:
                log_function(f"[{client.muda_name}] Handshake error: {e}. Retrying in 30s...", client.preset_name, "ERROR")
                await asyncio.sleep(30)
        
        if not handshake_success: return # Client closed

        log_function(f"[{client.muda_name}] Snipe-only: Handshake complete. Entering Ghost Mode.", client.preset_name, "INFO")

        # --- GHOST LOOP ---
        while not client.is_closed():
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            
            if not client.claim_right_available:
                # STATE: COOLDOWN -> Sleep until reset
                if client.next_claim_reset_at_utc and client.next_claim_reset_at_utc > now_utc:
                    wait_seconds = (client.next_claim_reset_at_utc - now_utc).total_seconds()
                    # Add buffer to ensure we wake up AFTER the minute flips
                    real_wait = max(5, wait_seconds + 2.0)
                    
                    log_function(f"[{client.muda_name}] Snipe-only: Silent. Sleeping {real_wait/60:.1f}m until reset.", client.preset_name, "RESET")
                    try:
                        await asyncio.sleep(real_wait)
                    except asyncio.CancelledError:
                        break # Allow clean ext
                    
                    # WAKE UP: Internal State Update
                    # Double check time just in case
                    if datetime.datetime.now(datetime.timezone.utc) >= client.next_claim_reset_at_utc:
                        client.claim_right_available = True
                        log_function(f"[{client.muda_name}] Snipe-only: Reset time reached. Claim restored locally.", client.preset_name, "CLAIM")
                        
                        # Chain the minute anchor
                        reset_delta = datetime.timedelta(minutes=client.claim_interval)
                        while client.next_claim_reset_at_utc <= datetime.datetime.now(datetime.timezone.utc):
                             client.next_claim_reset_at_utc += reset_delta
                        
                        log_function(f"[{client.muda_name}] Snipe-only: Next reset anchored to {client.next_claim_reset_at_utc.strftime('%H:%M')}", client.preset_name, "INFO")
                else:
                    # Fallback (Should be rare)
                    await asyncio.sleep(10)
            else:
                # STATE: READY -> Passive Monitor
                # We are waiting for on_message to trigger 'claim_character' -> 'verify_snipe_outcome'
                # Passively sleep in short bursts to allow for responsive shutdown or state checks
                await asyncio.sleep(10)


    async def check_status(client, channel, mudae_prefix, proceed_to_rolls: bool = True):
        log_function(f"[{client.muda_name}] Checking $tu...", client.preset_name, "CHECK")
        tu_message_content = None


        # Retrieve $tu message (using slash command if enabled)
        # IMPORTANT: Validate that the response is addressed to THIS user, not another player
        def is_tu_response_for_self(message_content: str) -> bool:
            """
            Validates that a Mudae $tu response is addressed to the bot's own user.
            Mudae formats responses as: **Username**, your rolls: ... or **Username**, you __can__ claim...
            Returns True if the username in the response matches client.user.
            """
            if not message_content:
                return False
            
            # Extract the bolded username at the start of the message
            # Pattern matches: **Username** at the beginning (with optional leading whitespace)
            username_match = re.match(r"^\s*\*\*([^*]+)\*\*", message_content)
            if not username_match:
                # Fallback: some Mudae responses may use different formatting
                # If we can't extract a username, be conservative and reject
                return False
            
            response_username = username_match.group(1).strip().lower()
            
            # Compare against both the bot's username and display name
            bot_username = (client.user.name or "").strip().lower()
            bot_display_name = (client.user.display_name or "").strip().lower()
            
            # Match if either the username or display name matches
            return response_username == bot_username or response_username == bot_display_name
        
        for _ in range(5):
            await send_tu_command(channel); await asyncio.sleep(2.5)
            async for msg in channel.history(limit=10):
                if msg.author.id == TARGET_BOT_ID and msg.content:
                    c = msg.content.lower()
                    if ("rolls" in c and "claim" in c) or ("rolls" in c and "casar" in c) or ("rolls" in c and "reclamar" in c) or ("rolls" in c and "marier" in c):
                        # Validate this response is for OUR user, not someone else's $tu
                        if is_tu_response_for_self(msg.content):
                            tu_message_content = msg.content
                            break
                        else:
                            # This is another player's $tu response, skip it
                            # Extract the detected username for debug logging
                            other_user_match = re.match(r"^\s*\*\*([^*]+)\*\*", msg.content)
                            other_user = other_user_match.group(1) if other_user_match else "Unknown"
                            log_function(f"[{client.muda_name}] Skipped $tu response for '{other_user}' (not our user)", preset_name, "INFO")
                            continue
            if tu_message_content: break
            await asyncio.sleep(5)
        
        if not tu_message_content:
            log_function(f"[{client.muda_name}] Failed to get $tu response.", preset_name, "ERROR")
            if client.rolling_enabled and proceed_to_rolls:
                await asyncio.sleep(1800) # Long sleep on failure
            return

        if client.dk_power_management and client.rolling_enabled:
            await handle_dk_power_management(client, channel, tu_message_content)

        c_lower = tu_message_content.lower()
        now_utc = datetime.datetime.now(datetime.timezone.utc)

        # $rt Status
        rt_ready = any(x in c_lower for x in ["$rt is available", "$rt está pronto", "$rt esta pronto", "$rt está disponível", "$rt está disponible", "$rt est disponible", "$rt est prêt"])
        rt_reset_minutes = None

        # Supports "$rt is in...", "$rt... time left:", etc.
        match_rt_reset = re.search(r"\$rt.*?(?:\:|in|em|en|dans|left|restante|restam|falta|tiempo|temps|tempo|restantes|restant)\s*\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min", c_lower)
        if match_rt_reset:
            h_rt, m_rt = parse_hours_minutes(match_rt_reset)
            rt_reset_minutes = h_rt * 60 + m_rt
            client.rt_available = False
            log_function(f"[{client.muda_name}] RT: Cooldown ({h_rt}h {m_rt}m)", preset_name, "INFO")
        elif rt_ready:
            client.rt_available = True
            log_function(f"[{client.muda_name}] RT: Ready", preset_name, "INFO")
        else:
            client.rt_available = False
            log_function(f"[{client.muda_name}] RT: Cooldown", preset_name, "INFO")

        # Claim Status
        can_claim = False
        wait_time = 0

        # Try to parse claim reset time first (available in both states)
        claim_reset_minutes = None
        match_claim_reset = re.search(r"(?:next claim reset|próximo reset de casamento|siguiente reclamo|prochain reset|tiempo restante).*?(?:in|em|en|dans|left|restante|restant|tempo|tiempo|falta|restam)\s*\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min", c_lower, re.IGNORECASE)
        if match_claim_reset:
            h_c, m_c = parse_hours_minutes(match_claim_reset)
            claim_reset_minutes = h_c * 60 + m_c
        
        claim_ready_pt = "você __pode__ se casar agora même" in c_lower or "você __pode__ se casar agora mesmo" in c_lower
        claim_ready_en = "you __can__ claim" in c_lower
        claim_ready_es = "puedes__ reclamar" in c_lower or ("puedes reclamar" in c_lower and "no puedes reclamar" not in c_lower)
        claim_ready_fr = "vous __pouvez__ vous marier" in c_lower
        
        if claim_ready_en or claim_ready_pt or claim_ready_es or claim_ready_fr:
            client.claim_right_available = True
            log_function(f"[{client.muda_name}] Claim: Ready", preset_name, "INFO")
            client.current_min_kakera_for_roll_claim = client.min_kakera
            
            if client.snipe_ignore_min_kakera_reset: 
                 if claim_reset_minutes is not None and claim_reset_minutes <= 60:
                      client.current_min_kakera_for_roll_claim = 0
                      log_function(f"[{client.muda_name}] Reset soon ({claim_reset_minutes}m). Ignoring Min Kakera.", preset_name, "WARN")
            
            if claim_reset_minutes is not None:
                # Align to the next minute boundary (:00) for precision
                client.next_claim_reset_at_utc = (now_utc + datetime.timedelta(minutes=claim_reset_minutes)).replace(second=0, microsecond=0)
            else:
                client.next_claim_reset_at_utc = now_utc.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
            
            can_claim = True
        else:
            client.claim_right_available = False
            client.current_min_kakera_for_roll_claim = client.min_kakera  # Reset to normal rules
            # Parse wait time
            match_wait = re.search(r"(?:can't claim|falta um tempo|no puedes|pouvez vous remarier).*?\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min", c_lower)
            if match_wait:
                h, m = parse_hours_minutes(match_wait)
                wait_time = h * 60 + m
                log_function(f"[{client.muda_name}] Claim: Cooldown ({h}h {m}m)", preset_name, "INFO")
                
                # Align to next minute for precision
                target_time = (now_utc + datetime.timedelta(minutes=wait_time)).replace(second=0, microsecond=0)
                client.claim_cooldown_until_utc = target_time
                client.next_claim_reset_at_utc = target_time
                
                if claim_reset_minutes is None:
                    claim_reset_minutes = wait_time
            
        # Roll Reset Status (New in check_status for better sleep awareness)
        roll_reset_minutes = None
        match_roll_reset = re.search(r"(?:reset in|reinicialização é em|siguiente reinicio.*?en|prochain rolls reset dans)\s+\*{0,2}(\d+h)?\*{0,2}\s*\*{0,2}(\d+)\*{0,2}\s*min", c_lower)
        if match_roll_reset:
            h_r, m_r = parse_hours_minutes(match_roll_reset)
            roll_reset_minutes = h_r * 60 + m_r

        # Kakera Status
        if "you __can__ react" in c_lower or "pode reagir" in c_lower or "pegar kakera" in c_lower or "puedes__ reaccionar" in c_lower or "puedes reaccionar" in c_lower or "pouvez__ réagir" in c_lower or "pouvez réagir" in c_lower:
            client.kakera_react_available = True
            client.kakera_react_cooldown_until_utc = None
        elif "can't react" in c_lower or "não pode" in c_lower or "no puedes" in c_lower:
            client.kakera_react_available = False
            # Try to parse time
            match_k = re.search(r"(?:react|pegar|reaccionar).*?\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min", c_lower)
            if match_k:
                h, m = parse_hours_minutes(match_k)
                client.kakera_react_cooldown_until_utc = now_utc + datetime.timedelta(minutes=(h*60+m))

        if client.key_limit_hit:
            log_function(f"[{client.muda_name}] Recovering from key limit. Skipping rolls.", preset_name, "INFO")
            client.key_limit_hit = False
            return

        # Timing logic: Only roll if claim reset is near (<= 60 mins)
        is_timing_window = False
        if client.time_rolls_to_claim_reset and claim_reset_minutes is not None and claim_reset_minutes <= 60:
            is_timing_window = True

        immediate_roll = (client.rolling_enabled and proceed_to_rolls and 
                         (can_claim or client.key_mode or client.rt_available or is_timing_window))
        
        if immediate_roll:
            await check_rolls_left_tu(client, channel, mudae_prefix, log_function, preset_name,
                                      tu_message_content, 
                                      (client.current_min_kakera_for_roll_claim == 0),
                                      (client.key_mode and not client.rt_available and not client.claim_right_available))
        elif client.rolling_enabled and proceed_to_rolls:
            # Decide best sleep target using a prioritized candidate list to avoid "Dead Zones"
            sleep_choices = []
            
            # 1. Personal claim cooldown
            if wait_time > 0:
                sleep_choices.append((float(wait_time), "claim cooldown"))
            
            # 2. Global claim reset (for timing window threshold entry at 60 mins)
            if client.time_rolls_to_claim_reset and claim_reset_minutes is not None and claim_reset_minutes > 60:
                # Wake up right as we enter the window where "Timing" becomes possible
                sleep_choices.append((float(claim_reset_minutes - 60), "timing threshold arrival"))
            
            # 3. $rt reset
            if rt_reset_minutes is not None and rt_reset_minutes > 0:
                sleep_choices.append((float(rt_reset_minutes), "$rt reset"))
                
            # 4. Roll reset
            if roll_reset_minutes is not None and roll_reset_minutes > 0:
                sleep_choices.append((float(roll_reset_minutes), "rolls replenishment"))

            if sleep_choices:
                # Sort by wait time and pick the smallest logical event
                sleep_choices.sort(key=lambda x: x[0])
                best_sleep_wait, sleep_reason = sleep_choices[0]
                # Ensure we don't sleep for too little or too much (clamped between 0.5 and the choice)
                best_sleep_wait = max(0.5, best_sleep_wait)
                await humanized_wait_and_proceed(client, channel, best_sleep_wait, sleep_reason)
            else:
                # Default safety sleep if no timers could be parsed
                await humanized_wait_and_proceed(client, channel, 30, "default status cycle")
            
            await check_status(client, channel, mudae_prefix)
            return
        else:
            return

    async def check_rolls_left_tu(client, channel, mudae_prefix, log_function, preset_name,
                                  tu_message_content_for_rolls, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll):
        content_lower = tu_message_content_for_rolls.lower()
        rolls_left = 0
        us_rolls_left = 0
        reset_time_r = 0
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        
        def parse_int_from_fragment(fragment: str) -> int:
            digits = re.sub(r"[^\d]", "", fragment or "")
            return int(digits) if digits else 0

        # Regex for rolls (singular/plural support for all languages)
        main_match_en = re.search(r"you have\s+\*{0,2}([\d,.]+)\*{0,2}\s+rolls?(.*?)(?:left\b)", content_lower, re.DOTALL)
        main_match_pt = re.search(r"você tem\s+\*{0,2}([\d,.]+)\*{0,2}\s+rolls?(.*?)(?:restantes?\b)", content_lower, re.DOTALL)
        main_match_es = re.search(r"tienes\s+\*{0,2}([\d,.]+)\*{0,2}\s+rolls?(.*?)(?:restantes?\b)", content_lower, re.DOTALL)
        main_match_fr = re.search(r"vous avez\s+\*{0,2}([\d,.]+)\*{0,2}\s+rolls?(.*?)(?:restants?\b)", content_lower, re.DOTALL)

        main_match = main_match_en or main_match_pt or main_match_es or main_match_fr
        
        if main_match:
            rolls_left = parse_int_from_fragment(main_match.group(1))
            middle_text = main_match.group(2)
            
            # Separate $us and $mk parsing.
            # $us are actual rolls we can use. $mk are passive and should be ignored for calculation.
            for bonus_match in re.finditer(r"\(\+\*{0,2}([\d,.]+)\*{0,2}\s+\$(us|mk)\)", middle_text):
                amount = parse_int_from_fragment(bonus_match.group(1))
                bonus_type = bonus_match.group(2).lower()
                
                if bonus_type == "us":
                    us_rolls_left += amount
                elif bonus_type == "mk":
                    pass 

            # Parse reset time
            match_reset = re.search(r"(?:reset in|reinicialização é em|siguiente reinicio.*?en|prochain rolls reset dans)\s+\*{0,2}(\d+h)?\*{0,2}\s*\*{0,2}(\d+)\*{0,2}\s*min", content_lower[main_match.end():])
            if match_reset:
                h_r = parse_int_from_fragment(match_reset.group(1))
                m_r = parse_int_from_fragment(match_reset.group(2))
                reset_time_r = h_r * 60 + m_r
                # Align to the next minute boundary (:00)
                client.roll_reset_at_utc = (now_utc + datetime.timedelta(minutes=reset_time_r)).replace(second=0, microsecond=0)
            else:
                reset_time_r = 60 # Default safe fallback
                client.roll_reset_at_utc = (now_utc + datetime.timedelta(minutes=reset_time_r)).replace(second=0, microsecond=0)
            
            # Only add $us to total. Ignoring $mk fixes the 0+1 loop bug.
            total_rolls = rolls_left + us_rolls_left

            if total_rolls == 0:
                # Reset time for rolls is known, but we should also check if we need to wake up for claim/timing
                # Parse claim reset again from local context to be safe
                sleep_candidates = [(float(reset_time_r if reset_time_r > 0 else 60), "rolls reset")]
                
                # Check claim reset and timing window awareness
                match_c = re.search(r"(?:next claim reset|próximo reset de casamento|siguiente reclamo|prochain reset|tiempo restante).*?(?:in|em|en|dans|left|restante|restant|tempo|tiempo|falta|restam)\s*\*{0,2}(\d+h)?\s*(\d+)\*{0,2}\s*min", content_lower, re.IGNORECASE)
                if match_c:
                    h_c, m_c = parse_hours_minutes(match_c) # Note: parse_hours_minutes is defined in check_status; we'll need to handle this or use local regex
                    c_min = h_c * 60 + m_c
                    if c_min > 0:
                        sleep_candidates.append((float(c_min), "claim reset"))
                        if client.time_rolls_to_claim_reset and c_min > 60:
                            sleep_candidates.append((float(c_min - 60), "timing window arrival"))
                
                sleep_candidates.sort(key=lambda x: x[0])
                wait_m, reason = sleep_candidates[0]
                
                await humanized_wait_and_proceed(client, channel, wait_m, reason)
                await check_status(client, channel, mudae_prefix); return
            else:
                log_detail = f" (+{us_rolls_left} $us)" if us_rolls_left > 0 else ""
                log_function(f"[{client.muda_name}] Rolls: {total_rolls}{log_detail}. Reset: {reset_time_r}m", preset_name, "INFO")
                await start_roll_commands(client, channel, total_rolls, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll)
                return
        else:
            log_function(f"[{client.muda_name}] Could not parse roll count.", preset_name, "ERROR")
            await asyncio.sleep(30); await check_status(client, channel, mudae_prefix); return

    async def start_roll_commands(client, channel, rolls_left, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll):
        log_text = f"Rolling {rolls_left} times"
        log_text += " (Reactive)" if client.enable_reactive_self_snipe else ""
        log_function(f"[{client.muda_name}] {log_text}", client.preset_name, "INFO")
        
        # Timing Logic: If not ready to claim and timing is enabled, wait until just before claim reset
        # If reset is soon (<= 60 mins), we time it even if RT/KeyMode is available (per user request)
        reset_soon = False
        if client.next_claim_reset_at_utc:
            diff = (client.next_claim_reset_at_utc - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
            if 0 < diff <= 60 * 60:
                reset_soon = True

        is_timing_mode_active = False
        if client.time_rolls_to_claim_reset and not client.claim_right_available and (reset_soon or (not client.rt_available and not client.key_mode)):
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if client.next_claim_reset_at_utc and client.next_claim_reset_at_utc > now_utc:
                actual_speed = max(client.roll_speed, 0.2 if client.use_slash_rolls else 0)
                total_duration = rolls_left * actual_speed
                
                # Aim for the last roll to finish ~1s AFTER reset.
                # This way claim happens after reset → we use normal claim (not RT) with fresh claim right.
                # Formula: start_time = reset + offset - total_duration
                # offset = 1 second after reset (minimizes new interval roll waste)
                target_start_time = client.next_claim_reset_at_utc + datetime.timedelta(seconds=1) - datetime.timedelta(seconds=total_duration)
                
                wait_seconds = (target_start_time - now_utc).total_seconds()
                
                # Safety: Don't wait past roll reset (ensure we finish before roll reset)
                if client.roll_reset_at_utc:
                    max_wait = (client.roll_reset_at_utc - now_utc).total_seconds() - total_duration - 5
                    wait_seconds = min(wait_seconds, max_wait)

                if wait_seconds > 2:
                    log_function(f"[{client.muda_name}] Timing rolls to finish after reset. Waiting {wait_seconds/60:.1f}m.", preset_name, "RESET")
                    await asyncio.sleep(wait_seconds)
                    is_timing_mode_active = True

        start_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=0.5)
        client.is_actively_rolling = True
        client.interrupt_rolling = False
        
        for i in range(rolls_left):
            if client.interrupt_rolling:
                break
            try:
                await send_roll_command(channel, roll_command)
                await asyncio.sleep(max(client.roll_speed, 0.2 if client.use_slash_rolls else 0))
            except Exception:
                await asyncio.sleep(1)
                
        client.is_actively_rolling = False
        await asyncio.sleep(5) # Let messages populate
        
        # If timing mode was active, claim reset has now happened. Update state for normal claim flow.
        if is_timing_mode_active:
            client.claim_right_available = True
            log_function(f"[{client.muda_name}] Reset passed. Claim is now available.", preset_name, "CLAIM")
        
        mudae_messages_to_process = []
        try:
            async for msg in channel.history(limit=(rolls_left*2 + 10), after=start_time, oldest_first=False):
                if msg.author.id == TARGET_BOT_ID and msg.embeds:
                    mudae_messages_to_process.append(msg)
            
            mudae_messages_to_process.reverse()
            if mudae_messages_to_process:
                 # In timing mode, use normal claim flow (not key_mode_only) since claim is now available
                 await handle_mudae_messages(client, channel, mudae_messages_to_process, ignore_limit_for_post_roll, False if is_timing_mode_active else key_mode_only_kakera_for_post_roll)
        except Exception as e:
            log_function(f"[{client.muda_name}] Post-roll processing error: {e}", preset_name, "ERROR")
        
        
        
        await asyncio.sleep(2)
        await asyncio.sleep(1)
        # Always check status (send $tu) after rolling sequence, as requested
        await check_status(client, channel, client.mudae_prefix)


    async def verify_snipe_outcome(client, channel, char_name, is_snipe_action=True):
        """
        Outcome Verifier:
        Checks the last few messages to see who actually got the character.
        If the bot got it -> Update local state (consume claim), set next reset.
        If someone else got it -> Keep claim available.
        """
        await asyncio.sleep(2.0) # Wait for message to appear
        
        found_marriage = False
        winner_name = None
        
        log_label = "Snipe Verification" if is_snipe_action else "Claim Verification"
        
        # Scan recent history
        async for msg in channel.history(limit=5):
            if not msg.content: continue
            # Format: 💖 **Username** and **Charname** are now married! 💖
            if "and" in msg.content and "are now married" in msg.content:
                 # Check if this marriage message relates to the target character
                 # Simple substring check (char_name might be partial, but usually sufficient)
                 if char_name.lower() in msg.content.lower():
                     found_marriage = True
                     # Extract username: **User**
                     match = re.search(r"\*\*(.+?)\*\*", msg.content)
                     if match:
                         winner_name = match.group(1).lower()
                     break
        
        if found_marriage and winner_name:
            bot_name = client.user.name.lower()
            bot_nick = client.user.display_name.lower()
            
            if winner_name == bot_name or winner_name == bot_nick:
                log_function(f"[{client.muda_name}] {log_label}: SUCCESS! We got {char_name}.", client.preset_name, "CLAIM")
                # Update State LOCALLY (No $tu)
                client.claim_right_available = False
                
                # REFINED MINUTE-LOCK LOGIC:
                # We calculate the next reset relative to the PAST reset point to maintain the exact minute.
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                interval_delta = datetime.timedelta(minutes=client.claim_interval)
                
                # If we have a known reset time, we increment it by the interval
                if client.next_claim_reset_at_utc:
                    # If current time is past the target reset, it means the 'next' reset is actually one interval further
                    base_reset = client.next_claim_reset_at_utc
                    while base_reset <= now_utc:
                        base_reset += interval_delta
                    
                    client.next_claim_reset_at_utc = base_reset.replace(second=0, microsecond=0)
                    log_function(f"[{client.muda_name}] Claim used. Next reset synced to {client.next_claim_reset_at_utc.strftime('%H:%M')} (Minute-Locked)", client.preset_name, "INFO")
                else:
                    # Fallback if bot just started and hasn't done $tu yet
                    client.next_claim_reset_at_utc = (now_utc + interval_delta).replace(second=0, microsecond=0)
                    log_function(f"[{client.muda_name}] Next claim reset set to {client.next_claim_reset_at_utc.strftime('%H:%M')} (Local Est.)", client.preset_name, "INFO")
            else:
                log_function(f"[{client.muda_name}] {log_label}: FAILED. Taken by {winner_name}.", client.preset_name, "WARN")
                # Do NOT set claim_right_available = False. We still have it!
        else:
             log_function(f"[{client.muda_name}] {log_label}: Inconclusive. Assuming failure/no-message.", client.preset_name, "WARN")



    async def handle_mudae_messages(client, channel, mudae_messages, ignore_limit_param, key_mode_only_kakera_param):
        kakera_claims = []
        char_claims_post = []
        wl_claims_post = []
        min_kak_post = 0 if ignore_limit_param else client.min_kakera

        for msg in mudae_messages:
            if not msg.embeds: continue
            embed = msg.embeds[0]
            if not is_character_embed(embed): continue
            
            all_kakera_emojis = client.kakera_emojis + client.chaos_emojis + client.sphere_emojis
            is_kakera = msg.components and any(hasattr(b.emoji, 'name') and b.emoji.name in all_kakera_emojis for c in msg.components for b in c.children)
            
            if is_kakera:
                kakera_claims.append(msg)
            else:
                if is_free_event(embed) or has_claim_option(msg, embed, client.claim_emojis):
                    char_n = embed.author.name.lower()
                    desc = embed.description or ""
                    
                    # Detect "Free" event cards (Christmas, New Year, etc.)
                    # These should be claimed regardless of claim availability 
                    if is_free_event(embed):
                        print_log(f"Detected free event card: {char_n}", client.preset_name, "CLAIM")
                        await claim_character(client, channel, msg, is_free_claim=True)
                        continue

                    k_v = 0
                    match_k = re.search(r"\**([\d,.]+)\**<:kakera:", desc)
                    if match_k:
                        k_v = int(re.sub(r"[^\d]", "", match_k.group(1)))
                    
                    series = desc.splitlines()[0].lower() if desc else ""
                    
                    # Check if character is on wishlist OR Mudae indicates we wished for it
                    is_wl = (char_n in client.wishlist) or \
                            (client.series_snipe_mode and any(s in series for s in client.series_wishlist)) or \
                            is_wished_by_self(msg, client.user.id)
                    if is_wl:
                        wl_claims_post.append((msg, char_n, k_v))
                    elif k_v >= min_kak_post:
                        char_claims_post.append((msg, char_n, k_v))

        # Kakera first
        for msg_k in kakera_claims:
            await claim_character(client, channel, msg_k, is_kakera=True)
            await asyncio.sleep(0.3)
        
        # Claims
        claimed_post = False
        msg_claimed_id = -1
        
        # Key Mode Kakera-Only: If key_mode is ON but no claim/RT available, skip all character claims
        if key_mode_only_kakera_param or is_key_mode_kakera_only():
            log_function(f"[{client.muda_name}] Key mode active, no claim/RT. Skipping character claims (kakera only).", preset_name, "INFO")
        elif is_character_snipe_allowed(is_external_snipe=False):
            # Allow claiming if claim right is available OR if RT is available (for RT claim)
            if client.claim_right_available or client.rt_available:
                if wl_claims_post:
                    msg_c, n, v = wl_claims_post[0]
                    if await claim_character(client, channel, msg_c, is_kakera=False, kakera_value=v):
                        claimed_post = True
                        msg_claimed_id = msg_c.id
                elif char_claims_post:
                    char_claims_post.sort(key=lambda x: x[2], reverse=True)
                    msg_c, n, v = char_claims_post[0]
                    if await claim_character(client, channel, msg_c, is_kakera=False, kakera_value=v):
                        claimed_post = True
                        msg_claimed_id = msg_c.id
        
        # RT check: Only attempt RT claim if RT is actually available and we're not in kakera-only mode
        if claimed_post and client.rt_available and not is_key_mode_kakera_only():
            rt_targets = [i for i in wl_claims_post if i[0].id != msg_claimed_id] + [i for i in char_claims_post if i[0].id != msg_claimed_id]
            rt_targets.sort(key=lambda x: x[2], reverse=True)
            if rt_targets:
                msg_rt, n_rt, v_rt = rt_targets[0]
                is_wl_rt = n_rt in client.wishlist
                
                # Check if we should ignore min_kakera for wishlist or if value is enough
                bypass_min = is_wl_rt and client.rt_ignore_min_kakera_for_wishlist
                if bypass_min or v_rt >= client.min_kakera:
                    log_function(f"[{client.muda_name}] Attempting RT on {n_rt} ({v_rt})", preset_name, "CLAIM")
                    try:
                        await channel.send(f"{client.mudae_prefix}rt")
                        client.rt_available = False
                        await asyncio.sleep(0.7)
                        await claim_character(client, channel, msg_rt, is_rt_claim=True, kakera_value=v_rt)
                    except Exception:
                        pass


    async def claim_character(client, channel, msg, is_kakera=False, is_rt_claim=False, is_snipe=False, is_free_claim=False, kakera_value=None):
        if not msg or not msg.embeds: return False
        embed = msg.embeds[0]
        char_author = embed.author.name if embed.author else None
        char_name = char_author if char_author else "Unknown"
        
        # Kakera value logging logic
        kakera_str = ""
        if not is_kakera and not is_free_claim:
            val = kakera_value
            if val is None:
                desc = embed.description or ""
                match_k = re.search(r"\**([\d,.]+)\**<:kakera:", desc)
                if match_k:
                    val = re.sub(r"[^\d]", "", match_k.group(1))
            
            if val is not None:
                kakera_str = f" ({val} ka)"
        
        # Authorization check
        # For snipe operations, check with is_external_snipe flag
        if not is_kakera and not is_rt_claim and not is_free_claim and not is_character_snipe_allowed(is_external_snipe=is_snipe):
            return False

        # RT Handling: If we are claiming a character and have no claim right but RT is ready, use it now.
        # If rt_only_self_rolls is enabled and this is an external snipe, don't use RT.
        rt_blocked_for_snipe = is_snipe and client.rt_only_self_rolls
        if not is_kakera and not is_free_claim and not is_rt_claim:
            if not client.claim_right_available and client.rt_available and not rt_blocked_for_snipe:
                log_function(f"[{client.muda_name}] Using RT for {char_name}", client.preset_name, "CLAIM")
                try:
                    await channel.send(f"{client.mudae_prefix}rt")
                    client.rt_available = False
                    await asyncio.sleep(0.8) # Wait for Mudae to process RT
                except Exception as e:
                    log_function(f"[{client.muda_name}] RT Failed: {e}", client.preset_name, "ERROR")
                    return False

        # Humanized delay for free event claims (since competition is low/none)
        if is_free_claim:
            await asyncio.sleep(random.uniform(1.0, 2.5))

        # Kakera Claim Logic
        if is_kakera:
            chaos_count = count_chaos_keys(embed)
            if not is_snipe and client.only_chaos and chaos_count == 0:
                return False
            
            # If sniping, treat as normal character (ignore chaos logic)
            target_list = (client.chaos_emojis if (chaos_count > 0 and not is_snipe) else client.kakera_emojis) + client.sphere_emojis
            cooldown_active = not is_kakera_reaction_allowed()
            clicked = False
            
            # Check for KakeraP or Spheres (always safe)
            has_p_or_sphere = msg.components and any(hasattr(b.emoji, 'name') and (b.emoji.name == 'kakeraP' or b.emoji.name in client.sphere_emojis) for c in msg.components for b in c.children)
            
            if cooldown_active and not has_p_or_sphere:
                return False

            if msg.components:
                for comp in msg.components:
                    for btn in comp.children:
                        if hasattr(btn.emoji, 'name') and btn.emoji.name in target_list:
                            name = btn.emoji.name
                            if cooldown_active and name != 'kakeraP' and name not in client.sphere_emojis:
                                continue
                            try:
                                await btn.click()
                                log_function(f"[{client.muda_name}] Kakera clicked: {char_name}", client.preset_name, "KAKERA")
                                clicked = True
                                await asyncio.sleep(0.5)
                            except Exception:
                                pass
            return clicked

        # Character Claim Logic
        clicked_claim = False
        if msg.components:
            for comp in msg.components:
                if clicked_claim: break
                for btn in comp.children:
                    # If it's a free claim, click ANY button. Otherwise, check for standard hearts.
                    has_emoji = hasattr(btn.emoji, 'name') and btn.emoji.name is not None
                    is_heart = has_emoji and btn.emoji.name in client.claim_emojis
                    
                    if is_free_claim or is_heart:
                        try:
                            await btn.click()
                            log_type = "CLAIM" if not is_free_claim else "INFO"
                            log_function(f"[{client.muda_name}] Claiming {char_name}{kakera_str}", client.preset_name, log_type)
                            clicked_claim = True
                            
                            # Snipe Verification Logic (is_snipe tells us if it was external)
                            # If we clicked, we verify if we actually won
                            # For regular rolling (not snipes), is_snipe is False -> "Claim Verification"
                            await verify_snipe_outcome(client, channel, char_name, is_snipe_action=is_snipe)
                            return True
                        except Exception:
                            continue
        
        # Reaction fallback
        if not clicked_claim and has_claim_option(msg, embed, client.claim_emojis):
            try:
                await msg.add_reaction("💖")
                log_function(f"[{client.muda_name}] Claiming {char_name}{kakera_str} (Reaction)", client.preset_name, "CLAIM")
                # Reaction fallback
                await verify_snipe_outcome(client, channel, char_name, is_snipe_action=is_snipe)
                return True
            except Exception:
                return False

        return False

    async def humanized_wait_and_proceed(client, channel, base_reset_minutes, reason="reset"):
        # Calculate random wait time
        min_wait = max(0.0, base_reset_minutes * 60)
        window = max(0.0, client.humanization_window_minutes * 60)
        
        # If no explicit reset time, fallback to default delay
        if min_wait <= 0:
            min_wait = max(client.delay_seconds + 60, 240)
            
        wait_seconds = min_wait + (random.uniform(0, window) if client.humanization_enabled else 0)
        end_time = datetime.datetime.now() + datetime.timedelta(seconds=wait_seconds)
        
        log_prefix = "Humanized " if client.humanization_enabled else ""
        log_function(f"[{client.muda_name}] {log_prefix}Waiting {wait_seconds/60:.1f}m ({reason}).", preset_name, "RESET")
        await asyncio.sleep(wait_seconds)

        # Inactivity check (anti-detection)
        if client.humanization_enabled:
            while True:
                try:
                    last_msg = None
                    async for m in channel.history(limit=1): last_msg = m
                    
                    if not last_msg: break
                    
                    diff = (datetime.datetime.now(timezone.utc) - last_msg.created_at).total_seconds()
                    if diff >= client.humanization_inactivity_seconds:
                        break
                    else:
                        await asyncio.sleep(client.humanization_inactivity_seconds - diff + 0.5)
                except Exception:
                    break

    @client.event
    async def on_message(message):
        # Filter for relevant messages
        if message.author.id != TARGET_BOT_ID or message.channel.id != client.target_channel_id:
            if client.rolling_enabled: await client.process_commands(message)
            return
        if not message.embeds: return
        embed = message.embeds[0]

        # Handle Kakera Drops (non-character messages)
        if not is_character_embed(embed):
            # Logic for sniping loose kakera if enabled
            if client.kakera_reaction_snipe_mode_active and message.id not in client.kakera_reaction_sniped_messages:
                 # Verify it's actually a drop via buttons
                all_k = client.kakera_emojis + client.chaos_emojis
                has_btn = message.components and any(hasattr(b.emoji, 'name') and b.emoji.name in all_k for c in message.components for b in c.children)
                
                if has_btn:
                    # Check owner targets
                    if client.kakera_reaction_snipe_targets:
                        owner = get_character_owner(embed)
                        if not owner or owner not in client.kakera_reaction_snipe_targets:
                            return

                    client.kakera_reaction_sniped_messages.add(message.id)
                    await asyncio.sleep(client.kakera_reaction_snipe_delay_value)
                    # Snipe flag is True here
                    await claim_character(client, message.channel, message, is_kakera=True, is_snipe=True)
            return

        # Handle Character Rolls
        
        # Key Limit Check
        if client.rolling_enabled and client.is_actively_rolling:
            desc = embed.description or ""
            if "limit of 1,000 keys" in desc or "limite de 1.000 chaves" in desc or "límite de 1.000 llaves" in desc:
                client.interrupt_rolling = True
                client.key_limit_hit = True
                log_function(f"[{client.muda_name}] Key Limit Hit. Pausing.", preset_name, "ERROR")
                # Wait 1 hour + human jitter
                await asyncio.sleep(3600 + random.randint(0, 600))
                await check_status(client, message.channel, client.mudae_prefix)
                return

        process = True
        
        # Self-snipe (Reactive)
        if client.rolling_enabled and client.enable_reactive_self_snipe and client.is_actively_rolling:
            c_name = embed.author.name.lower()
            desc = embed.description or ""
            series = desc.splitlines()[0].lower() if desc else ""
            k_val = 0
            m_k = re.search(r"\**([\d,.]+)\**<:kakera:", desc)
            if m_k: k_val = int(re.sub(r"[^\d]", "", m_k.group(1)))
            
            # Check if character is on wishlist OR Mudae indicates we wished for it
            is_wl = c_name in client.wishlist or \
                    (client.series_snipe_mode and any(s in series for s in client.series_wishlist)) or \
                    is_wished_by_self(message, client.user.id)
            is_val = client.kakera_snipe_mode_active and k_val >= client.kakera_snipe_threshold
            
            if (is_wl or is_val) and has_claim_option(message, embed, client.claim_emojis):
                # Skip reactive claim if key_mode is active but no claim/RT available
                if is_key_mode_kakera_only():
                    pass  # Will fall through to kakera handling below
                else:
                    if client.reactive_snipe_delay > 0: await asyncio.sleep(client.reactive_snipe_delay)
                    if await claim_character(client, message.channel, message, kakera_value=k_val):
                        client.interrupt_rolling = True
                        process = False

        # Snipe other users
        if process and not client.is_actively_rolling:
            c_name = embed.author.name.lower()
            
            # External Kakera Snipe on Character Rolls
            if client.kakera_reaction_snipe_mode_active and message.id not in client.kakera_reaction_sniped_messages and process:
                 all_k = client.kakera_emojis + client.chaos_emojis
                 has_btn = message.components and any(hasattr(b.emoji, 'name') and b.emoji.name in all_k for c in message.components for b in c.children)
                 if has_btn:
                    # Check owner
                    target_ok = True
                    if client.kakera_reaction_snipe_targets:
                        owner = get_character_owner(embed)
                        if not owner or owner not in client.kakera_reaction_snipe_targets:
                            target_ok = False
                    
                    if target_ok:
                        client.kakera_reaction_sniped_messages.add(message.id)
                        await asyncio.sleep(client.kakera_reaction_snipe_delay_value)
                        await claim_character(client, message.channel, message, is_kakera=True, is_snipe=True)
                        process = False
            
            # Series Snipe
            if client.series_snipe_mode and client.series_wishlist:
                desc = embed.description or ""
                series = desc.splitlines()[0].lower() if desc else ""
                if any(s in series for s in client.series_wishlist) and has_claim_option(message, embed, client.claim_emojis):
                    if is_key_mode_kakera_only():
                        pass  # Key mode kakera-only: skip character claims
                    elif not is_character_snipe_allowed(is_external_snipe=True):
                        pass  # Can't snipe without claim right/RT (when rt_only_self_rolls is on)
                    else:
                        await asyncio.sleep(client.series_snipe_delay)
                        if await claim_character(client, message.channel, message, is_snipe=True):
                             client.series_snipe_happened = True; process = False

            # Wishlist Snipe (includes "Wished by" detection from Mudae)
            is_on_wishlist = c_name in client.wishlist or is_wished_by_self(message, client.user.id)
            if process and client.snipe_mode and is_on_wishlist and has_claim_option(message, embed, client.claim_emojis):
                if is_key_mode_kakera_only():
                    pass  # Key mode kakera-only: skip character claims
                elif not is_character_snipe_allowed(is_external_snipe=True):
                    pass  # Can't snipe without claim right/RT (when rt_only_self_rolls is on)
                else:
                    await asyncio.sleep(client.snipe_delay)
                    if await claim_character(client, message.channel, message, is_snipe=True):
                        client.snipe_happened = True; process = False
            
            # Value Snipe
            if process and client.kakera_snipe_mode_active:
                desc = embed.description or ""
                k_val = 0
                m_k = re.search(r"\**([\d,.]+)\**<:kakera:", desc)
                if m_k: k_val = int(re.sub(r"[^\d]", "", m_k.group(1)))
                
                if k_val >= client.kakera_snipe_threshold and has_claim_option(message, embed, client.claim_emojis):
                    if is_key_mode_kakera_only():
                        pass  # Key mode kakera-only: skip character claims
                    elif not is_character_snipe_allowed(is_external_snipe=True):
                        pass  # Can't snipe without claim right/RT (when rt_only_self_rolls is on)
                    else:
                        await asyncio.sleep(client.snipe_delay)
                        if await claim_character(client, message.channel, message, is_snipe=True, kakera_value=k_val):
                            client.snipe_happened = True; process = False

            # Free Event Card Snipe (Regardless of mode)
            if process and is_free_event(embed):
                print_log(f"Sniping free event card: {c_name}", client.preset_name, "CLAIM")
                if await claim_character(client, message.channel, message, is_free_claim=True):
                    process = False

        # Reactive Kakera on own rolls (with humanized delay)
        if client.rolling_enabled and client.enable_reactive_self_snipe and client.is_actively_rolling and process:
            # Check if kakera button exists and value is high enough
            all_k = client.kakera_emojis + client.chaos_emojis + client.sphere_emojis
            if any(hasattr(b.emoji, 'name') and b.emoji.name in all_k for c in message.components for b in c.children):
                 # Apply humanized delay before clicking kakera on own rolls
                 delay_min, delay_max = client.reactive_kakera_delay_range
                 if delay_max > 0:
                     await asyncio.sleep(random.uniform(delay_min, delay_max))
                 await claim_character(client, message.channel, message, is_kakera=True)


    # Logic to handle the Discord client execution
    try:
        # log_handler=None prevents logging conflicts within threads on Windows
        # reconnect=True ensures the bot attempts to stay online during minor outages
        client.run(token, reconnect=True)
    except Exception as e:
        # This specific error happens on Windows when the bot runs in a sub-thread.
        # It's a signal handling limitation and doesn't affect Mudae functionality.
        if "set_wakeup_fd" in str(e):
            pass 
        else:
            log_function(f"[{BOT_NAME}] Crash: {e}", preset_name, "ERROR")

def bot_lifecycle_wrapper(preset_name, preset_data):
    # Auto-restart wrapper
    while True:
        try:
            run_bot(
                preset_data["token"], preset_data["prefix"], preset_data["channel_id"],
                preset_data["roll_command"], preset_data["min_kakera"], preset_data["delay_seconds"],
                preset_data["mudae_prefix"], print_log, preset_name, 
                preset_data.get("key_mode", False), preset_data.get("start_delay", 0),
                preset_data.get("snipe_mode", False), preset_data.get("snipe_delay", 2),
                preset_data.get("snipe_ignore_min_kakera_reset", False), preset_data.get("wishlist", []),
                preset_data.get("series_snipe_mode", False), preset_data.get("series_snipe_delay", 3),
                preset_data.get("series_wishlist", []), preset_data.get("roll_speed", 0.4),
                preset_data.get("kakera_snipe_mode", False), preset_data.get("kakera_snipe_threshold", 0),
                preset_data.get("reactive_snipe_on_own_rolls", True), preset_data.get("rolling", True),
                preset_data.get("kakera_reaction_snipe_mode", False), preset_data.get("kakera_reaction_snipe_delay", 0.75),
                preset_data.get("kakera_reaction_snipe_targets", []),
                preset_data.get("humanization_enabled", False), preset_data.get("humanization_window_minutes", 40),
                preset_data.get("humanization_inactivity_seconds", 5),
                preset_data.get("dk_power_management", False), preset_data.get("skip_initial_commands", False),
                preset_data.get("use_slash_rolls", False), preset_data.get("only_chaos", False),
                preset_data.get("reactive_snipe_delay", 0), preset_data.get("time_rolls_to_claim_reset", False),
                preset_data.get("rt_ignore_min_kakera_for_wishlist", False),
                preset_data.get("claim_emojis", None),
                preset_data.get("kakera_emojis", None),
                preset_data.get("chaos_emojis", None),
                preset_data.get("rt_only_self_rolls", False),
                preset_data.get("reactive_kakera_delay_range", [0.3, 1.0]),
                preset_data.get("claim_interval", 180),
                preset_data.get("roll_interval", 60)
            )
        except Exception as e:
            print_log(f"Instance crashed: {e}", preset_name, "ERROR")
        
        time.sleep(60)

def start_preset_thread(preset_name, preset_data):
    if not preset_data.get("token"): return None
    t = threading.Thread(target=bot_lifecycle_wrapper, args=(preset_name, preset_data), daemon=True)
    t.start()
    return t

def main_menu():
    banner = r"""
  __  __ _    _ _____          _____  ______ __  __  ____ _______ ______
 |  \/  | |  | |  __ \   /\   |  __ \|  ____|  \/  |/ __ \__   __|  ____|
 | \  / | |  | | |  | | /  \  | |__) | |__  | \  / | |  | | | |  | |__
 | |\/| | |  | | |  | |/ /\ \ |  _  /|  __| | |\/| | |  | | | |  |  __|
 | |  | | |__| | |__| / ____ \| | \ \| |____| |  | | |__| | | |  | |____
 |_|  |_|\____/|_____/_/    \_\_|  \_\______|_|  |_|\____/  |_|  |______|
"""
    print("\033[1;36m" + banner + "\033[0m\n")
    
    threads = []
    while True:
        opts = ['Select and Run Preset', 'Select and Run Multiple', 'Exit']
        q = [inquirer.List('opt', message="Select Option", choices=opts)]
        ans = inquirer.prompt(q)
        
        if not ans or ans['opt'] == 'Exit': break
        
        if ans['opt'] == 'Select and Run Preset':
            p_ans = inquirer.prompt([inquirer.List('p', message="Preset", choices=list(presets.keys()))])
            if p_ans: threads.append(start_preset_thread(p_ans['p'], presets[p_ans['p']]))
            
        elif ans['opt'] == 'Select and Run Multiple':
            p_ans = inquirer.prompt([inquirer.Checkbox('p', message="Presets", choices=list(presets.keys()))])
            if p_ans: 
                for p in p_ans['p']: threads.append(start_preset_thread(p, presets[p]))

def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="Mudae Bot Helper")
    parser.add_argument("--preset", type=str, help="Name of the preset to run")
    parser.add_argument("--all", action="store_true", help="Run all presets")
    return parser.parse_args()

if __name__ == "__main__":
    cleanup_after_update()
    check_for_updates()
    args = parse_args()
    
    if args.preset:
        if args.preset in presets:
            # FIX: Runs directly in main thread to avoid 'set_wakeup_fd' error
            bot_lifecycle_wrapper(args.preset, presets[args.preset])
        else:
            print(f"Preset '{args.preset}' not found.")
    elif args.all:
        started = []
        for p_name, p_data in presets.items():
            t = start_preset_thread(p_name, p_data)
            if t: started.append(t)
        # FIX: Ensure all threads are finished before closing
        for t in started: 
            if t: t.join()
    else:
        # Start the interactive menu
        main_menu()
        
        # FIX: Keep the main thread alive after menu selection so daemon threads don't die
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[MudaRemote] Shutting down...")
