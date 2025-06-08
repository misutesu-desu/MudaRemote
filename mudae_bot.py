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
CLAIM_EMOJIS = ['💖', '💗', '💘', '❤️', '💓', '💕', '♥️', '🪐']
# Reverted KAKERA_EMOJIS list
KAKERA_EMOJIS = ['kakeraY', 'kakeraO', 'kakeraR', 'kakeraW', 'kakeraL']


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
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\033[91m[{timestamp}][System] Error writing to log file: {e}\033[0m")


def print_log(message, preset_name, log_type="INFO"):
    log_message_formatted = color_log(message, preset_name, log_type)
    write_log_to_file(log_message_formatted)


def run_bot(token, prefix, target_channel_id, roll_command, min_kakera, delay_seconds, mudae_prefix,
            log_function, preset_name, key_mode, start_delay, snipe_mode, snipe_delay,
            snipe_ignore_min_kakera_reset, wishlist,
            series_snipe_mode, series_snipe_delay, series_wishlist, roll_speed,
            kakera_snipe_mode_preset, kakera_snipe_threshold_preset,
            enable_reactive_self_snipe_preset, rolling_enabled,
            kakera_reaction_snipe_mode_preset, kakera_reaction_snipe_delay_preset):

    client = commands.Bot(command_prefix=prefix, chunk_guilds_at_startup=False, self_bot=True)

    discord_logger = logging.getLogger('discord')
    discord_logger.propagate = False
    handlers = [h for h in discord_logger.handlers if isinstance(h, logging.StreamHandler)]
    for h in handlers: discord_logger.removeHandler(h)

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

    client.kakera_reaction_snipe_mode_active = kakera_reaction_snipe_mode_preset
    client.kakera_reaction_snipe_delay_value = kakera_reaction_snipe_delay_preset
    client.kakera_reaction_sniped_messages = set()


    @client.event
    async def on_ready():
        log_function(f"[{client.muda_name}] Bot ready: {client.user}", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Target Channel: {target_channel_id}", preset_name, "INFO")
        log_function(f"[{client.muda_name}] Rolling Enabled: {'On' if client.rolling_enabled else 'Off (SNIPE-ONLY MODE)'}", preset_name, "INFO")

        if client.rolling_enabled:
            log_function(f"[{client.muda_name}] Delay: {delay_seconds}s", preset_name, "INFO")
            log_function(f"[{client.muda_name}] Key Mode: {'On' if key_mode else 'Off'}", preset_name, "INFO")

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

        if client.rolling_enabled:
            log_function(f"[{client.muda_name}] Reactive Self-Roll Snipe: {'On' if client.enable_reactive_self_snipe else 'Off'}", preset_name, "INFO")
            if client.enable_reactive_self_snipe:
                log_function(f"[{client.muda_name}]   Reactive Self-Roll Kakera Threshold (for heart claim): {client.kakera_snipe_threshold if client.kakera_snipe_mode_active else 'N/A (kakera_value_snipe_mode off)'}", preset_name, "INFO")
            log_function(f"[{client.muda_name}] Roll Speed: {roll_speed}s", preset_name, "INFO")
            log_function(f"[{client.muda_name}] Min Kakera (General Post-Roll): {client.min_kakera}", preset_name, "INFO")
            log_function(f"[{client.muda_name}] $tu claim ignore_min_kakera_reset: {snipe_ignore_min_kakera_reset}", preset_name, "INFO")

        channel = client.get_channel(target_channel_id)
        if not channel: log_function(f"[{client.muda_name}] Err: No channel {target_channel_id}", preset_name, "ERROR"); await client.close(); return
        if not isinstance(channel, discord.TextChannel): log_function(f"[{client.muda_name}] Err: Not text channel {target_channel_id}", preset_name, "ERROR"); await client.close(); return

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
                log_function(f"[{client.muda_name}] Initial commands (rolling enabled)...", preset_name, "INFO")
                await channel.send(f"{client.mudae_prefix}limroul 1 1 1 1"); await asyncio.sleep(1.0)
                await channel.send(f"{client.mudae_prefix}dk"); await asyncio.sleep(1.0)
                await channel.send(f"{client.mudae_prefix}daily"); await asyncio.sleep(1.0)
                await check_status(client, channel, client.mudae_prefix)
            except discord.errors.Forbidden as e: log_function(f"[{client.muda_name}] Err: Forbidden in setup (rolling) {e}", preset_name, "ERROR"); await client.close()
            except Exception as e: log_function(f"[{client.muda_name}] Err: Unexpected in setup (rolling) {e}", preset_name, "ERROR"); await client.close()
        else:
            log_function(f"[{client.muda_name}] Snipe-Only Mode active. No initial commands will be sent. No status checks performed. Listening for snipes...", preset_name, "INFO")


    async def check_status(client, channel, mudae_prefix):
        log_function(f"[{client.muda_name}] Checking $tu (rolling enabled)...", client.preset_name, "CHECK")
        error_count = 0; max_retries = 5
        tu_message_content = None

        while True:
            await channel.send(f"{mudae_prefix}tu"); await asyncio.sleep(2.5)
            tu_message_content = None
            async for msg in channel.history(limit=10):
                if msg.author.id == TARGET_BOT_ID and msg.content:
                    content_lower_check = msg.content.lower()
                    # FIX: Changed "rolls left" to "roll left" to catch both singular and plural forms.
                    is_tu_message_en = ("roll left" in content_lower_check and \
                                       ("you __can__ claim" in content_lower_check or "can't claim for another" in content_lower_check))
                    is_tu_message_pt = (("roll restantes" in content_lower_check or "rolls restantes" in content_lower_check) and \
                                       ("você __pode__ se casar agora mesmo!" in content_lower_check or "calma aí, falta um tempo antes que você possa se casar novamente" in content_lower_check))

                    if is_tu_message_en or is_tu_message_pt:
                        tu_message_content = msg.content
                        log_function(f"[{client.muda_name}] Found $tu response.", preset_name, "INFO")
                        break
                    # FIX: Changed "rolls left" to "roll left" here as well for the fallback check.
                    elif client.user.name.lower() in content_lower_check.splitlines()[0].lower() and \
                         ("roll left" in content_lower_check or "roll restantes" in content_lower_check or "rolls restantes" in content_lower_check) :
                        tu_message_content = msg.content
                        log_function(f"[{client.muda_name}] Found $tu response (user name match).", preset_name, "INFO")
                        break

            if not tu_message_content:
                error_count += 1; log_function(f"[{client.muda_name}] Err $tu ({error_count}/{max_retries}): Response not found/identified.", preset_name, "ERROR")
                if error_count >= max_retries: log_function(f"[{client.muda_name}] Max $tu retries. Wait 30m.", preset_name, "ERROR"); await asyncio.sleep(1800); error_count = 0
                else: log_function(f"[{client.muda_name}] Retry $tu in 7s.", preset_name, "ERROR"); await asyncio.sleep(7)
                continue
            else:
                break

        content_lower = tu_message_content.lower()
        claim_reset_proceed = False
        lang_log_suffix = ""

        match_can_claim_en = re.search(r"you __can__ claim.*?next claim reset .*?\*\*(\d+h)?\s*(\d+)\*\* min\.?", content_lower)
        match_can_claim_pt = re.search(r"você __pode__ se casar agora mesmo!.*?a próxima reinicialização é em .*?\*\*(\d+h)?\s*(\d+)\*\* min\.?", content_lower)
        match_cant_claim_en = re.search(r"can't claim for another \*\*(\d+h)?\s*(\d+)\*\* min\.?", content_lower)
        match_cant_claim_pt = re.search(r"calma aí, falta um tempo antes que você possa se casar novamente \*\*(\d+h)?\s*(\d+)\*\* min\.?", content_lower)

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
        elif match_c_wait:
            h_s = match_c_wait.group(1); h = int(h_s[:-1]) if h_s else 0; m = int(match_c_wait.group(2))
            log_function(f"[{client.muda_name}] Claim: No. Reset: {h}h {m}m.{lang_log_suffix}", preset_name, "INFO")
            client.current_min_kakera_for_roll_claim = client.min_kakera
            if client.key_mode:
                log_function(f"[{client.muda_name}] KeyMode on. Check rolls.", preset_name, "INFO"); claim_reset_proceed = True
            else:
                log_function(f"[{client.muda_name}] Wait claim reset...", preset_name, "RESET")
                await wait_for_reset((h * 60 + m) * 60, client.delay_seconds, log_function, preset_name)
                await check_status(client, channel, mudae_prefix); return
        else:
            log_function(f"[{client.muda_name}] Ambiguous/Unknown claim status in $tu. Assume No. Check rolls.", preset_name, "WARN")
            client.claim_right_available = False; client.current_min_kakera_for_roll_claim = client.min_kakera
            claim_reset_proceed = True

        if claim_reset_proceed:
            await check_rolls_left_tu(client, channel, mudae_prefix, log_function, preset_name,
                                        tu_message_content_for_rolls=tu_message_content,
                                        ignore_limit_for_post_roll=(client.current_min_kakera_for_roll_claim == 0),
                                        key_mode_only_kakera_for_post_roll=(client.key_mode and not client.claim_right_available))
            return

        log_function(f"[{client.muda_name}] Unexp. state in $tu parse. Retry check_status.", preset_name, "ERROR")
        await asyncio.sleep(7)
        await check_status(client, channel, mudae_prefix)
        return


    async def check_rolls_left_tu(client, channel, mudae_prefix, log_function, preset_name,
                                  tu_message_content_for_rolls, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll):
        log_function(f"[{client.muda_name}] Parsing rolls from $tu (rolling enabled)...", preset_name, "CHECK")
        content_lower = tu_message_content_for_rolls.lower()

        rolls_left = 0; reset_time_r = 0; lang_log_suffix_rolls = ""; parsed_rolls_info = False

        # MODIFIED REGEXES: Restructured to make the optional reset part more robustly captured.
        # The separator (like period, space, newline) is now part of the optional group.
        match_rolls_en = re.search(
            r"you have \*\*(\d+)\*\* rolls?(?: \(.+?\))? left"  # Group 1 for rolls_left
            r"(?:"                                             # Start of optional non-capturing group for reset info
                r"[.\s\n]*?"                                   # Non-greedy separator (dot, whitespace, newline)
                r"next rolls? reset in \*\*(\d+)\*\* min\.?"   # Group 2 for reset_minutes
            r")?",                                             # End of optional non-capturing group
            content_lower,
            re.DOTALL
        )
        match_rolls_pt = re.search(
            r"você tem \*\*(\d+)\*\* rolls? restantes\.?"      # Group 1 for rolls_left
            r"(?:"                                            # Start of optional non-capturing group for reset info
                r"[.\s\n]*?"                                  # Non-greedy separator
                r"a próxima reinicialização é em \*\*(\d+)\*\* min\.?"  # Group 2 for reset_minutes
            r")?",                                            # End of optional non-capturing group
            content_lower,
            re.DOTALL
        )

        roll_match_obj = None; reset_minutes_str = None

        if match_rolls_en:
            roll_match_obj = match_rolls_en # Assign the match object
            rolls_left = int(roll_match_obj.group(1))
            reset_minutes_str = roll_match_obj.group(2) # This is group 2 from the modified regex
            lang_log_suffix_rolls = " (EN)"; parsed_rolls_info = True
        elif match_rolls_pt:
            roll_match_obj = match_rolls_pt # Assign the match object
            rolls_left = int(roll_match_obj.group(1))
            reset_minutes_str = roll_match_obj.group(2) # This is group 2 from the modified regex
            lang_log_suffix_rolls = " (PT)"; parsed_rolls_info = True

        if parsed_rolls_info:
            if reset_minutes_str: # This checks if group(2) captured something
                try: reset_time_r = int(reset_minutes_str)
                except ValueError: log_function(f"[{client.muda_name}] Warn: Roll reset time parse fail (value error).{lang_log_suffix_rolls}", preset_name, "ERROR"); reset_time_r = 0
            else: # reset_minutes_str is None (optional group for reset time didn't match)
                log_function(f"[{client.muda_name}] Warn: Roll reset time phrase not found in $tu.{lang_log_suffix_rolls}", preset_name, "WARN")
                reset_time_r = 0

            if rolls_left == 0:
                log_function(f"[{client.muda_name}] No rolls. Reset: {reset_time_r} min.{lang_log_suffix_rolls}", preset_name, "RESET")
                if reset_time_r <= 0: log_function(f"[{client.muda_name}] Roll reset time is {reset_time_r} min, using default 60 min for wait.", preset_name, "INFO"); reset_time_r = 60
                await wait_for_rolls_reset(reset_time_r, client.delay_seconds, log_function, preset_name)
                await check_status(client, channel, mudae_prefix); return
            else:
                log_function(f"[{client.muda_name}] Rolls left: {rolls_left}. Next reset in {reset_time_r} min.{lang_log_suffix_rolls}", preset_name, "INFO")
                await start_roll_commands(client, channel, rolls_left, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll)
                return
        else:
            log_function(f"[{client.muda_name}] CRITICAL: Roll parse fail from $tu. Re-check status.", preset_name, "ERROR")
            await asyncio.sleep(30); await check_status(client, channel, mudae_prefix); return


    async def start_roll_commands(client, channel, rolls_left, ignore_limit_for_post_roll, key_mode_only_kakera_for_post_roll):
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
        log_function(f"[{client.muda_name}] Rolls sent/interrupted. Wait Mudae msgs...", client.preset_name, "INFO")
        await asyncio.sleep(5)
        mudae_messages_to_process = []; fetch_limit = rolls_left * 2 + 10; processed_count = 0
        try:
            async for msg in channel.history(limit=fetch_limit, after=start_time, oldest_first=False):
                processed_count += 1
                if msg.author.id == TARGET_BOT_ID and msg.embeds and msg.embeds[0].author and msg.embeds[0].author.name:
                         mudae_messages_to_process.append(msg)
            mudae_messages_to_process.reverse()
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
        kakera_claims = []; char_claims_post = []; wl_claims_post = []
        min_kak_post = 0 if ignore_limit_param else client.min_kakera
        log_function(f"[{client.muda_name}] Post-Roll Handle. MinKak(gen):{min_kak_post} (IgnLmtP:{ignore_limit_param},KeyMNoClaimP:{key_mode_only_kakera_param})", preset_name, "CHECK")
        for msg in mudae_messages:
            if not msg.embeds or not msg.embeds[0].author or not msg.embeds[0].author.name: continue
            if msg.components:
                for comp in msg.components:
                    for btn in comp.children:
                        if hasattr(btn.emoji,'name') and btn.emoji.name in KAKERA_EMOJIS: kakera_claims.append(msg); break
            if client.claim_right_available or key_mode_only_kakera_param: # key_mode_only_kakera_param allows populating for RT even if claim is off
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

        # RT logic: Only consider RT if a claim was made OR if it's key_mode and claim is not available (key_mode_only_kakera_param)
        if key_mode_only_kakera_param or claimed_post:
            rt_targets=[i for i in wl_claims_post if i[0].id!=msg_claimed_id] + [i for i in char_claims_post if i[0].id!=msg_claimed_id]
            rt_targets.sort(key=lambda x:x[2],reverse=True) # Sort by kakera value, highest first
            if rt_targets:
                msg_rt,n_rt,v_rt=rt_targets[0] # Get the best available character for RT
                
                # MODIFIED: RT decision strictly uses client.min_kakera
                if v_rt >= client.min_kakera:
                    log_function(f"[{client.muda_name}] (Post) RT: {n_rt} ({v_rt}) vs MinKakRT: {client.min_kakera}", preset_name, "CLAIM")
                    try: 
                        await channel.send(f"{client.mudae_prefix}rt"); await asyncio.sleep(0.7)
                        await claim_character(client,channel,msg_rt,is_rt_claim=True)
                    except Exception as e: 
                        log_function(f"[{client.muda_name}] (Post) RT Err: {e}", preset_name, "ERROR")
                # Log if RT was skipped due to this stricter check, but would have passed the general min_kak_post
                elif v_rt >= min_kak_post : # This implies it met general (potentially 0) threshold but not strict RT threshold
                     log_function(f"[{client.muda_name}] (Post) RT Skipped: {n_rt} ({v_rt}) < MinKakRT: {client.min_kakera} (but was >= Gen. Post-Roll MinKak: {min_kak_post})", preset_name, "INFO")


    async def claim_character(client, channel, msg, is_kakera=False, is_rt_claim=False):
        if not msg or not msg.embeds: log_function(f"[{client.muda_name}] Invalid msg to claim_character.", preset_name, "ERROR"); return False
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
                        except Exception as e: log_function(f"{log_px} {log_action_desc} Fail (Unexp {e}){log_sx}", preset_name, "ERROR"); return False
        if not btn_clicked_ok and not is_kakera and not is_rt_claim:
            log_function(f"{log_px} No btn for {char_name}. Fallback react.", preset_name, "INFO")
            try:
                log_function(f"{log_px} {log_action_desc}{log_sx} (react)", client.preset_name, log_ty)
                await msg.add_reaction("💖"); await asyncio.sleep(1.5); return True
            except Exception as e: log_function(f"{log_px} {log_action_desc} React Fail{log_sx}: {e}", preset_name, "ERROR"); return False
        elif not btn_clicked_ok: log_function(f"{log_px} No btn for {log_action_desc} on {char_name}", preset_name, "INFO")
        return False

    async def wait_for_reset(seconds_to_wait, base_delay_seconds, log_function, preset_name):
        if seconds_to_wait <= 0: seconds_to_wait = 1
        total_wait = seconds_to_wait + base_delay_seconds; end_time = datetime.datetime.now() + datetime.timedelta(seconds=total_wait)
        log_function(f"[{client.muda_name}] Wait claim reset. Total: {total_wait:.2f}s. Resume ~{end_time.strftime('%H:%M:%S')}", preset_name, "RESET")
        await asyncio.sleep(total_wait); log_function(f"[{client.muda_name}] Claim wait done.", preset_name, "RESET")

    async def wait_for_rolls_reset(reset_time_minutes, base_delay_seconds, log_function, preset_name):
        actual_reset_time_minutes = reset_time_minutes
        if reset_time_minutes <= 0 :
            actual_reset_time_minutes = 60
            log_function(f"[{client.muda_name}] Invalid roll reset time ({reset_time_minutes}m), using default {actual_reset_time_minutes}m.", preset_name, "WARN")

        wait_seconds_duration = actual_reset_time_minutes * 60
        total_wait = wait_seconds_duration + base_delay_seconds + 15
        end_time = datetime.datetime.now() + datetime.timedelta(seconds=total_wait)
        log_function(f"[{client.muda_name}] Wait rolls reset (~{actual_reset_time_minutes}m). Total: {total_wait:.2f}s. Resume ~{end_time.strftime('%H:%M:%S')}", preset_name, "RESET")
        await asyncio.sleep(total_wait); log_function(f"[{client.muda_name}] Roll wait done.", preset_name, "RESET")


    @client.event
    async def on_message(message):
        if message.author.id != TARGET_BOT_ID or message.channel.id != client.target_channel_id:
            if client.rolling_enabled: await client.process_commands(message)
            return
        if not message.embeds: return
        embed = message.embeds[0]; process_further = True

        if client.rolling_enabled and client.enable_reactive_self_snipe and client.is_actively_rolling and client.claim_right_available:
            if embed.author and embed.author.name:
                char_name_l = embed.author.name.lower(); desc = embed.description or ""; series_l=(desc.splitlines()[0] if desc else "").lower(); k_val=0
                match_k = re.search(r"\*\*([\d,]+)\*\*<:kakera:", desc);
                if match_k:
                    try: k_val = int(match_k.group(1).replace(",",""))
                    except ValueError: pass
                is_wl = any(w == char_name_l for w in client.wishlist)
                is_series_wl = client.series_wishlist and any(sw in series_l for sw in client.series_wishlist)
                is_k_snipe_criterion = client.kakera_snipe_mode_active and k_val >= client.kakera_snipe_threshold

                if is_wl or is_series_wl or is_k_snipe_criterion:
                    has_claim_btn = any(hasattr(b.emoji,'name') and b.emoji.name in CLAIM_EMOJIS for comp in message.components for b in comp.children)
                    if has_claim_btn:
                        if await claim_character(client, message.channel, message, is_kakera=False):
                            client.claim_right_available=False; client.interrupt_rolling=True; client.snipe_happened=True; process_further=False
                            if any(hasattr(b.emoji,'name') and b.emoji.name in KAKERA_EMOJIS for comp in message.components for b in comp.children):
                                await asyncio.sleep(0.2); await claim_character(client, message.channel, message, is_kakera=True)

        if process_further:
            # FIX: Added 'and not client.is_actively_rolling' to prevent external series snipe during own rolls
            if client.series_snipe_mode and client.series_wishlist and message.id not in client.series_sniped_messages and not client.is_actively_rolling:
                desc = embed.description or "";
                if desc:
                    first_line = desc.splitlines()[0].lower()
                    if any(kw in first_line for kw in client.series_wishlist):
                        if any(hasattr(b.emoji,'name') and b.emoji.name in CLAIM_EMOJIS for comp in message.components for b in comp.children):
                            client.series_sniped_messages.add(message.id); s_name = embed.author.name if embed.author else desc.splitlines()[0]
                            log_function(f"[{client.muda_name}] Ext.Series Snipe: {s_name} (Delay {client.series_snipe_delay}s)", preset_name, "CLAIM")
                            await asyncio.sleep(client.series_snipe_delay)
                            if await claim_character(client, message.channel, message): client.series_snipe_happened=True; process_further=False

            # FIX: Added 'and not client.is_actively_rolling' to prevent external character snipe during own rolls
            if process_further and client.snipe_mode and client.wishlist and message.id not in client.sniped_messages and not client.is_actively_rolling:
                if embed.author and embed.author.name:
                    char_name_l = embed.author.name.lower()
                    is_snipe_ext = any(w == char_name_l for w in client.wishlist)
                    if is_snipe_ext:
                        if any(hasattr(b.emoji,'name') and b.emoji.name in CLAIM_EMOJIS for comp in message.components for b in comp.children):
                            client.sniped_messages.add(message.id)
                            log_function(f"[{client.muda_name}] Ext.Char Snipe: {embed.author.name} (Delay {client.snipe_delay}s)", preset_name, "CLAIM")
                            await asyncio.sleep(client.snipe_delay)
                            if await claim_character(client, message.channel, message): client.snipe_happened=True; process_further=False

            # FIX: Added 'and not client.is_actively_rolling' to prevent external kakera snipe during own rolls
            if process_further and client.kakera_snipe_mode_active and message.id not in client.kakera_value_sniped_messages and not client.is_actively_rolling:
                if embed.author and embed.author.name:
                    desc = embed.description or ""; k_val=0
                    match_k_ext = re.search(r"\*\*([\d,]+)\*\*<:kakera:", desc)
                    if match_k_ext:
                        try: k_val = int(match_k_ext.group(1).replace(",",""))
                        except ValueError: pass

                    if k_val >= client.kakera_snipe_threshold:
                        if any(hasattr(b.emoji,'name') and b.emoji.name in CLAIM_EMOJIS for comp in message.components for b in comp.children):
                            client.kakera_value_sniped_messages.add(message.id)
                            log_function(f"[{client.muda_name}] Ext.Kakera Val. Snipe: {embed.author.name} ({k_val}) (Delay {client.snipe_delay}s)", preset_name, "CLAIM")
                            await asyncio.sleep(client.snipe_delay)
                            if await claim_character(client, message.channel, message):
                                client.snipe_happened = True
                                process_further = False
            
            # FIX: Added 'and not client.is_actively_rolling' to prevent external kakera reaction snipe during own rolls
            if process_further and client.kakera_reaction_snipe_mode_active and message.id not in client.kakera_reaction_sniped_messages and not client.is_actively_rolling:
                has_kakera_button_for_external_snipe = False
                if message.components:
                    for comp in message.components:
                        for btn in comp.children:
                            if hasattr(btn.emoji, 'name') and btn.emoji.name in KAKERA_EMOJIS:
                                has_kakera_button_for_external_snipe = True
                                break
                        if has_kakera_button_for_external_snipe:
                            break

                if has_kakera_button_for_external_snipe:
                    client.kakera_reaction_sniped_messages.add(message.id)
                    log_subject_name = "Kakera Event"
                    if embed.author and embed.author.name:
                        log_subject_name = embed.author.name
                    elif embed.description:
                        log_subject_name = embed.description.splitlines()[0][:30]

                    log_function(f"[{client.muda_name}] Ext.KakeraReact Snipe: {log_subject_name} (Delay {client.kakera_reaction_snipe_delay_value}s)", client.preset_name, "KAKERA")
                    await asyncio.sleep(client.kakera_reaction_snipe_delay_value)
                    await claim_character(client, message.channel, message, is_kakera=True)

        if client.rolling_enabled and client.enable_reactive_self_snipe and client.is_actively_rolling and process_further: #This part is for self-roll kakera reaction
            # Check if it's a character embed and kakera is present
            if embed.author and embed.author.name: # Ensure it's a character embed
                desc = embed.description or ""; k_val=0
                match_k = re.search(r"\*\*([\d,]+)\*\*<:kakera:", desc)
                if match_k:
                    try: k_val = int(match_k.group(1).replace(",",""))
                    except ValueError: pass

                kakera_button_present = any(hasattr(b.emoji,'name') and b.emoji.name in KAKERA_EMOJIS for comp in message.components for b in comp.children)

                # Click kakera if:
                # 1. Kakera button is present.
                # 2. EITHER kakera_snipe_mode_active is OFF (meaning click any kakera)
                # 3. OR kakera_snipe_mode_active is ON AND k_val meets the threshold
                # 4. OR kakera_snipe_threshold is 0 (meaning click any kakera if mode is on)
                should_click_kakera = kakera_button_present and \
                                      (not client.kakera_snipe_mode_active or k_val >= client.kakera_snipe_threshold or client.kakera_snipe_threshold == 0)

                if should_click_kakera:
                    if await claim_character(client, message.channel, message, is_kakera=True):
                        pass # Kakera claimed

        if process_further and client.rolling_enabled: # Only process commands if rolling is enabled for this bot
            await client.process_commands(message)


    try: client.run(token)
    except discord.errors.LoginFailure: log_function(f"[{BOT_NAME}] LoginFail '{preset_name}'. Check token.", preset_name, "ERROR")
    except Exception as e: log_function(f"[{BOT_NAME}] Unexp Err '{preset_name}': {e}", preset_name, "ERROR")

def start_preset_thread(preset_name, preset_data):
     if not validate_preset(preset_name, preset_data): print(f"\033[91mSkip preset '{preset_name}' (config err).\033[0m"); return None
     print(f"\033[92mStarting bot for preset: {preset_name}\033[0m")
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


     thread = threading.Thread(target=run_bot, args=(
         preset_data["token"], preset_data["prefix"], preset_data["channel_id"],
         preset_data["roll_command"], preset_data["min_kakera"], preset_data["delay_seconds"],
         preset_data["mudae_prefix"], print_log, preset_name, key_mode, start_delay,
         snipe_mode, snipe_delay, snipe_ignore_min_kakera_reset, wishlist,
         series_snipe_mode, series_snipe_delay, series_wishlist, roll_speed,
         kakera_snipe_mode_preset, kakera_snipe_threshold_preset,
         enable_reactive_self_snipe_preset, rolling_enabled_preset,
         kakera_reaction_snipe_mode_p, kakera_reaction_snipe_delay_p
     ), daemon=True); thread.start(); return thread

def show_banner():
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
    req_k = ["token","prefix","channel_id","roll_command","min_kakera","delay_seconds","mudae_prefix"]
    miss_k = [k for k in req_k if k not in preset_data]
    if miss_k: print(f"\033[91mErr '{preset_name}': Missing: {','.join(miss_k)}\033[0m"); return False
    if not isinstance(preset_data["token"],str) or not preset_data["token"]: print(f"\033[91mErr '{preset_name}': 'token' bad.\033[0m"); return False
    if not isinstance(preset_data["channel_id"],int): print(f"\033[91mErr '{preset_name}': 'channel_id' bad.\033[0m"); return False

    if not isinstance(preset_data["min_kakera"],int) or preset_data["min_kakera"]<0: print(f"\033[91mErr '{preset_name}': 'min_kakera' bad (number >= 0).\033[0m"); return False
    if not isinstance(preset_data["delay_seconds"],(int,float)) or preset_data["delay_seconds"]<0: print(f"\033[91mErr '{preset_name}': 'delay_seconds' bad (number >= 0).\033[0m"); return False

    if "rolling" in preset_data and not isinstance(preset_data["rolling"], bool):
        print(f"\033[91mErr '{preset_name}': 'rolling' field, if present, must be a boolean (true or false).\033[0m")
        return False

    if "key_mode" in preset_data and not isinstance(preset_data["key_mode"],bool): print(f"\033[91mWarn '{preset_name}': 'key_mode' should be boolean.\033[0m")
    if "start_delay" in preset_data and (not isinstance(preset_data["start_delay"],(int,float)) or preset_data["start_delay"]<0): print(f"\033[91mWarn '{preset_name}': 'start_delay' should be number >=0.\033[0m")
    if "snipe_mode" in preset_data and not isinstance(preset_data["snipe_mode"],bool): print(f"\033[91mWarn '{preset_name}': 'snipe_mode' should be boolean.\033[0m")
    if "snipe_delay" in preset_data and (not isinstance(preset_data["snipe_delay"], (int,float)) or preset_data["snipe_delay"] < 0): print(f"\033[91mWarn '{preset_name}': 'snipe_delay' should be number >=0.\033[0m")
    if "wishlist" in preset_data and not isinstance(preset_data["wishlist"],list): print(f"\033[91mWarn '{preset_name}': 'wishlist' should be a list.\033[0m")
    if "kakera_snipe_mode" in preset_data and not isinstance(preset_data["kakera_snipe_mode"],bool): print(f"\033[91mWarn '{preset_name}': 'kakera_snipe_mode' should be boolean.\033[0m")
    if "kakera_snipe_threshold" in preset_data and (not isinstance(preset_data["kakera_snipe_threshold"],int) or preset_data["kakera_snipe_threshold"]<0): print(f"\033[91mWarn '{preset_name}': 'kakera_snipe_threshold' should be non-neg int.\033[0m")
    if "reactive_snipe_on_own_rolls" in preset_data and not isinstance(preset_data["reactive_snipe_on_own_rolls"], bool):
        print(f"\033[91mWarn in preset '{preset_name}': 'reactive_snipe_on_own_rolls' should be true or false.\033[0m")

    if "kakera_reaction_snipe_mode" in preset_data and not isinstance(preset_data["kakera_reaction_snipe_mode"], bool):
        print(f"\033[91mWarn in preset '{preset_name}': 'kakera_reaction_snipe_mode' should be true or false.\033[0m")
    if "kakera_reaction_snipe_delay" in preset_data and (not isinstance(preset_data["kakera_reaction_snipe_delay"], (int, float)) or preset_data["kakera_reaction_snipe_delay"] < 0):
        print(f"\033[91mWarn in preset '{preset_name}': 'kakera_reaction_snipe_delay' should be a non-negative number.\033[0m")

    return True

def main_menu():
    show_banner(); active_threads = []
    while True:
        active_threads = [t for t in active_threads if t.is_alive()]
        questions = [inquirer.List('option',message=f"Select ({len(active_threads)} bots run):",choices=['Select and Run Preset','Select and Run Multiple Presets','Exit'])]
        try:
            answers = inquirer.prompt(questions)
            if not answers: print("\nExiting..."); break
            option = answers['option']
            if option == 'Select and Run Preset':
                preset_list = list(presets.keys())
                if not preset_list: print("\033[91mNo presets in presets.json.\033[0m"); continue
                preset_answers = inquirer.prompt([inquirer.List('preset',message="Select preset:",choices=preset_list)])
                if preset_answers:
                    thread = start_preset_thread(preset_answers['preset'], presets[preset_answers['preset']])
                    if thread: active_threads.append(thread)
            elif option == 'Select and Run Multiple Presets':
                preset_list = list(presets.keys())
                if not preset_list: print("\033[91mNo presets in presets.json.\033[0m"); continue
                multi_preset_answers = inquirer.prompt([inquirer.Checkbox('presets',message="Select presets (Space, Enter):",choices=preset_list)])
                if multi_preset_answers:
                    for preset_name in multi_preset_answers['presets']:
                        thread = start_preset_thread(preset_name, presets[preset_name])
                        if thread: active_threads.append(thread)
            elif option == 'Exit': print("\033[1;32mExiting MudaRemote...\033[0m"); break
        except KeyboardInterrupt: print("\nCtrl+C. Exiting..."); break
        except Exception as e: print(f"\033[91mMenu error: {e}\033[0m")

if __name__ == "__main__":
    try:
        with open("logs.txt", "a", encoding='utf-8') as f: f.write(f"\n--- MudaRemote Log Start: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    except Exception as e: print(f"\033[91mLog file init error: {e}\033[0m")
    main_menu()
