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

# --- Global Configuration ---
BOT_NAME = "MudaRemote"

# Load presets from the JSON file
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

# Target bot ID (Mudae's official ID)
TARGET_BOT_ID = 432610292342587392

# ANSI color codes for console logging
COLORS = {
    "INFO": "\033[94m",    # Blue
    "CLAIM": "\033[92m",   # Green
    "KAKERA": "\033[93m",  # Yellow
    "ERROR": "\033[91m",    # Red
    "CHECK": "\033[95m",    # Magenta
    "RESET": "\033[36m",    # Cyan
    "ENDC": "\033[0m"      # End Color
}

# Emojis for claims and kakera reactions
CLAIM_EMOJIS = ['💖', '💗', '💘', '❤️', '💓', '💕', '♥️', '🪐']
KAKERA_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL']

# --- Logging Functions ---

def color_log(message, preset_name, log_type="INFO"):
    """Formats a log message with a timestamp, preset name, and color."""
    color_code = COLORS.get(log_type.upper(), COLORS["INFO"])
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}][{preset_name}] {message}"
    print(f"{color_code}{log_message}{COLORS['ENDC']}")
    return log_message

def write_log_to_file(log_message):
    """Appends a log message to the logs.txt file."""
    try:
        with open("logs.txt", "a", encoding='utf-8') as log_file:
            log_file.write(log_message + "\n")
    except Exception as e:
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\033[91m[{timestamp}][System] Error writing to log file: {e}\033[0m")

def print_log(message, preset_name, log_type="INFO"):
    """Prints a colored log message to the console and writes it to the log file."""
    log_message_formatted = color_log(message, preset_name, log_type)
    write_log_to_file(log_message_formatted)

# --- Main Bot Logic ---

def run_bot(token, prefix, target_channel_id, roll_command, min_kakera, delay_seconds, mudae_prefix,
            log_function, preset_name, key_mode, start_delay, snipe_mode, snipe_delay,
            snipe_ignore_min_kakera_reset, wishlist,
            series_snipe_mode, series_snipe_delay, series_wishlist, roll_speed,
            kakera_snipe_mode_preset, kakera_snipe_threshold_preset,
            enable_reactive_self_snipe_preset, rolling_enabled,
            kakera_reaction_snipe_mode_preset, kakera_reaction_snipe_delay_preset):

    client = commands.Bot(command_prefix=prefix, self_bot=True)

    # --- Suppress 'Command Not Found' errors to keep logs clean ---
    @client.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return # Silently ignore commands not meant for this bot
        log_function(f"A command error occurred: {error}", preset_name, "ERROR")

    # Disable default discord.py logging to avoid console clutter
    discord_logger = logging.getLogger('discord')
    discord_logger.propagate = False
    handlers = [h for h in discord_logger.handlers if isinstance(h, logging.StreamHandler)]
    for h in handlers: discord_logger.removeHandler(h)

    # --- Set initial client attributes from the preset ---
    client.preset_name = preset_name
    client.min_kakera = min_kakera
    client.snipe_mode = snipe_mode
    client.snipe_delay = snipe_delay
    client.snipe_ignore_min_kakera_reset = snipe_ignore_min_kakera_reset
    client.wishlist = [w.lower() for w in wishlist]
    client.series_snipe_mode = series_snipe_mode
    client.series_snipe_delay = series_snipe_delay
    client.series_wishlist = [sw.lower() for sw in series_wishlist]
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
    client.rolling_enabled = rolling_enabled
    client.kakera_reaction_snipe_mode_active = kakera_reaction_snipe_mode_preset
    client.kakera_reaction_snipe_delay_value = kakera_reaction_snipe_delay_preset
    client.kakera_reaction_sniped_messages = set()

    @client.event
    async def on_ready():
        """Event triggered when the bot is connected and ready."""
        log_function(f"[{client.muda_name}] Bot ready: {client.user}", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Target Channel: {target_channel_id}", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Rolling Enabled: {'On' if client.rolling_enabled else 'Off (SNIPE-ONLY MODE)'}", preset_name, "INFO")
        # Log other configuration details...
        channel = client.get_channel(target_channel_id)
        # Verify channel exists and bot has permissions...
        
        log_function(f"[{client.muda_name}] Initial delay: {start_delay}s...", preset_name, "INFO")
        await asyncio.sleep(start_delay)

        if client.rolling_enabled:
            try:
                log_function(f"[{client.muda_name}] Sending initial commands (rolling enabled)...", preset_name, "INFO")
                await channel.send(f"{client.mudae_prefix}limroul 1 1 1 1"); await asyncio.sleep(1.0)
                await channel.send(f"{client.mudae_prefix}dk"); await asyncio.sleep(1.0)
                await channel.send(f"{client.mudae_prefix}daily"); await asyncio.sleep(1.0)
                await check_status(client, channel, client.mudae_prefix)
            except discord.errors.Forbidden as e:
                log_function(f"[{client.muda_name}] Error: Forbidden during setup (rolling): {e}", preset_name, "ERROR"); await client.close()
            except Exception as e:
                log_function(f"[{client.muda_name}] Error: Unexpected during setup (rolling): {e}", preset_name, "ERROR"); await client.close()
        else:
            log_function(f"[{client.muda_name}] Snipe-Only Mode active. No initial commands sent. Listening for snipes...", preset_name, "INFO")

    # =====================================================================================
    # === MAJOR CHANGE HERE: check_status() function made more robust. ===
    # =====================================================================================
    async def check_status(client, channel, mudae_prefix):
        """
        Sends '$tu' and reliably finds and parses Mudae's response to determine
        claim and roll status. This function is designed to be resilient against
        variations in Mudae's message format.
        """
        log_function(f"[{client.muda_name}] Checking $tu (rolling enabled)...", client.preset_name, "CHECK")
        error_count = 0
        max_retries = 5
        tu_message_content = None

        while True:
            await channel.send(f"{mudae_prefix}tu")
            await asyncio.sleep(3)  # Give Mudae some time to respond
            tu_message_content = None
            
            # Search for a valid response in recent channel history
            async for msg in channel.history(limit=15):
                if msg.author.id == TARGET_BOT_ID and msg.content:
                    content_lower = msg.content.lower()
                    # NEW, ROBUST CHECK: A valid $tu response must be directed at the user.
                    if content_lower.startswith(client.user.name.lower()):
                        # It must also contain keywords related to status.
                        if "claim reset" in content_lower or "rolls reset" in content_lower or "can't claim for another" in content_lower or "rolls left" in content_lower:
                            tu_message_content = msg.content
                            log_function(f"[{client.muda_name}] Found a valid $tu response.", preset_name, "INFO")
                            break # Exit the history loop once a valid message is found

            if not tu_message_content:
                error_count += 1
                log_function(f"[{client.muda_name}] Err $tu ({error_count}/{max_retries}): Response not found/identified.", preset_name, "ERROR")
                if error_count >= max_retries:
                    log_function(f"[{client.muda_name}] Max $tu retries reached. Waiting 30 minutes.", preset_name, "ERROR")
                    await asyncio.sleep(1800)
                    error_count = 0  # Reset counter after long wait
                else:
                    log_function(f"[{client.muda_name}] Retrying $tu in 7s.", preset_name, "ERROR")
                    await asyncio.sleep(7)
                continue  # Retry the while loop
            else:
                break # Exit the while loop since we have the message content

        # Now, parse the reliably found message content
        content_lower = tu_message_content.lower()
        
        # Determine claim availability
        if "you can claim right now" in content_lower or "você pode se casar agora mesmo" in content_lower:
            client.claim_right_available = True
        else:
            client.claim_right_available = False

        # Parse claim reset time if user can't claim
        match_cant_claim_en = re.search(r"can't claim for another \*\*(\d+h)?\s*(\d+)\*\* min\.?", content_lower)
        match_cant_claim_pt = re.search(r"calma aí, falta um tempo antes que você possa se casar novamente \*\*(\d+h)?\s*(\d+)\*\* min\.?", content_lower)
        
        if not client.claim_right_available and (match_cant_claim_en or match_cant_claim_pt):
            match_wait = match_cant_claim_en or match_cant_claim_pt
            h_s = match_wait.group(1); h = int(h_s[:-1]) if h_s else 0; m = int(match_wait.group(2))
            log_function(f"[{client.muda_name}] Claim: No. Reset in: {h}h {m}m.", preset_name, "INFO")
            client.current_min_kakera_for_roll_claim = client.min_kakera
            if client.key_mode:
                log_function(f"[{client.muda_name}] KeyMode is on. Proceeding to check rolls.", preset_name, "INFO")
            else:
                log_function(f"[{client.muda_name}] Waiting for claim reset...", preset_name, "RESET")
                await wait_for_reset((h * 60 + m) * 60, client.delay_seconds, log_function, preset_name)
                await check_status(client, channel, mudae_prefix)
                return
        else:
            log_function(f"[{client.muda_name}] Claim: Yes.", preset_name, "INFO")
            # Determine min_kakera for post-roll based on reset proximity and settings
            match_reset_claim = re.search(r"next claim reset in \*\*(\d+h)?\s*(\d+)\*\* min\.?", content_lower)
            if match_reset_claim:
                h_s = match_reset_claim.group(1); h = int(h_s[:-1]) if h_s else 0; m = int(match_reset_claim.group(2))
                if (h * 60 + m) * 60 <= 3600 and client.snipe_ignore_min_kakera_reset:
                    client.current_min_kakera_for_roll_claim = 0
                else:
                    client.current_min_kakera_for_roll_claim = client.min_kakera
            else:
                client.current_min_kakera_for_roll_claim = client.min_kakera

        # Proceed to check rolls
        await check_rolls_left_tu(client, channel, mudae_prefix, log_function, preset_name,
                                    tu_message_content_for_rolls=tu_message_content,
                                    ignore_limit_for_post_roll=(client.current_min_kakera_for_roll_claim == 0),
                                    key_mode_only_kakera_for_post_roll=(client.key_mode and not client.claim_right_available))

    async def check_rolls_left_tu(client, channel, mudae_prefix, log_function, preset_name,
                                  tu_message_content_for_rolls, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll):
        """Parses the roll count and reset time from the $tu message content."""
        log_function(f"[{client.muda_name}] Parsing rolls from $tu content...", preset_name, "CHECK")
        content_lower = tu_message_content_for_rolls.lower()

        rolls_left = 0
        reset_time_r = 0

        # Regex to find rolls left. Handles "roll" vs "rolls" and bonus rolls like `(+3 $mk)`.
        match_rolls = re.search(r"you have \*\*(\d+)\*\* rolls?(?: \(.+?\))? left", content_lower)
        if not match_rolls:
            match_rolls = re.search(r"você tem \*\*(\d+)\*\* rolls? restantes\.?", content_lower)

        if match_rolls:
            rolls_left = int(match_rolls.group(1))
        else:
            # If the "You have X rolls" line is missing, it implies 0 rolls left.
            rolls_left = 0
            log_function(f"[{client.muda_name}] 'Rolls left' phrase not found. Assuming 0 rolls.", preset_name, "INFO")

        # Regex to find the next rolls reset time.
        match_reset = re.search(r"next rolls? reset in \*\*(\d+)\*\* min", content_lower)
        if not match_reset:
            match_reset = re.search(r"a próxima reinicialização é em \*\*(\d+)\*\* min", content_lower)

        if match_reset:
            reset_time_r = int(match_reset.group(1))
        else:
            log_function(f"[{client.muda_name}] 'Rolls reset' time not found. Assuming default wait if needed.", preset_name, "WARN")
            reset_time_r = 0

        if rolls_left == 0:
            log_function(f"[{client.muda_name}] No rolls left. Reset in: {reset_time_r} min.", preset_name, "RESET")
            if reset_time_r <= 0:
                log_function(f"[{client.muda_name}] Roll reset time is invalid ({reset_time_r}m), using default 60m wait.", preset_name, "INFO")
                reset_time_r = 60
            await wait_for_rolls_reset(reset_time_r, client.delay_seconds, log_function, preset_name)
            await check_status(client, channel, mudae_prefix)
        else:
            log_function(f"[{client.muda_name}] Rolls left: {rolls_left}. Next reset in {reset_time_r} min.", preset_name, "INFO")
            await start_roll_commands(client, channel, rolls_left, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll)

    async def start_roll_commands(client, channel, rolls_left, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll):
        """Sends the roll commands and orchestrates post-roll processing."""
        # ... [This function's logic is sound and does not need changes]
        log_text = f"Starting {rolls_left} rolls"
        if client.enable_reactive_self_snipe: log_text += " (Reactive Snipe ON)"
        else: log_text += " (Reactive Snipe OFF)"
        log_function(f"[{client.muda_name}] {log_text}", client.preset_name, "INFO")
        start_time = datetime.datetime.now(datetime.timezone.utc)
        client.is_actively_rolling = True; client.interrupt_rolling = False
        for i in range(rolls_left):
            if client.interrupt_rolling:
                log_function(f"[{client.muda_name}] Rolling interrupted. {i}/{rolls_left} sent.", client.preset_name, "INFO")
                client.interrupt_rolling = False; break
            try: await channel.send(f"{client.mudae_prefix}{roll_command}"); await asyncio.sleep(client.roll_speed)
            except discord.errors.HTTPException as e: log_function(f"[{client.muda_name}] Error sending roll: {e}. Skip.", preset_name, "ERROR"); await asyncio.sleep(1)
        client.is_actively_rolling = False
        log_function(f"[{client.muda_name}] Rolls sent/interrupted. Waiting for Mudae messages...", client.preset_name, "INFO")
        await asyncio.sleep(5)
        mudae_messages_to_process = []; fetch_limit = rolls_left * 2 + 10; processed_count = 0
        try:
            async for msg in channel.history(limit=fetch_limit, after=start_time, oldest_first=False):
                processed_count += 1
                if msg.author.id == TARGET_BOT_ID and msg.embeds and msg.embeds[0].author and msg.embeds[0].author.name:
                         mudae_messages_to_process.append(msg)
            mudae_messages_to_process.reverse()
            log_function(f"[{client.muda_name}] Fetched {processed_count} messages. Processing {len(mudae_messages_to_process)} post-roll messages.", client.preset_name, "INFO")
            if mudae_messages_to_process:
                 await handle_mudae_messages(client, channel, mudae_messages_to_process, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll)
            else: log_function(f"[{client.muda_name}] No character messages found for post-roll processing.", client.preset_name, "INFO")
        except Exception as e: log_function(f"[{client.muda_name}] Error fetching/processing post-roll messages: {e}", preset_name, "ERROR")
        await asyncio.sleep(2)
        if client.snipe_happened or client.series_snipe_happened:
            log_function(f"[{client.muda_name}] Claim/Snipe occurred. Re-checking status.", client.preset_name, "INFO")
            client.snipe_happened = False; client.series_snipe_happened = False
        else: log_function(f"[{client.muda_name}] Rolls complete. Re-checking status.", client.preset_name, "INFO")
        await asyncio.sleep(1); await check_status(client, channel, client.mudae_prefix)

    async def handle_mudae_messages(client, channel, mudae_messages, ignore_limit_param, key_mode_only_kakera_param):
        """Processes a list of Mudae messages after rolling to claim characters/kakera."""
        # ... [This function's logic is sound and does not need changes]
        kakera_claims = []; char_claims_post = []; wl_claims_post = []
        min_kak_post = 0 if ignore_limit_param else client.min_kakera
        log_function(f"[{client.muda_name}] Post-Roll Handle. MinKak(gen):{min_kak_post} (IgnLmtP:{ignore_limit_param},KeyMNoClaimP:{key_mode_only_kakera_param})", preset_name, "CHECK")
        for msg in mudae_messages:
            if not msg.embeds or not msg.embeds[0].author or not msg.embeds[0].author.name: continue
            if msg.components:
                for comp in msg.components:
                    for btn in comp.children:
                        if hasattr(btn.emoji,'name') and btn.emoji.name in KAKERA_EMOJIS: kakera_claims.append(msg); break
            if client.claim_right_available or key_mode_only_kakera_param:
                char_n=msg.embeds[0].author.name.lower(); desc=msg.embeds[0].description or ""; k_v=0
                match_k=re.search(r"\*\*([\d,]+)\*\*<:kakera:",desc);
                if match_k:
                    try: k_v=int(match_k.group(1).replace(",",""))
                    except ValueError: pass
                is_wl = any(w == char_n for w in client.wishlist)
                has_claim_b = any(hasattr(b.emoji,'name') and b.emoji.name in CLAIM_EMOJIS for c in msg.components for b in c.children)
                if has_claim_b:
                    if is_wl: wl_claims_post.append((msg,char_n,k_v))
                    elif k_v >= min_kak_post: char_claims_post.append((msg,char_n,k_v))
        
        for msg_k in kakera_claims: await claim_character(client,channel,msg_k,is_kakera=True); await asyncio.sleep(0.3)

        claimed_post=False; msg_claimed_id=-1
        if client.claim_right_available and wl_claims_post:
            msg_c,n,v=wl_claims_post[0]; log_function(f"[{client.muda_name}] (Post) Gen. WL: {n}", preset_name, "CLAIM")
            if await claim_character(client,channel,msg_c,is_kakera=False): claimed_post=True;client.claim_right_available=False;msg_claimed_id=msg_c.id
        elif client.claim_right_available and char_claims_post:
            char_claims_post.sort(key=lambda x:x[2],reverse=True); msg_c,n,v=char_claims_post[0]
            log_function(f"[{client.muda_name}] (Post) Gen. HV: {n} ({v})", preset_name, "CLAIM")
            if await claim_character(client,channel,msg_c,is_kakera=False): claimed_post=True;client.claim_right_available=False;msg_claimed_id=msg_c.id

        if key_mode_only_kakera_param or claimed_post:
            rt_targets=[i for i in wl_claims_post if i[0].id!=msg_claimed_id] + [i for i in char_claims_post if i[0].id!=msg_claimed_id]
            rt_targets.sort(key=lambda x:x[2],reverse=True)
            if rt_targets:
                msg_rt,n_rt,v_rt=rt_targets[0]
                if v_rt >= client.min_kakera:
                    log_function(f"[{client.muda_name}] (Post) RT: {n_rt} ({v_rt}) vs MinKakRT: {client.min_kakera}", preset_name, "CLAIM")
                    try: 
                        await channel.send(f"{client.mudae_prefix}rt"); await asyncio.sleep(0.7)
                        await claim_character(client,channel,msg_rt,is_rt_claim=True)
                    except Exception as e: 
                        log_function(f"[{client.muda_name}] (Post) RT Err: {e}", preset_name, "ERROR")
                elif v_rt >= min_kak_post :
                     log_function(f"[{client.muda_name}] (Post) RT Skipped: {n_rt} ({v_rt}) < MinKakRT: {client.min_kakera} (but was >= Gen. Post-Roll MinKak: {min_kak_post})", preset_name, "INFO")

    async def claim_character(client, channel, msg, is_kakera=False, is_rt_claim=False):
        """Clicks the claim or kakera button on a given message."""
        # ... [This function's logic is sound and does not need changes]
        if not msg or not msg.embeds: log_function(f"[{client.muda_name}] Invalid message passed to claim_character.", preset_name, "ERROR"); return False
        embed = msg.embeds[0]; char_name = embed.author.name if embed.author and embed.author.name else "Unknown"; log_px = f"[{client.muda_name}]"; log_sx = f": {char_name}"; log_ty = "CLAIM"
        btns_to_click = CLAIM_EMOJIS; log_action_desc = "Claim"
        if is_kakera: log_action_desc = "Kakera"; log_ty = "KAKERA"; btns_to_click = KAKERA_EMOJIS
        elif is_rt_claim: log_action_desc = "RT Claim"
        btn_clicked_ok = False
        if msg.components:
            for comp in msg.components:
                if btn_clicked_ok: break
                for btn in comp.children:
                    if hasattr(btn.emoji, 'name') and btn.emoji and btn.emoji.name in btns_to_click:
                        try:
                            log_function(f"{log_px} {log_action_desc}{log_sx}", client.preset_name, log_ty)
                            await btn.click(); btn_clicked_ok=True; await asyncio.sleep(1.5); return True
                        except discord.errors.NotFound: log_function(f"{log_px} {log_action_desc} Fail (NotFound){log_sx}", preset_name, "ERROR"); return False
                        except discord.errors.HTTPException as e: log_function(f"{log_px} {log_action_desc} Fail (HTTP {e.status}){log_sx}", preset_name, "ERROR"); return False
                        except Exception as e: log_function(f"{log_px} {log_action_desc} Fail (Unexpected {e}){log_sx}", preset_name, "ERROR"); return False
        if not btn_clicked_ok and not is_kakera and not is_rt_claim:
            log_function(f"{log_px} No button found for {char_name}. Falling back to reaction.", preset_name, "INFO")
            try:
                log_function(f"{log_px} {log_action_desc}{log_sx} (react)", client.preset_name, log_ty)
                await msg.add_reaction("💖"); await asyncio.sleep(1.5); return True
            except Exception as e: log_function(f"{log_px} {log_action_desc} React Fail{log_sx}: {e}", preset_name, "ERROR"); return False
        elif not btn_clicked_ok: log_function(f"{log_px} No button found for {log_action_desc} on {char_name}", preset_name, "INFO")
        return False

    async def wait_for_reset(seconds_to_wait, base_delay_seconds, log_function, preset_name):
        """Pauses execution to wait for the claim timer to reset."""
        # ... [This function's logic is sound and does not need changes]
        if seconds_to_wait <= 0: seconds_to_wait = 1
        total_wait = seconds_to_wait + base_delay_seconds; end_time = datetime.datetime.now() + datetime.timedelta(seconds=total_wait)
        log_function(f"[{client.muda_name}] Waiting for claim reset. Total: {total_wait:.2f}s. Resuming at ~{end_time.strftime('%H:%M:%S')}", preset_name, "RESET")
        await asyncio.sleep(total_wait); log_function(f"[{client.muda_name}] Claim wait complete.", preset_name, "RESET")

    async def wait_for_rolls_reset(reset_time_minutes, base_delay_seconds, log_function, preset_name):
        """Pauses execution to wait for the rolls timer to reset."""
        # ... [This function's logic is sound and does not need changes]
        actual_reset_time_minutes = reset_time_minutes
        if reset_time_minutes <= 0 :
            actual_reset_time_minutes = 60
            log_function(f"[{client.muda_name}] Invalid roll reset time ({reset_time_minutes}m), using default {actual_reset_time_minutes}m.", preset_name, "WARN")

        wait_seconds_duration = actual_reset_time_minutes * 60
        total_wait = wait_seconds_duration + base_delay_seconds + 15
        end_time = datetime.datetime.now() + datetime.timedelta(seconds=total_wait)
        log_function(f"[{client.muda_name}] Waiting for rolls reset (~{actual_reset_time_minutes}m). Total: {total_wait:.2f}s. Resuming at ~{end_time.strftime('%H:%M:%S')}", preset_name, "RESET")
        await asyncio.sleep(total_wait); log_function(f"[{client.muda_name}] Rolls wait complete.", preset_name, "RESET")

    @client.event
    async def on_message(message):
        """The main event handler for processing incoming messages."""
        # ... [This function's logic is sound and does not need changes]
        # Ignore messages not from Mudae or not in the target channel
        if message.author.id != TARGET_BOT_ID or message.channel.id != client.target_channel_id:
            if client.rolling_enabled: await client.process_commands(message) # Process own commands
            return

        if not message.embeds: return
        embed = message.embeds[0]; process_further = True

        # --- Reactive Snipe Logic for Own Rolls ---
        if client.rolling_enabled and client.enable_reactive_self_snipe and client.is_actively_rolling and client.claim_right_available:
            if embed.author and embed.author.name:
                # [logic for reactive snipe]
                pass # This section is complex but its internal logic is fine

        # --- External Snipe Logic (for other users' rolls) ---
        if process_further:
            # Series Snipe
            if client.series_snipe_mode and client.series_wishlist and message.id not in client.series_sniped_messages and not client.is_actively_rolling:
                # [logic for series snipe]
                pass
            # Character Wishlist Snipe
            if process_further and client.snipe_mode and client.wishlist and message.id not in client.sniped_messages and not client.is_actively_rolling:
                # [logic for wishlist snipe]
                pass
            # Kakera Value Snipe
            if process_further and client.kakera_snipe_mode_active and message.id not in client.kakera_value_sniped_messages and not client.is_actively_rolling:
                # [logic for kakera value snipe]
                pass
            # Kakera Reaction Snipe
            if process_further and client.kakera_reaction_snipe_mode_active and message.id not in client.kakera_reaction_sniped_messages and not client.is_actively_rolling:
                # [logic for kakera reaction snipe]
                pass
        
        # --- Kakera reaction on own rolls ---
        if client.rolling_enabled and client.enable_reactive_self_snipe and client.is_actively_rolling and process_further:
            # [logic for kakera reaction on self-rolls]
            pass

        if process_further and client.rolling_enabled:
            await client.process_commands(message)

    try:
        client.run(token)
    except discord.errors.LoginFailure:
        log_function(f"[{BOT_NAME}] Login failed for preset '{preset_name}'. Please check the token.", preset_name, "ERROR")
    except Exception as e:
        log_function(f"[{BOT_NAME}] An unexpected error occurred in preset '{preset_name}': {e}", preset_name, "ERROR")

# --- Bot Initialization and Menu ---

def start_preset_thread(preset_name, preset_data):
     """Validates a preset and starts it in a new thread."""
     if not validate_preset(preset_name, preset_data):
         print(f"\033[91mSkipping preset '{preset_name}' due to configuration errors.\033[0m")
         return None
     print(f"\033[92mStarting bot for preset: {preset_name}\033[0m")
     # ... [Extracting preset data] ...
     thread = threading.Thread(target=run_bot, args=(...), daemon=True) # daemon=True allows main to exit
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
    print("\033[1;36m" + banner + "\033[0m")
    print("\033[1;33mWelcome to MudaRemote - Your Remote Mudae Assistant\033[0m\n")

def validate_preset(preset_name, preset_data):
    """Checks a preset for required keys and valid data types."""
    # ... [This function's logic is sound and does not need changes]
    return True

def main_menu():
    """Displays the main interactive menu for selecting and running presets."""
    show_banner()
    active_threads = []
    while True:
        active_threads = [t for t in active_threads if t.is_alive()]
        questions = [
            inquirer.List(
                'option',
                message=f"Select an option ({len(active_threads)} bots running):",
                choices=['Select and Run a Preset', 'Select and Run Multiple Presets', 'Exit']
            )
        ]
        try:
            answers = inquirer.prompt(questions)
            if not answers: # Handle Ctrl+C
                print("\nExiting..."); break
            option = answers['option']
            if option == 'Select and Run a Preset':
                # [logic for single preset selection]
                pass
            elif option == 'Select and Run Multiple Presets':
                # [logic for multiple preset selection]
                pass
            elif option == 'Exit':
                print("\033[1;32mExiting MudaRemote...\033[0m"); break
        except KeyboardInterrupt:
            print("\nCtrl+C detected. Exiting..."); break
        except Exception as e:
            print(f"\033[91mAn error occurred in the menu: {e}\033[0m")

if __name__ == "__main__":
    try:
        # Create a separator in the log file for each new session
        with open("logs.txt", "a", encoding='utf-8') as f:
            f.write(f"\n--- MudaRemote Log Start: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    except Exception as e:
        print(f"\033[91mFailed to initialize log file: {e}\033[0m")
    main_menu()
