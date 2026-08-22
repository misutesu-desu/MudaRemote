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

    wanted = {"add_text_field", "add_number_field", "add_checkbox", "add_list_field", "add_optional_list_field"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr not in wanted:
            continue
        args = [literal(arg) for arg in node.args]
        if len(args) < 3 or not isinstance(args[1], str) or not isinstance(args[2], str):
            continue
        key, label = args[1], args[2]
        entry = settings.setdefault(key, {})
        entry.setdefault("label", label)
        description = literal(next((kw.value for kw in node.keywords if kw.arg == "description"), None))
        if isinstance(description, str) and description.strip():
            entry["description"] = description.strip()
        if node.func.attr == "add_number_field" and len(args) > 3 and "default" not in entry:
            entry["default"] = args[3]

    for key, value in defaults.items():
        entry = settings.setdefault(key, {})
        entry.setdefault("default", value)
        entry.setdefault("label", key.replace("_", " ").title())
        entry.setdefault("description", "This setting is also available in the desktop preset editor.")

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
    }
    for key, value in list_field_defaults.items():
        entry = settings.setdefault(key, {})
        if not isinstance(entry.get("default"), list):
            entry["default"] = list(value)
    settings.setdefault("token", {
        "default": "", "label": "Discord Account Token (stored separately)",
        "description": "Keep this secret. Android stores it separately with the device Keystore."
    })

    section_groups = {
        "Connection": {"token", "channel_id", "command_channel_id", "prefix", "mudae_prefix", "roll_command", "main_account_id", "webhook_url", "webhook_log_types"},
        "Rolling": {"rolling", "roll_speed", "roll_interval", "delay_seconds", "start_delay", "use_slash_rolls", "auto_rolls_enabled", "auto_rolls_limit", "auto_rolls_in_key_mode", "auto_rolls_only_claim_hour", "auto_us_enabled", "auto_us_limit", "auto_us_stop_on_claim", "bulk_us_enabled", "skip_initial_commands"},
        "Claiming": {"min_kakera", "claim_interval", "max_claim_rank", "max_like_rank", "panic_roll_minutes", "auto_free_claim", "auto_rt_after_claim", "rt_ignore_min_kakera_for_wishlist", "rt_only_self_rolls"},
        "Character Sniping": {"snipe_mode", "snipe_delay", "snipe_channels", "character_snipe_targets", "reactive_snipe_on_own_rolls", "reactive_snipe_delay", "series_snipe_mode", "series_snipe_delay", "series_snipe_only_self_rolls", "series_wishlist", "kakera_snipe_mode", "kakera_snipe_threshold", "enable_snipe_chat_reactions", "snipe_chat_messages"},
        "Kakera Reactions": {"kakera_reaction_snipe_mode", "kakera_reaction_snipe_delay", "kakera_reaction_snipe_targets", "kakera_snipe_channels", "enable_kakera_snipe_chat_reactions", "kakera_snipe_chat_messages", "immediate_kakera_click", "collect_purple_kakera", "kakera_power_thresholds", "auto_dk_enabled", "auto_dk_min_power", "max_dk_power"},
        "Wishlist and Farming": {"wishlist", "avoid_list", "key_mode", "only_chaos", "farm_character", "farm_characters", "farm_character_enabled", "forcedivorce_channel_id", "farm_forcedivorce_before_roll", "farm_forcedivorce_after_claim", "farm_forcedivorce_after_other_claim", "auto_divorce_enabled", "auto_divorce_max_kakera", "auto_divorce_series", "auto_divorce_blacklist", "auto_divorce_blacklist_series", "auto_divorce_protect_wishes"},
        "Spheres and Emoji": {"claim_emojis", "kakera_emojis", "chaos_emojis", "sphere_perk_emojis", "randomized_claim_reactions", "kakera_priority_order", "sphere_click_targets", "auto_oh_enabled", "oh_priority_order", "oh_unknown_explore_clicks", "oh_use_individually", "auto_oc_enabled", "oc_reward_priority_order", "oc_collect_after_red"},
        "Timing and Humanization": {"humanization_enabled", "humanization_window_minutes", "humanization_inactivity_seconds", "inactive_hours", "scheduled_roll_times", "persistent_stagger_seconds", "time_rolls_to_claim_reset"},
        "Advanced": {"debug_mode", "debug_log_categories", "autostart", "op_perk_5_only", "mk_only", "auto_mk_enabled", "auto_mk_full_power_only", "mk_bypass_power_check", "dk_power_management", "auto_p_enabled", "enable_hybrid_panic_claim", "hybrid_panic_instant_claim_min_kakera", "hybrid_panic_instant_claim_max_rank", "claim_rounds_thresholds", "wish_starwish_kakera_only", "randomized_claim_reactions"},
    }
    sections = {key: section for section, keys in section_groups.items() for key in keys}
    for key, entry in settings.items():
        if "default" not in entry:
            entry["default"] = ""
        entry.setdefault("label", key.replace("_", " ").title())
        entry.setdefault("description", "This setting is also available in the desktop preset editor.")
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
