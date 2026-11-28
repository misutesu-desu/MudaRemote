"""Generate the Android preset schema from the desktop editor source.

The generated file is a build artifact. Keeping the source of truth in
`mudae_preset_editor.py` prevents the Android labels/defaults from drifting.
"""

import ast
import json
import os
import sys


def literal(node, fallback=None):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return fallback


def main(project_root, output_dir):
    source_path = os.path.join(project_root, "mudae_preset_editor.py")
    tree = ast.parse(open(source_path, encoding="utf-8").read(), filename=source_path)
    defaults = {}
    settings = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            value = literal(node.value)
            if name == "DEFAULTS" and isinstance(value, dict):
                defaults.update(value)
            elif name in {"BOOL_SETTINGS", "NUMERIC_SETTINGS", "TEXT_SETTINGS"} and isinstance(value, list):
                for item in value:
                    if isinstance(item, (list, tuple)) and len(item) >= 3:
                        settings.setdefault(str(item[0]), {})["default"] = item[2]

    wanted = {"add_text_field", "add_number_field", "add_checkbox", "add_list_field", "add_optional_list_field", "add_choice_field", "add_profile_picker"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr not in wanted:
            continue
        args = [literal(arg) for arg in node.args]
        if len(args) < 3 or not isinstance(args[1], str) or not isinstance(args[2], str):
            continue
        key, label = args[1], args[2]
        entry = settings.setdefault(key, {})
        entry.setdefault("label", label)
        if node.func.attr == "add_choice_field" and len(args) > 3:
            entry["choices"] = args[3]
        description = literal(next((kw.value for kw in node.keywords if kw.arg == "description"), None))
        if isinstance(description, str) and description.strip():
            entry["description"] = description.strip()
        if node.func.attr == "add_number_field" and len(args) > 3 and "default" not in entry:
            entry["default"] = args[3]

    for key, value in defaults.items():
        entry = settings.setdefault(key, {})
        entry.setdefault("default", value)
        entry.setdefault("label", key.replace("_", " ").title())
        entry.setdefault("description", "")  # no filler text: the app shows nothing without a real description

    # The desktop editor derives emoji-list defaults from module constants
    # rather than the DEFAULTS mapping, so the AST scan above never sees them.
    # Without explicit list defaults these fields used to fall back to ""
    # (typed "text"), producing string configs that crash the engine's list
    # concatenation at runtime.
    emoji_defaults = [
        "kakeraY", "kakeraO", "kakeraR", "kakeraW", "kakeraL",
        "kakeraP", "kakeraD", "kakeraC", "kakeraG", "kakeraT", "kakera",
    ]
    list_field_defaults = {
        "claim_emojis": ["💖", "💗", "💘", "❤️", "💓", "💕", "♥️"],
        "kakera_emojis": list(emoji_defaults),
        "chaos_emojis": list(emoji_defaults),
        "sphere_perk_emojis": list(emoji_defaults),
        # Optional override: absent/empty inherits kakera_emojis at runtime,
        # but the schema still needs a typed list default.
        "mk_kakera_emojis": list(emoji_defaults),
        # Absent means OP5 rolls keep their normal context.
        "op5_kakera_emojis": list(emoji_defaults),
    }
    for key, value in list_field_defaults.items():
        entry = settings.setdefault(key, {})
        if not isinstance(entry.get("default"), list):
            entry["default"] = list(value)
    settings.setdefault("token", {
        "default": "", "label": "Discord Account Token (stored separately)",
        "description": "Keep this secret. Android stores it separately with the device Keystore."
    })
    # Multi-account support: desktop presets expand every entry of "tokens"
    # into its own running account ("Name", "Name #2", ...). The first token
    # is the main; the extra entries are its alts (mudae_core.account_roles).
    tokens_entry = settings.setdefault("tokens", {
        "default": [],
        "label": "Account Tokens (multi-account)",
    })
    tokens_entry["description"] = "Extra tokens here are your alts. The first token (above) is the main."
    if not isinstance(tokens_entry.get("default"), list):
        tokens_entry["default"] = []
    # Desktop-only UI convenience (splits primary vs extra tokens); the editor
    # merges it away before saving, so exposing it here would be a dead control.
    settings.pop("additional_tokens", None)

    section_groups = {
        "Connection": {"token", "tokens", "channel_id", "command_channel_id", "prefix", "mudae_prefix", "roll_command", "webhook_url", "webhook_log_types"},
        "Main & alts": {"account_role", "main_profile_id", "side_order", "side_rolls_for_main", "side_rolls_max_per_reset", "side_claim_leftovers", "main_claims_alt_rolls", "main_claims_alt_rolls_mode", "alts_claim_main_rolls", "main_rolls_while_alt_can_claim", "accounts_share_kakera_reacts", "main_account_id", "fast_setup", "fast_setup_round", "auto_give_kakera", "give_kakera_threshold", "give_kakera_amount_mode", "give_kakera_daily_cap", "give_kakera_button_minimum", "give_kakera_now_round", "auto_give_spheres", "sphere_give_interval_min", "spheres_keep", "give_spheres_now_round", "auto_give_harem", "harem_give_trigger", "harem_give_pages", "harem_give_characters", "harem_give_value", "harem_check_hours", "harem_give_pages_text", "harem_keep_first_pages", "harem_give_daily_cap", "auto_perk10", "side_perk10", "perk10_min_spheres", "perk10_max_characters", "perk10_daily_cap", "perk10_amount", "perk10_now_round"},
        "Rolling": {"hourly_tu_refresh", "rolling", "pause_on_key_limit", "key_limit_pause_scope", "roll_speed", "roll_interval", "delay_seconds", "start_delay", "use_slash_rolls", "slash_claim_target", "slash_claim_limit", "slash_claim_window_minutes", "auto_rolls_enabled", "auto_rolls_limit", "auto_rolls_in_key_mode", "auto_rolls_only_claim_hour", "auto_us_enabled", "auto_us_limit", "auto_us_stop_on_claim", "bulk_us_enabled", "skip_initial_commands"},
        "Kakera Loot": {"loot_mode", "kl_amount", "scrap_target_id", "scrap_amount", "loot_min_cooldown", "loot_max_cooldown"},
        "Claiming": {"min_kakera", "claim_interval", "max_claim_rank", "max_like_rank", "lurker_mode", "lurker_final_round_only", "panic_roll_minutes", "auto_free_claim", "auto_rt_enabled", "auto_rt_after_claim", "rt_ignore_min_kakera_for_wishlist", "rt_only_self_rolls", "rt_in_command_channel", "rt_min_kakera"},
        "Character Sniping": {"snipe_mode", "snipe_delay", "snipe_channels", "character_snipe_targets", "snipe_ignore_users", "reactive_snipe_on_own_rolls", "reactive_snipe_delay", "series_snipe_mode", "series_snipe_delay", "series_snipe_only_self_rolls", "series_wishlist", "kakera_snipe_mode", "kakera_snipe_threshold", "enable_snipe_chat_reactions", "snipe_chat_messages"},
        "Kakera Reactions": {"kakera_reaction_snipe_mode", "kakera_reaction_snipe_delay", "kakera_reaction_snipe_targets", "kakera_snipe_channels", "enable_kakera_snipe_chat_reactions", "kakera_snipe_chat_messages", "immediate_kakera_click", "collect_purple_kakera", "shop_perk_7_only", "kakera_power_thresholds", "auto_dk_enabled", "auto_dk_min_power", "max_dk_power"},
        "Wishlist and Farming": {"wishlist", "avoid_list", "key_mode", "only_chaos", "farm_character", "farm_characters", "farm_character_enabled", "forcedivorce_channel_id", "farm_forcedivorce_before_roll", "farm_forcedivorce_after_claim", "farm_forcedivorce_after_other_claim", "auto_divorce_enabled", "auto_divorce_max_kakera", "auto_divorce_series", "auto_divorce_blacklist", "auto_divorce_blacklist_series", "auto_divorce_protect_wishes"},
        "Spheres and Emoji": {"claim_emojis", "kakera_emojis", "chaos_emojis", "sphere_perk_emojis", "mk_kakera_emojis", "op5_kakera_emojis", "randomized_claim_reactions", "kakera_priority_order", "sphere_click_targets", "sphere_collect_any_last", "auto_oh_enabled", "oh_priority_order", "oh_unknown_explore_clicks", "oh_use_individually", "auto_oc_enabled", "oc_reward_priority_order", "oc_collect_after_red", "auto_oq_enabled", "auto_ot_enabled", "sphere_games_daily_only"},
        "Timing and Humanization": {"humanization_enabled", "humanization_window_minutes", "humanization_inactivity_seconds", "inactive_hours", "scheduled_roll_times", "persistent_stagger_seconds", "time_rolls_to_claim_reset"},
        "Advanced": {"debug_mode", "debug_log_categories", "save_logs_txt", "logs_keep_days", "logs_max_mb", "autostart", "op_perk_5_only", "mk_only", "auto_mk_enabled", "auto_mk_full_power_only", "mk_bypass_power_check", "dk_power_management", "auto_p_enabled", "enable_hybrid_panic_claim", "hybrid_panic_instant_claim_min_kakera", "hybrid_panic_instant_claim_max_rank", "claim_rounds_thresholds", "wish_starwish_kakera_only", "randomized_claim_reactions"},
    }
    sections = {key: section for section, keys in section_groups.items() for key in keys}
    # The Android app fills this field with a picker of the other profiles and
    # stores the picked profile's stable id (see MainActivity.buildFieldView).
    settings.setdefault("main_profile_id", {})["picker"] = "profile"
    # The old separate-profile fields come last («Advanced: separate profiles»).
    role_order = ["side_rolls_for_main", "main_rolls_while_alt_can_claim",
                  "side_rolls_max_per_reset", "side_claim_leftovers", "main_claims_alt_rolls",
                  "main_claims_alt_rolls_mode", "alts_claim_main_rolls", "accounts_share_kakera_reacts",
                  "main_account_id",
                  "fast_setup", "fast_setup_round", "auto_give_kakera", "give_kakera_threshold",
                  "give_kakera_amount_mode", "give_kakera_daily_cap", "give_kakera_button_minimum",
                  "auto_give_spheres", "sphere_give_interval_min", "spheres_keep",
                  "auto_give_harem", "harem_give_trigger", "harem_give_pages",
                  "harem_give_characters", "harem_give_value", "harem_check_hours", "harem_give_pages_text",
                  "harem_keep_first_pages", "harem_give_daily_cap", "auto_perk10", "side_perk10", "perk10_min_spheres",
                  "perk10_max_characters", "perk10_daily_cap", "perk10_amount",
                  "account_role", "main_profile_id", "side_order",
                  # the manual actions: small rows at the very end of the group
                  "give_kakera_now_round", "give_spheres_now_round", "perk10_now_round"]
    for order, key in enumerate(role_order):
        settings.setdefault(key, {})["order"] = order
    # «Send again» for Fast setup: the app shows a button that raises this
    # counter (and switches Fast setup on) instead of a number field.
    settings.setdefault("fast_setup_round", {}).update({
        "widget": "send_again",
        "label": "Fast setup: Send again",
        "description": "Fast setup is sent once and then stays off. Press to send it once more (save to apply).",
    })
    # Give settings («side_only») stay editable; a profile without alt tokens
    # shows one hint line under them (MainActivity.buildFieldView).
    # «Give all kakera now»: a button that raises this request counter and saves
    # (the running side then gives its whole total once).
    settings.setdefault("give_kakera_now_round", {}).update({
        "widget": "request_now",
        "label": "Give kakera now",
        "description": "One give of the whole kakera total to the main, when it is known and at least «Minimum for the button». The account must be running.",
    })
    settings.setdefault("give_spheres_now_round", {}).update({
        "widget": "request_now",
        "label": "Give spheres now",
        "description": "One give of all the spheres (minus «Spheres to keep on this account») to the main. The account must be running.",
    })
    settings.setdefault("perk10_amount", {}).update({
        "label": "Characters to upgrade each time (0 = as many as the spheres allow)",
        "description": "Optional. Once the spheres reach the minimum, it upgrades exactly this many (or fewer when the spheres afford fewer). 0 upgrades as many as the spheres allow.",
    })
    settings.setdefault("perk10_now_round", {}).update({
        "widget": "request_now",
        "label": "Upgrade perk 10 now",
        "description": "One perk-10 upgrade now (needs at least 1,000 spheres known). Works with the automatic switch off; alts only with «Let side accounts upgrade too». The account must be running.",
    })
    # The 6.0.x switch «give_kakera_extra» is replaced by the choice «give_kakera_amount_mode»; the app does not show
    # it (a stored profile keeps the key, and the bot reads it when the choice is absent).
    settings.pop("give_kakera_extra", None)
    settings.setdefault("auto_perk10", {}).update({
        "label": "Upgrade perk 10 automatically",
        "description": "Upgrades the main's characters. Alts upgrade too only with «Let side accounts upgrade too». "
                       "Off by default.",
    })
    settings.setdefault("auto_give_spheres", {})["description"] = (
        "Each alt sends its spheres to the main automatically. Off on the alts while «Let side accounts upgrade too» "
        "is on (your choice here is kept). Waits for the sphere games first. Off by default.")
    # The 6.0.0 separate side profiles: kept for old profiles, not offered for new ones.
    for key in ("account_role", "main_profile_id", "side_order"):
        entry = settings.setdefault(key, {})
        entry["label"] = "Advanced: separate profiles — " + str(entry.get("label", key))
        entry["description"] = ("Only for profiles set up before alts lived under Account Tokens; leave as is. "
                                + str(entry.get("description", "")).strip())
    for key in ("auto_give_kakera", "give_kakera_threshold", "give_kakera_amount_mode", "give_kakera_daily_cap",
                "give_kakera_button_minimum", "give_kakera_now_round", "auto_give_spheres",
                "sphere_give_interval_min", "spheres_keep", "give_spheres_now_round",
                "auto_give_harem", "harem_give_trigger", "harem_give_pages", "harem_give_characters", "harem_give_value", "harem_check_hours",
                "harem_give_pages_text", "harem_keep_first_pages", "harem_give_daily_cap"):
        settings.setdefault(key, {})["side_only"] = True
    filter_keys = ["kakera_filter_match_mode", "only_chaos", "perk_eight_only", "shop_perk_7_only", "mk_only", "op_perk_5_only", "wish_starwish_kakera_only"]
    for order, key in enumerate(filter_keys):
        sections[key] = "Kakera Reactions"
        settings[key]["order"] = order
    for key, entry in settings.items():
        if "default" not in entry:
            entry["default"] = ""
        entry.setdefault("label", key.replace("_", " ").title())
        entry.setdefault("description", "")  # no filler text: the app shows nothing without a real description
        entry["section"] = sections.get(key, "Advanced")
        value = entry["default"]
        if isinstance(value, bool):
            entry["type"] = "boolean"
        elif isinstance(value, (int, float)):
            entry["type"] = "number"
        elif isinstance(value, (list, dict)):
            entry["type"] = "json"
        else:
            entry["type"] = "text"

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "android_schema.json")
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump({"fields": settings}, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
