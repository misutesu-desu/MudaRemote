"""Preset-to-client configuration for MudaRemote.

This module owns the translation from a validated preset dictionary to the
per-client attributes consumed by the bot lifecycle.  It intentionally does
not import ``mudae_bot`` so that the setup logic can be read and tested
independently of the event-loop harness.
"""

import datetime
from datetime import timezone

from mudae_core.kakera import (
    KakeraInteractionLedger,
    KakeraPowerLedger,
    normalize_character_sphere_emoji,
)
from mudae_core.runtime import (
    NormalRollActionOwner,
    RollActionTiming,
    RollCommandCorrelation,
)
from mudae_core.spheres import SphereButtonBudget
from mudae_core.status import ResetAnchor, initialize_status_tracking


def configure_client(
    client,
    preset_name,
    preset_data,
    *,
    bot_name,
    claim_emojis,
    kakera_emojis,
    sphere_emojis,
    slash_available,
):
    """Apply one preset to a fresh discord.py client.

    Missing values use the lifecycle defaults historically supplied by
    ``bot_lifecycle_wrapper``, not the standalone ``run_bot`` signature
    defaults.
    """

    # Identity and target channel
    client.preset_name = preset_name
    client.muda_name = bot_name
    client.claim_right_available = False
    try:
        client.target_channel_id = int(preset_data.get("channel_id"))
    except (TypeError, ValueError):
        client.target_channel_id = preset_data.get("channel_id")
    client.roll_command = (
        str(preset_data.get("roll_command", "wa") or "wa").strip().lstrip("/")
        or "wa"
    )
    client.command_channel_id_preset = str(
        preset_data.get("command_channel_id") or ""
    ).strip()
    client.forcedivorce_channel_id_preset = str(
        preset_data.get("forcedivorce_channel_id") or ""
    ).strip()

    # Basic rolling and snipe settings
    client.min_kakera = preset_data.get("min_kakera", 100)
    client.base_min_kakera = client.min_kakera
    client.roll_speed = preset_data.get("roll_speed", 0.4)
    client.mudae_prefix = preset_data.get("mudae_prefix", "$")
    client.key_mode = preset_data.get("key_mode", False)
    client.pause_on_key_limit = bool(preset_data.get("pause_on_key_limit", True))
    client.delay_seconds = preset_data.get("delay_seconds", 0)
    client.rolling_enabled = preset_data.get("rolling", True)
    client.skip_initial_commands = preset_data.get("skip_initial_commands", False)
    client.use_slash_rolls = bool(
        preset_data.get("use_slash_rolls", False) and slash_available
    )
    client.slash_claim_target = str(preset_data.get("slash_claim_target") or "").strip().casefold()
    try:
        client.slash_claim_limit = max(0, int(preset_data.get("slash_claim_limit") or 0))
    except (TypeError, ValueError):
        client.slash_claim_limit = 0
    try:
        client.slash_claim_window_minutes = max(1, int(preset_data.get("slash_claim_window_minutes") or 180))
    except (TypeError, ValueError):
        client.slash_claim_window_minutes = 180
    if client.use_slash_rolls and client.slash_claim_target and client.slash_claim_limit:
        from .roll_mode import adaptive_slash_ledger
        adaptive_slash_ledger.register(
            client.target_channel_id, client.slash_claim_target, client.slash_claim_window_minutes
        )

    # Snipe configuration
    client.snipe_mode = preset_data.get("snipe_mode", False)
    client.snipe_delay = preset_data.get("snipe_delay", 2)
    client.snipe_ignore_min_kakera_reset = preset_data.get(
        "snipe_ignore_min_kakera_reset", False
    )
    client.wishlist = set(w.lower() for w in preset_data.get("wishlist", []))
    client.series_snipe_mode = preset_data.get("series_snipe_mode", False)
    client.series_snipe_only_self_rolls = bool(
        preset_data.get("series_snipe_only_self_rolls", False)
    )
    client.series_snipe_delay = preset_data.get("series_snipe_delay", 3)
    client.series_wishlist = set(
        sw.lower() for sw in preset_data.get("series_wishlist", [])
    )
    client.avoid_list = set(
        a.lower() for a in (preset_data.get("avoid_list") or [])
    )

    client.snipe_channels = set()
    for ch in preset_data.get("snipe_channels") or []:
        try:
            client.snipe_channels.add(int(ch))
        except (TypeError, ValueError):
            pass
    client.kakera_snipe_channels = set()
    configured_kakera_snipe_channels = (
        preset_data.get("kakera_snipe_channels")
        or preset_data.get("snipe_channels")
        or []
    )
    for ch in configured_kakera_snipe_channels:
        try:
            client.kakera_snipe_channels.add(int(ch))
        except (TypeError, ValueError):
            pass

    client.max_claim_rank = int(preset_data.get("max_claim_rank", 0) or 0)
    client.max_like_rank = int(preset_data.get("max_like_rank", 0) or 0)
    client.base_max_claim_rank = client.max_claim_rank
    client.base_max_like_rank = client.max_like_rank

    # Kakera / reaction snipe configuration
    client.kakera_snipe_mode_active = preset_data.get("kakera_snipe_mode", False)
    client.kakera_snipe_threshold = preset_data.get("kakera_snipe_threshold", 0)
    client.enable_reactive_self_snipe = preset_data.get(
        "reactive_snipe_on_own_rolls", True
    )
    client.reactive_snipe_delay = preset_data.get("reactive_snipe_delay", 0)
    client.kakera_reaction_snipe_mode_active = preset_data.get(
        "kakera_reaction_snipe_mode", False
    )
    client.kakera_reaction_snipe_delay_value = preset_data.get(
        "kakera_reaction_snipe_delay", 0.75
    )
    client.kakera_reaction_snipe_targets = set(
        t.lower() for t in preset_data.get("kakera_reaction_snipe_targets", [])
    )
    client.character_snipe_targets = set(
        t.lower().strip()
        for t in (preset_data.get("character_snipe_targets") or [])
        if t.strip()
    )
    client.kakera_reaction_sniped_messages = set()
    client.kakera_react_available = None
    client.kakera_react_cooldown_until_utc = None
    client.auto_free_claim_enabled = bool(preset_data.get("auto_free_claim", True))

    # Humanization and maintenance
    client.humanization_enabled = preset_data.get("humanization_enabled", False)
    client.humanization_window_minutes = preset_data.get(
        "humanization_window_minutes", 40
    )
    client.humanization_inactivity_seconds = preset_data.get(
        "humanization_inactivity_seconds", 5
    )
    client.inactive_hours = preset_data.get("inactive_hours") or []
    client.maintenance_until = None

    # DK / power / US / MK / rolls automation
    client.auto_dk_enabled = preset_data.get("auto_dk_enabled", True)
    client.dk_power_management = preset_data.get("dk_power_management", False)
    client.dk_stock_count = 0
    client.max_dk_power = preset_data.get("max_dk_power", 100)
    client.auto_dk_min_power = max(
        0, int(preset_data.get("auto_dk_min_power", 0) or 0)
    )
    client.only_chaos = preset_data.get("only_chaos", False)
    client.perk_eight_only = bool(preset_data.get("perk_eight_only", False))
    client.shop_perk_7_only = preset_data.get("shop_perk_7_only", False)
    client.kakera_filter_match_mode = (
        "any" if preset_data.get("kakera_filter_match_mode", "all") == "any" else "all"
    )
    client.mk_only = preset_data.get("mk_only", False)

    client.auto_us_enabled = preset_data.get("auto_us_enabled", False)
    client.auto_us_limit = preset_data.get("auto_us_limit", 0)
    client.auto_us_stop_on_claim = preset_data.get("auto_us_stop_on_claim", True)
    client.bulk_us_enabled = preset_data.get("bulk_us_enabled", False)
    client.us_pulled_this_cycle = 0
    client.mk_rolls_left = 0
    client.auto_mk_enabled = preset_data.get("auto_mk_enabled", True)
    client.auto_mk_full_power_only = bool(
        preset_data.get("auto_mk_full_power_only", False)
    )
    client._mk_full_power_refresh_at = None
    client._mk_full_power_refresh_handle = None
    client._mk_full_power_wait_signature = None

    client.auto_rolls_enabled = preset_data.get("auto_rolls_enabled", False)
    client.auto_rolls_limit = preset_data.get("auto_rolls_limit", 0)
    client.auto_rolls_in_key_mode = preset_data.get("auto_rolls_in_key_mode", False)
    client.auto_rolls_only_claim_hour = preset_data.get(
        "auto_rolls_only_claim_hour", False
    )
    client.rolls_item_used_count = 0
    client.rolls_used_this_interval_utc = None
    client.panic_roll_minutes = (
        preset_data.get("panic_roll_minutes", 5)
        if preset_data.get("panic_roll_minutes") is not None
        else 5
    )
    client.lurker_mode = preset_data.get("lurker_mode", False)
    client.auto_rt_after_claim = preset_data.get("auto_rt_after_claim", False)

    # Claim thresholds and round overrides
    client.time_rolls_to_claim_reset = preset_data.get(
        "time_rolls_to_claim_reset", False
    )
    client.rt_ignore_min_kakera_for_wishlist = preset_data.get(
        "rt_ignore_min_kakera_for_wishlist", False
    )
    client.rt_only_self_rolls = preset_data.get("rt_only_self_rolls", False)

    reactive_kakera_delay_range = preset_data.get("reactive_kakera_delay_range")
    if (
        reactive_kakera_delay_range
        and isinstance(reactive_kakera_delay_range, (list, tuple))
        and len(reactive_kakera_delay_range) == 2
    ):
        client.reactive_kakera_delay_range = (
            float(reactive_kakera_delay_range[0]),
            float(reactive_kakera_delay_range[1]),
        )
    else:
        client.reactive_kakera_delay_range = (0.3, 1.0)

    client.auto_p_enabled = preset_data.get("auto_p_enabled", True)
    client.enable_hybrid_panic_claim = preset_data.get(
        "enable_hybrid_panic_claim", False
    )
    client.hybrid_panic_instant_claim_min_kakera = int(
        preset_data.get("hybrid_panic_instant_claim_min_kakera", 300) or 300
    )
    client.hybrid_panic_instant_claim_max_rank = int(
        preset_data.get("hybrid_panic_instant_claim_max_rank", 200) or 200
    )
    client.claim_rounds_thresholds = preset_data.get("claim_rounds_thresholds") or []

    # Reactions and priority lists
    client.randomized_claim_reactions = preset_data.get(
        "randomized_claim_reactions"
    ) or ["💖", "💗", "💘", "❤️", "👍", "🔥"]
    client.main_account_id = str(preset_data.get("main_account_id") or "").strip()
    client.scheduled_roll_times = preset_data.get("scheduled_roll_times") or []
    client.kakera_priority_order = preset_data.get("kakera_priority_order") or [
        "kakeraP",
        "kakeraC",
        "kakeraL",
        "kakeraW",
        "kakeraR",
        "kakeraO",
        "kakeraD",
        "kakeraY",
        "kakeraG",
        "kakeraT",
        "kakera",
    ]

    client.claim_emojis = (
        preset_data.get("claim_emojis")
        if preset_data.get("claim_emojis") is not None
        else claim_emojis
    )
    client.kakera_emojis = (
        preset_data.get("kakera_emojis")
        if preset_data.get("kakera_emojis") is not None
        else kakera_emojis
    )
    client.chaos_emojis = (
        preset_data.get("chaos_emojis")
        if preset_data.get("chaos_emojis") is not None
        else list(client.kakera_emojis)
    )
    client.sphere_perk_emojis = (
        preset_data.get("sphere_perk_emojis")
        if preset_data.get("sphere_perk_emojis") is not None
        else list(client.kakera_emojis)
    )
    client.mk_kakera_emojis = (
        preset_data.get("mk_kakera_emojis")
        if preset_data.get("mk_kakera_emojis") is not None
        else list(client.kakera_emojis)
    )
    client.sphere_emojis = sphere_emojis

    # Sphere games
    sphere_click_targets = (
        ["spG", "spY", "spO", "spR", "spW", "spL", "spD", "spM", "spU"]
        if preset_data.get("sphere_click_targets") is None
        else preset_data.get("sphere_click_targets")
    )
    client.sphere_click_targets = {
        normalize_character_sphere_emoji(target).casefold()
        for target in sphere_click_targets
        if str(target or "").strip()
    }
    client.immediate_kakera_click = preset_data.get("immediate_kakera_click", True)
    client.collect_purple_kakera = bool(
        preset_data.get("collect_purple_kakera", True)
    )
    client.auto_oh_enabled = bool(preset_data.get("auto_oh_enabled", False))
    client.auto_oc_enabled = bool(preset_data.get("auto_oc_enabled", False))
    client.oh_use_individually = bool(preset_data.get("oh_use_individually", False))
    client.oh_priority_order = [
        str(item).strip()
        for item in preset_data.get("oh_priority_order") or []
        if str(item).strip()
    ]
    client.oh_unknown_explore_clicks = max(
        0, int(preset_data.get("oh_unknown_explore_clicks", 3) or 0)
    )
    client.oc_reward_priority_order = [
        str(item).strip()
        for item in preset_data.get("oc_reward_priority_order") or []
        if str(item).strip()
    ]
    client.oc_collect_after_red = bool(
        preset_data.get("oc_collect_after_red", True)
    )
    client.sphere_game_counts = {"oh": 0, "oc": 0, "oq": 0, "ot": 0}
    client.sphere_button_budget = SphereButtonBudget()
    client._sphere_quota_recheck_requested = False
    client.sphere_game_refill_at_utc = None
    client._pre_roll_status_required = False
    client._pre_roll_status_cycle_id = None
    client._pre_roll_status_requested_at = None
    client._sphere_game_lock = None
    client._kakera_action_lock = None
    client._sphere_game_response_future = None
    client._sphere_game_response_channel_id = None
    client._sphere_game_response_kind = None
    client._sphere_game_bonus_clicks = 0
    client._sphere_game_bonus_event = None
    client._sphere_game_bonus_counts = {}
    client._sphere_game_retry_after = {"oh": 0.0, "oc": 0.0}
    client._sphere_board_update_events = {}
    client._kakera_power_reconcile_handle = None

    # Chat reactions for snipes
    client.enable_snipe_chat_reactions = preset_data.get(
        "enable_snipe_chat_reactions", False
    )
    client.snipe_chat_messages = preset_data.get("snipe_chat_messages") or [
        "omg",
        "ezz",
    ]
    client.enable_kakera_snipe_chat_reactions = bool(
        preset_data.get("enable_kakera_snipe_chat_reactions", False)
    )
    client.kakera_snipe_chat_messages = preset_data.get(
        "kakera_snipe_chat_messages"
    ) or ["nice", "free kakera"]

    # Kakera farm / forcedivorce settings
    configured_farm_characters = list(preset_data.get("farm_characters") or [])
    farm_character_preset = preset_data.get("farm_character", "")
    if farm_character_preset:
        configured_farm_characters.insert(0, farm_character_preset)
    client.farm_characters = []
    seen_farm_characters = set()
    for farm_name in configured_farm_characters:
        cleaned_farm_name = str(farm_name or "").strip()
        normalized_farm_name = cleaned_farm_name.casefold()
        if cleaned_farm_name and normalized_farm_name not in seen_farm_characters:
            seen_farm_characters.add(normalized_farm_name)
            client.farm_characters.append(cleaned_farm_name)
    client.farm_character = client.farm_characters[0] if client.farm_characters else ""
    farm_character_enabled = preset_data.get("farm_character_enabled", False)
    client.farm_character_enabled = farm_character_enabled
    client.farm_forcedivorce_after_claim = bool(
        preset_data.get("farm_forcedivorce_after_claim", False)
    )
    client.farm_forcedivorce_before_roll = bool(
        preset_data.get(
            "farm_forcedivorce_before_roll",
            bool(farm_character_enabled)
            and not preset_data.get("farm_forcedivorce_after_claim", False)
            and not preset_data.get("farm_forcedivorce_after_other_claim", False),
        )
    )
    client.farm_forcedivorce_after_other_claim = bool(
        preset_data.get("farm_forcedivorce_after_other_claim", False)
    )
    client.forcedivorce_channel = None
    client._farm_release_recent = {}
    client._farm_release_lock = None
    client.op_perk_5_only = preset_data.get("op_perk_5_only", False)
    client.auto_divorce_protect_wishes = bool(
        preset_data.get("auto_divorce_protect_wishes", True)
    )
    client.wish_starwish_kakera_only = bool(
        preset_data.get("wish_starwish_kakera_only", False)
    )

    # Auto divorce
    client.auto_divorce_enabled = preset_data.get("auto_divorce_enabled", False)
    client.auto_divorce_max_kakera = (
        preset_data.get("auto_divorce_max_kakera", 50)
        if preset_data.get("auto_divorce_max_kakera") is not None
        else 50
    )
    client.auto_divorce_series = [
        s.lower().strip()
        for s in (preset_data.get("auto_divorce_series") or [])
        if s.strip()
    ]
    client.auto_divorce_blacklist = set(
        c.lower().strip()
        for c in (preset_data.get("auto_divorce_blacklist") or [])
        if c.strip()
    )
    client.auto_divorce_blacklist_series = [
        s.lower().strip()
        for s in (preset_data.get("auto_divorce_blacklist_series") or [])
        if s.strip()
    ]
    client.mk_bypass_power_check = preset_data.get("mk_bypass_power_check", False)

    # Reset / status anchors and intervals
    client.next_claim_reset_at_utc = None
    client.roll_reset_at_utc = None
    client.claim_cooldown_until_utc = None
    client.is_claiming = False
    client.snipe_watch = {}
    client.snipe_watch_expiry_seconds = 180
    client.snipe_globally_disabled_until = None

    client.claim_interval = preset_data.get("claim_interval", 180) or 180
    client.roll_interval = preset_data.get("roll_interval", 60) or 60
    if (
        preset_data.get("server_reset_minute") is not None
        and str(preset_data.get("server_reset_minute")).strip() != ""
    ):
        try:
            client.server_reset_minute = int(preset_data.get("server_reset_minute"))
        except (TypeError, ValueError):
            client.server_reset_minute = None
    else:
        client.server_reset_minute = None

    client.roll_reset_anchor = ResetAnchor(
        "roll", client.roll_interval, authoritative_minute=client.server_reset_minute
    )
    client.claim_reset_anchor = ResetAnchor("claim", client.claim_interval)
    if client.server_reset_minute is not None:
        init_anchor_now = datetime.datetime.now(timezone.utc)
        client.roll_reset_anchor.advance_through(init_anchor_now)
        client.roll_reset_at_utc = client.roll_reset_anchor.next_boundary_at_utc
        client.current_roll_cycle_id = client.roll_reset_anchor.cycle_id_for_boundary(
            client.roll_reset_anchor.next_boundary_index - 1
        )
    else:
        client.current_roll_cycle_id = None
    client.current_claim_cycle_id = None
    client.normal_roll_replenishment_capacity = None
    client.normal_roll_replenishment_capacity_confidence = False
    client._normal_roll_cycle_state = {}
    client._pending_boundary_roll_origins = {}
    client.rolls_used_cycle_id = None
    client._rolls_item_limit_cycle_id = None
    client._predicted_roll_action_handle = None
    client._predicted_roll_action_cycle_id = None
    client._normal_roll_action_roll_counts = {}
    client._active_normal_roll_cycle_id = None
    client._active_normal_batch_remaining = 0
    client._normal_roll_action_scheduled_triggers = set()
    client._last_automation_roll_command_token = None
    client._normal_roll_handoff_from_cycle_id = None
    client._normal_roll_handoff_to_cycle_id = None
    client._normal_roll_handoff_boundary_utc = None
    client._local_boundary_wake_pending = False
    client.predicted_roll_state_valid = False
    client.predicted_roll_cycle_id = None
    client.cross_cycle_roll_count_uncertain = False
    client.cross_cycle_uncertain_cycle_id = None
    client._manual_roll_sync_at_utc = None
    client._sanity_sync_at_utc = None

    # Runtime ledgers and correlators
    client.kakera_power_ledger = KakeraPowerLedger()
    client.kakera_interaction_ledger = KakeraInteractionLedger()
    client._mudae_command_ack_waiters = {}
    client._recent_mudae_command_acks = {}
    client._rt_command_in_flight = None
    client._manual_rt_pending_claims = []
    client._manual_rt_timeout_handle = None
    client._daily_rolls_claim_wake_handle = None
    client._daily_rolls_claim_wake_at_utc = None
    client._daily_rolls_claim_hour_until_utc = None
    client._daily_rolls_observed_claim_reset_utc = None
    client._rolls_item_limit_reset_at_utc = None
    client._rolls_ack_retry_after = 0.0
    client._auto_rolls_ack_ambiguous_cycle_id = None
    client._auto_rolls_reconcile_cycle_id = None
    client._deferred_independent_known_work = False
    client._normal_roll_transaction_cycle_id = None
    client._normal_roll_deferred_until_utc = None
    client._normal_roll_deferred_cycle_id = None
    client._confirmed_kakera_c_bonus_until = 0.0
    client._confirmed_kakera_c_discount_until = 0.0
    client._confirmed_kakera_c_discount_channel_id = None
    client.collected_kakera_rolls = []
    client._pending_mk_roll = None
    client._mk_roll_generation = 0
    client._classified_mk_roll_messages = {}
    client.roll_command_correlation = RollCommandCorrelation()
    client.roll_action_timing = RollActionTiming()
    client.normal_roll_action_owner = NormalRollActionOwner(client.roll_action_timing)

    # Claim state and counters
    client.current_min_kakera_for_roll_claim = client.min_kakera
    client.is_actively_rolling = False
    client._roll_batch_deferred_status_fields = set()
    client.active_cycle_id = 0
    client.tu_lock = None
    client.interrupt_rolling = False
    client._roll_interrupt_reason = None
    client.sniped_messages = set()
    client.snipe_happened = False
    client.series_sniped_messages = set()
    client.series_snipe_happened = False
    client.kakera_value_sniped_messages = set()
    client.rt_available = False
    client.rt_available_at_utc = None
    client.processed_claim_messages = set()
    client._rt_failed_message_ids = set()
    client.claim_retry_counts = {}
    client.last_successfully_claimed_character = None
    client._has_initialized = False
    client._main_loop_task = None
    client._immediate_check_event = None
    client._runtime_state_event = None
    client.scheduled_roll_due = False
    client.pending_claim = None
    client._claim_evidence_event = None
    client._claim_text_evidence = None
    client._claim_reset_refresh_requested = False
    client._status_cycle_not_before_monotonic = 0.0
    client._shared_reset_observed_at_utc = None
    client._shared_claim_reset_handle = None
    client._snipe_claim_refresh_reset_at_utc = None
    client._snipe_claim_refresh_at_utc = None
    client._snipe_claim_refresh_completed_for = None

    # Power / US / DK state
    client.current_dk_power = None
    client.dk_power_revision = 0
    client._us_lock = None
    client._us_in_flight = False
    client._us_pending_amount = 0
    client._us_retry_after = 0.0
    client.us_failed_this_cycle = False
    client.dk_consumption = 35
    client._kakera_result_waiters = {}

    # Slash-roll state
    client.slash_fallback_active = False
    client.slash_retry_at = 0.0
    client.mudae_slash_cache = {}
    client.mudae_slash_missing = set()
    client.mudae_session_id = None
    client.slash_fail_streak = 0
    client.slash_fail_threshold = 3
    client.slash_min_interval = (
        max(1.0, float(client.roll_speed)) if client.roll_speed else 1.0
    )
    client.slash_max_backoff = 6.0
    client.last_slash_attempt = 0.0
    client.slash_rate_limited_until = 0.0

    # Misc flags and logging
    client.p_available = False
    client.next_p_claim_at_utc = None
    client.key_limit_hit = False
    client.is_timing_mode_active = False
    client.kakera_power_thresholds = preset_data.get("kakera_power_thresholds") or {}
    client.debug_mode = preset_data.get("debug_mode", False)
    client.debug_log_categories = {
        str(item).strip().casefold()
        for item in preset_data.get("debug_log_categories") or ["all"]
        if str(item).strip()
    }
    client.webhook_url = str(preset_data.get("webhook_url") or "").strip()
    client.webhook_log_types = {
        str(item).strip().upper()
        for item in preset_data.get("webhook_log_types")
        or ["ERROR", "WARN", "CLAIM", "KAKERA"]
        if str(item).strip()
    }
    client.persistent_stagger_seconds = max(
        0.0, float(preset_data.get("persistent_stagger_seconds", 0) or 0.0)
    )

    # Status tracking (last; depends on intervals above)
    client.last_tu_query_utc = None
    client._tu_timing_deadline_utc = None
    initialize_status_tracking(client)
    client.last_tu_snapshot_complete = False
    client._tu_response_future = None
    client._tu_response_channel_id = None
    client._tu_request_started_at = None
    client._local_extra_rolls_pending = 0
    client.rolls_left = 0
    client._claim_reset_rolls_pending = False
    client._roll_count_sync_cycle_id = None
    client._roll_count_sync_at_utc = None
    client._roll_count_sync_handle = None
    client._roll_count_sync_requested_cycle_id = None
    client._roll_count_reconcile_cycle_id = None
    client._roll_count_reconcile_started_at_utc = None
    client._schedule_private_roll_count_sync = None
    client._advance_predicted_reset_cycles = None
    client._rolls_sent = 0
    client._rolls_received = 0
    client.collected_rolls = []
