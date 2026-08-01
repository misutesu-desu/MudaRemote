import ast
import os
import unittest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _AutomationCallVisitor(ast.NodeVisitor):
    def __init__(self):
        self.function_stack = []
        self.calls = []

    def visit_AsyncFunctionDef(self, node):
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_Await(self, node):
        call = node.value
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute):
            if call.func.attr in {"send", "click", "add_reaction"}:
                self.calls.append((self.function_stack[-1] if self.function_stack else None, call.func.attr, node.lineno))
        self.generic_visit(node)


class RuntimeSourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.path.join(PROJECT_ROOT, "mudae_bot.py")
        with open(path, "r", encoding="utf-8") as handle:
            cls.source = handle.read()
            cls.tree = ast.parse(cls.source, filename=path)

    def test_external_automation_actions_use_pause_guards(self):
        visitor = _AutomationCallVisitor()
        visitor.visit(self.tree)
        allowed = {
            ("guarded_send", "send"),
            ("guarded_click", "click"),
            ("guarded_reaction", "add_reaction"),
        }
        unguarded = [call for call in visitor.calls if call[:2] not in allowed]
        self.assertEqual(unguarded, [])

    def test_active_roll_loops_reference_pause_state(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        for function_name in ("start_roll_commands", "process_mk_rolls"):
            node = functions[function_name]
            pause_checks = [
                child for child in ast.walk(node)
                if isinstance(child, ast.Attribute) and child.attr == "is_paused"
            ]
            self.assertTrue(pause_checks, function_name)

    def test_tu_response_retry_budget_is_two_commands(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        check_status = functions["check_status"]
        retry_loops = []
        for node in ast.walk(check_status):
            if not isinstance(node, ast.For):
                continue
            sends_tu = any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "send_tu_command"
                for child in ast.walk(node)
            )
            if sends_tu:
                retry_loops.append(node)
        self.assertEqual(len(retry_loops), 1)
        iterator = retry_loops[0].iter
        self.assertIsInstance(iterator, ast.Call)
        self.assertIsInstance(iterator.func, ast.Name)
        self.assertEqual(iterator.func.id, "range")
        self.assertEqual(iterator.args[0].value, 2)

    def test_authoritative_cooldown_refreshes_claim_and_rt_before_retry(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        cooldown_handler = functions["process_claim_cooldown_message"]
        called_names = {
            child.func.id
            for child in ast.walk(cooldown_handler)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
        }
        self.assertIn("wake_status_loop", called_names)
        self.assertIn("request_status_refresh", called_names)

    def test_explicit_localized_claim_denial_overrides_ready_substring(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        status_source = ast.get_source_segment(self.source, functions["check_status"])
        self.assertIn(
            "explicit_claim_cooldown = parse_claim_denied_cooldown(c_lower)",
            status_source,
        )
        self.assertIn(
            "explicit_claim_cooldown is None\n"
            "                and re.search(REGEX_PATTERNS[\"CLAIM_READY\"], c_lower)",
            status_source,
        )

    def test_tu_snapshot_does_not_trigger_another_status_refresh(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        cooldown_source = ast.get_source_segment(
            self.source,
            functions["process_claim_cooldown_message"],
        )
        snapshot_guard = cooldown_source.index("if is_tu_status_snapshot_for_self(message)")
        refresh_call = cooldown_source.index("request_status_refresh")
        self.assertLess(snapshot_guard, refresh_call)

    def test_exact_extra_roll_message_uses_local_state_without_tu(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        on_message = functions["on_message"]
        extra_roll_branches = []
        for node in ast.walk(on_message):
            if not isinstance(node, ast.If):
                continue
            references_extra_rolls = any(
                isinstance(child, ast.Name) and child.id == "m_bonus"
                for child in ast.walk(node.test)
            )
            if references_extra_rolls:
                extra_roll_branches.append(node)
        self.assertEqual(len(extra_roll_branches), 1)
        called_names = {
            child.func.id
            for child in ast.walk(extra_roll_branches[0])
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
        }
        self.assertIn("wake_status_loop", called_names)
        self.assertNotIn("request_status_refresh", called_names)
        self.assertNotIn("mark_status_dirty", called_names)

    def test_tu_response_is_captured_before_channel_filter_returns(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        on_message = functions["on_message"]
        capture_calls = [
            child for child in ast.walk(on_message)
            if isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "capture_tu_response"
        ]
        returns = [child for child in ast.walk(on_message) if isinstance(child, ast.Return)]
        self.assertEqual(len(capture_calls), 1)
        self.assertLess(capture_calls[0].lineno, min(node.lineno for node in returns))

    def test_sphere_game_response_is_captured_before_channel_filter_returns(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        on_message = functions["on_message"]
        capture_calls = [
            child for child in ast.walk(on_message)
            if isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "capture_sphere_game_response"
        ]
        returns = [child for child in ast.walk(on_message) if isinstance(child, ast.Return)]
        self.assertEqual(len(capture_calls), 1)
        self.assertLess(capture_calls[0].lineno, min(node.lineno for node in returns))

    def test_separate_sphere_bonus_message_is_captured_before_channel_filter_returns(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        on_message = functions["on_message"]
        capture_calls = [
            child for child in ast.walk(on_message)
            if isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "capture_sphere_game_bonus"
        ]
        returns = [child for child in ast.walk(on_message) if isinstance(child, ast.Return)]
        self.assertEqual(len(capture_calls), 1)
        self.assertLess(capture_calls[0].lineno, min(node.lineno for node in returns))

    def test_sphere_game_automation_uses_tu_counts_and_guarded_actions(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        status_source = ast.get_source_segment(self.source, functions["check_status"])
        game_source = ast.get_source_segment(self.source, functions["run_sphere_game"])
        available_source = ast.get_source_segment(self.source, functions["run_available_sphere_games"])
        board_source = ast.get_source_segment(self.source, functions["play_sphere_game"])
        self.assertIn("parse_sphere_game_status(tu_content)", status_source)
        self.assertIn("await run_available_sphere_games", status_source)
        self.assertIn("await guarded_send", game_source)
        self.assertIn("if client._sphere_game_lock is None", game_source)
        self.assertIn("client._sphere_game_lock = asyncio.Lock()", game_source)
        self.assertIn("await guarded_click", board_source)
        self.assertIn("revealed = normalize_sphere_emoji", board_source)
        self.assertIn("not harvest_reveal_is_free(revealed)", board_source)
        self.assertIn("_sphere_game_bonus_clicks", board_source)
        self.assertIn("await asyncio.wait_for(bonus_event.wait()", board_source)
        self.assertIn("for click_attempt in range(2)", board_source)
        self.assertIn("_sphere_board_update_events", board_source)
        self.assertIn("collecting bonus spheres", board_source)
        self.assertIn('status.available_for("oc")', available_source)
        self.assertIn("split_command_batches(available, 10)", available_source)
        self.assertIn("remaining -= batch_size", available_source)

    def test_localized_sphere_boards_do_not_require_english_text(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        kind_source = ast.get_source_segment(self.source, functions["sphere_game_kind"])
        capture_source = ast.get_source_segment(
            self.source,
            functions["capture_sphere_game_response"],
        )
        recent_source = ast.get_source_segment(
            self.source,
            functions["find_recent_sphere_game"],
        )
        self.assertIn('command_name in {"oh", "oc"}', kind_source)
        self.assertIn("len(buttons) != 25", capture_source)
        self.assertIn('expected_kind not in {"oh", "oc"}', capture_source)
        self.assertIn("sphere_game_kind(candidate) in (None, kind)", recent_source)

    def test_points_cooldown_schedules_a_fresh_status_check(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        schedule_source = ast.get_source_segment(
            self.source,
            functions["schedule_points_refresh"],
        )
        status_source = ast.get_source_segment(self.source, functions["check_status"])
        self.assertIn("client.loop.call_later", schedule_source)
        self.assertIn('{"points"}', schedule_source)
        self.assertIn('"p-reset"', schedule_source)
        self.assertIn('"$p está pronto"', status_source)
        self.assertGreaterEqual(
            status_source.count("schedule_points_refresh(client.next_p_claim_at_utc)"),
            2,
        )

    def test_series_claims_can_be_limited_to_self_owned_rolls(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        matcher_source = ast.get_source_segment(self.source, functions["series_wishlist_matches"])
        handler_source = ast.get_source_segment(self.source, functions["on_message"])
        self.assertIn("client.series_snipe_only_self_rolls", matcher_source)
        self.assertIn("await detect_roll_owner", matcher_source)
        self.assertIn("known_self_roll=is_manual_self_roll", handler_source)

    def test_unknown_control_commands_are_ignored_without_tracebacks(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        handler_source = ast.get_source_segment(self.source, functions["on_command_error"])
        self.assertIn("commands.CommandNotFound", handler_source)
        self.assertIn("return", handler_source)

    def test_updates_show_changelog_and_require_confirmation_before_apply(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        update_source = ast.get_source_segment(self.source, functions["check_for_updates"])
        self.assertIn("format_update_changelog(data)", update_source)
        self.assertIn("confirmation(latest_version, changelog)", update_source)
        self.assertLess(
            update_source.index("confirmation(latest_version, changelog)"),
            update_source.index("apply_update("),
        )

    def test_login_failure_stops_with_concise_actionable_message(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.FunctionDef)
        }
        wrapper_source = ast.get_source_segment(self.source, functions["bot_lifecycle_wrapper"])
        login_branch = wrapper_source.index('isinstance(e, getattr(discord, "LoginFailure", ()))')
        crash_log = wrapper_source.index('print_log(f"Instance crashed:')
        self.assertLess(login_branch, crash_log)
        self.assertIn("401 Unauthorized", wrapper_source)
        self.assertIn("Re-enter the current token", wrapper_source)

    def test_farm_divorce_timings_can_be_enabled_independently(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        start_source = ast.get_source_segment(self.source, functions["start_roll_commands"])
        finalize_source = ast.get_source_segment(self.source, functions["finalize_successful_claim"])
        self.assertIn("client.farm_forcedivorce_before_roll", start_source)
        self.assertNotIn("not client.farm_forcedivorce_after_claim", start_source)
        self.assertIn("after verified claim (configured timing)", finalize_source)
        self.assertIn("await execute_farm_forcedivorce", finalize_source)
        self.assertIn(
            "farm_character_claimed and consumes_claim and client.auto_rt_after_claim and client.rt_available",
            finalize_source,
        )

    def test_rejected_claim_is_only_released_when_it_can_be_retried(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        resolve_source = ast.get_source_segment(
            self.source,
            functions["resolve_pending_claim_from_status"],
        )
        retry_guard = (
            "if message_id is not None and retry_count < 1 "
            "and can_retry and not client.is_paused:"
        )
        self.assertIn(retry_guard, resolve_source)
        self.assertGreater(
            resolve_source.index("client.processed_claim_messages.discard(message_id)"),
            resolve_source.index(retry_guard),
        )
        self.assertLess(
            resolve_source.index("client.processed_claim_messages.discard(message_id)"),
            resolve_source.index("elif not can_retry:"),
        )

    def test_text_and_slash_commands_share_the_same_pacer(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        for function_name in ("guarded_send", "_trigger_mudae_slash"):
            called_names = {
                child.func.id
                for child in ast.walk(functions[function_name])
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
            }
            self.assertIn("paced_mudae_action", called_names, function_name)

    def test_mk_rolls_use_the_slash_aware_command_path(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        mk_source = ast.get_source_segment(self.source, functions["process_mk_rolls"])
        self.assertIn('await send_roll_command(channel, "mk")', mk_source)
        self.assertNotIn('guarded_send(channel, f"{client.mudae_prefix}mk")', mk_source)

    def test_cross_account_farm_release_is_independently_optional(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        handler_source = ast.get_source_segment(self.source, functions["on_message"])
        self.assertIn("client.farm_forcedivorce_after_other_claim", handler_source)
        self.assertIn("is_claim_announcement_for_character", handler_source)
        self.assertIn("farm_claim_evidence.outcome != ClaimOutcome.SUCCESS", handler_source)

    def test_initial_status_check_includes_automated_account_stagger(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        ready_source = ast.get_source_segment(self.source, functions["on_ready"])
        self.assertIn('getattr(client, "persistent_stagger_seconds", 0)', ready_source)
        self.assertIn(
            "total_start_delay = manual_start_delay + automated_startup_stagger",
            ready_source,
        )
        self.assertIn(
            "pause_interruptible_sleep(client, total_start_delay + random.uniform(0.1, 0.5))",
            ready_source,
        )
        self.assertLess(
            ready_source.index("pause_interruptible_sleep(client, total_start_delay"),
            ready_source.index("main_status_loop(client, channel)"),
        )

    def test_stagger_offset_is_supplied_by_the_active_launcher_set(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.FunctionDef)
        }
        run_source = ast.get_source_segment(self.source, functions["run_bot"])
        launcher_source = ast.get_source_segment(self.source, functions["start_active_preset_threads"])

        self.assertIn("persistent_stagger_seconds_preset", run_source)
        self.assertNotIn("sorted(list(presets.keys()))", run_source)
        self.assertIn("prepare_active_presets", launcher_source)

    def test_kakera_and_character_actions_do_not_share_processed_message_lock(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        claim_source = ast.get_source_segment(self.source, functions["claim_character"])
        self.assertIn(
            "if not is_kakera and msg.id in client.processed_claim_messages",
            claim_source,
        )
        self.assertIn(
            "if not is_kakera:\n            # Check lock and register",
            claim_source,
        )

    def test_kakera_threshold_check_and_click_are_serialized_per_client(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        lock_source = ast.get_source_segment(self.source, functions["get_kakera_action_lock"])
        self.assertIn("if client._kakera_action_lock is None", lock_source)
        self.assertIn("client._kakera_action_lock = asyncio.Lock()", lock_source)

        for function_name in ("start_roll_commands", "claim_character"):
            lock_blocks = []
            for node in ast.walk(functions[function_name]):
                if not isinstance(node, ast.AsyncWith):
                    continue
                for item in node.items:
                    context = item.context_expr
                    if (
                        isinstance(context, ast.Call)
                        and isinstance(context.func, ast.Name)
                        and context.func.id == "get_kakera_action_lock"
                    ):
                        lock_blocks.append(node)
                        break

            self.assertEqual(len(lock_blocks), 1, function_name)
            block_source = ast.get_source_segment(self.source, lock_blocks[0])
            ordered_actions = (
                "current_pow = get_current_dk_power()",
                "threshold = first_configured",
                "await guarded_click(btn)",
                "client.current_dk_power = max(0, get_current_dk_power() - cost)",
            )
            positions = [block_source.index(action) for action in ordered_actions]
            self.assertEqual(positions, sorted(positions), function_name)

    def test_external_kakera_clicks_reconcile_estimated_power(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        reconcile_source = ast.get_source_segment(
            self.source,
            functions["schedule_external_kakera_power_reconcile"],
        )
        claim_source = ast.get_source_segment(self.source, functions["claim_character"])

        self.assertIn('reason="external-kakera-result-reconcile"', reconcile_source)
        self.assertIn("client.loop.call_later(5.0, reconcile)", reconcile_source)
        self.assertIn("if is_snipe:\n                                    schedule_external_kakera_power_reconcile()", claim_source)
        self.assertIn("Estimated Pw", claim_source)

    def test_kakera_snipe_channels_do_not_require_character_sniping(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        handler_source = ast.get_source_segment(self.source, functions["on_message"])
        self.assertIn("is_kakera_snipe_channel", handler_source)
        self.assertIn(
            "not (is_roll or is_snipe or is_kakera_snipe_channel)",
            handler_source,
        )

    def test_op5_filter_requires_the_authoritative_sp_marker(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        claim_source = ast.get_source_segment(self.source, functions["claim_character"])
        op5_start = claim_source.index("if client.op_perk_5_only:")
        op5_end = claim_source.index("if client.mk_only", op5_start)
        op5_source = claim_source[op5_start:op5_end]

        self.assertIn("if not has_op5:", op5_source)
        self.assertNotIn("has_free", op5_source)
        self.assertNotIn('any(f"sp"', op5_source)
        self.assertIn("has_op5 = has_op_perk_five_marker(embed.description)", claim_source)
        self.assertIn("has_sp_perk = has_perk_eight_discount(embed.description)", claim_source)

    def test_mudae_button_artwork_is_cached_for_the_preset_editor(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        cache_source = ast.get_source_segment(self.source, functions["cache_mudae_emoji_asset"])
        schedule_source = ast.get_source_segment(self.source, functions["schedule_mudae_emoji_asset_cache"])
        handler_source = ast.get_source_segment(self.source, functions["on_message"])

        self.assertIn("MUDAE_EMOJI_ASSET_DIR", cache_source)
        self.assertIn("cdn.discordapp.com/emojis", cache_source)
        self.assertIn("cache_mudae_emoji_asset", schedule_source)
        self.assertIn("schedule_mudae_emoji_asset_cache(client, message)", handler_source)

    def test_kakera_collection_is_not_limited_to_three_buttons(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        claim_source = ast.get_source_segment(self.source, functions["claim_character"])
        roll_source = ast.get_source_segment(self.source, functions["start_roll_commands"])

        self.assertNotIn("max_clicks = 3", claim_source)
        self.assertNotIn("clicks_per_message", roll_source)
        self.assertIn("if match_custom or match_pos:", claim_source)

    def test_idle_manual_self_rolls_use_reactive_claiming(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        handler_source = ast.get_source_segment(self.source, functions["on_message"])
        self.assertIn("is_manual_self_roll", handler_source)
        self.assertIn("client.enable_reactive_self_snipe", handler_source)
        self.assertIn("is_external_snipe=False", handler_source)
        self.assertIn("Manual Self-Roll Claim", handler_source)

    def test_claim_cooldown_rejection_is_retried_after_rt_status_refresh(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        cooldown_source = ast.get_source_segment(self.source, functions["process_claim_cooldown_message"])
        resolve_source = ast.get_source_segment(self.source, functions["resolve_pending_claim_from_status"])
        self.assertIn('pending["rejected_by_cooldown"] = True', cooldown_source)
        self.assertIn('request_status_refresh({"claim", "rt"}', cooldown_source)
        self.assertNotIn("resolve_pending_claim_from_status(False", cooldown_source)
        self.assertIn("rejected_by_cooldown", resolve_source)
        self.assertIn("client.rt_available", resolve_source)

    def test_green_claim_button_is_handled_before_normal_claim_filters(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        handler_source = ast.get_source_segment(self.source, functions["on_message"])
        free_index = handler_source.index("has_free_claim_button(message.components")
        active_roll_index = handler_source.index(
            "if client.rolling_enabled and client.is_actively_rolling",
            free_index,
        )
        self.assertLess(free_index, active_roll_index)
        self.assertIn("is_free_claim=True", handler_source[free_index:active_roll_index])

    def test_farm_forcedivorce_sends_confirmation_through_guarded_queue(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        helper = functions["execute_farm_forcedivorce"]
        guarded_arguments = [
            child.args[1]
            for child in ast.walk(helper)
            if isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "guarded_send"
            and len(child.args) > 1
        ]
        self.assertTrue(
            any(isinstance(argument, ast.Constant) and argument.value == "y" for argument in guarded_arguments)
        )
        helper_source = ast.get_source_segment(self.source, helper)
        self.assertIn("channel = _get_forcedivorce_channel(channel)", helper_source)
        self.assertLess(
            helper_source.index('f"{client.mudae_prefix}forcedivorce {char_name}"'),
            helper_source.index('guarded_send(channel, "y")'),
        )
        confirmation_index = helper_source.index("Confirmed forcedivorce")
        guard_clear_index = helper_source.index(
            "client.last_successfully_claimed_character = None"
        )
        self.assertGreater(guard_clear_index, confirmation_index)
        direct_sends = [
            child
            for child in ast.walk(helper)
            if isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "send"
        ]
        self.assertEqual(direct_sends, [])


if __name__ == "__main__":
    unittest.main()
