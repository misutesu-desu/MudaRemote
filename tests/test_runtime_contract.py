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

    def test_target_channel_id_is_normalized_for_message_routing(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        run_bot_source = ast.get_source_segment(self.source, functions["run_bot"])
        self.assertIn("client.target_channel_id = int(target_channel_id)", run_bot_source)

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
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for function_name in ("start_roll_commands", "process_mk_rolls"):
            node = functions[function_name]
            pause_checks = [
                child for child in ast.walk(node)
                if isinstance(child, ast.Attribute) and child.attr == "is_paused"
            ]
            self.assertTrue(pause_checks, function_name)

    def test_claim_interrupt_resumes_known_rolls_without_tu_refresh(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        roll_source = ast.get_source_segment(self.source, functions["start_roll_commands"])
        message_source = ast.get_source_segment(self.source, functions["on_message"])

        self.assertIn('client._roll_interrupt_reason = "claim-attempt"', message_source)
        self.assertIn('interrupt_reason == "claim-attempt"', roll_source)
        self.assertIn("can_resume_claim_interrupted_rolls(client)", roll_source)
        self.assertIn("without $tu", roll_source)
        self.assertIn('reason="rolling-interrupted"', roll_source)

    def test_completed_normal_rolls_refresh_status_for_auto_us(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        roll_source = ast.get_source_segment(self.source, functions["start_roll_commands"])

        self.assertIn("if pending_roll_work()[1]:", roll_source)
        self.assertIn('reason="normal-rolls-complete-auto-us"', roll_source)
        self.assertIn('request_status_refresh(\n                    {"rolls"}', roll_source)
        self.assertIn('reason="normal-roll-responses-missing"', roll_source)

    def test_snipe_only_clients_ignore_shared_roll_boundaries(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        source = ast.get_source_segment(self.source, functions["_apply_shared_reset_snapshot"])
        self.assertIn('getattr(client, "rolling_enabled", False)', source)
        self.assertIn('reason="shared-roll-boundary"', source)
        self.assertIn("client.us_pulled_this_cycle = 0", source)
        self.assertIn("client.us_failed_this_cycle = False", source)

    def test_snipe_only_status_refresh_is_humanized_once_per_reset(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        loop_source = ast.get_source_segment(self.source, functions["snipe_only_status_loop"])
        self.assertIn("humanized_claim_refresh_deadline(", loop_source)
        self.assertIn("cached_reset != reset_at", loop_source)
        self.assertIn('reason="snipe-claim-reset"', loop_source)

    def test_shared_claim_boundary_does_not_interrupt_humanized_refresh(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        start = self.source.index("    def unlock_at_shared_boundary():")
        end = self.source.index("\n    loop = getattr(client, \"loop\", None)", start)
        boundary_source = self.source[start:end]
        self.assertIn('reason="shared-claim-boundary"', boundary_source)
        self.assertNotIn("event.set()", boundary_source)
        shared_reset_source = ast.get_source_segment(
            self.source,
            functions["_apply_shared_reset_snapshot"],
        )
        self.assertIn("reconcile_shared_claim_deadline(", shared_reset_source)

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

    def test_tu_commands_use_process_wide_twenty_second_pacing(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        source = ast.get_source_segment(self.source, functions["send_tu_command"])
        self.assertIn("_tu_interval_coordinator.reserve", source)
        self.assertIn("TU_GLOBAL_INTERVAL_SECONDS", source)
        self.assertIn("await active_delay(global_wait)", source)

    def test_every_tu_send_waits_for_inactive_hours_and_channel_quiet(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        inactivity_source = ast.get_source_segment(
            self.source,
            functions["wait_for_tu_inactivity"],
        )
        send_source = ast.get_source_segment(self.source, functions["send_tu_command"])

        self.assertIn("is_inactive_hour()", inactivity_source)
        self.assertIn("seconds_until_active()", inactivity_source)
        self.assertIn("client.humanization_inactivity_seconds", inactivity_source)
        self.assertIn("channel.history(limit=1)", inactivity_source)
        self.assertIn("TU_INACTIVITY_MAX_TOTAL_WAIT_SECONDS", inactivity_source)
        self.assertIn("sending anyway", inactivity_source)
        self.assertIn("wait_for_tu_send_window()", send_source)
        self.assertEqual(send_source.count("await wait_for_tu_send_window()"), 2)
        self.assertNotIn("await wait_for_global_tu_slot(): return False", send_source)

    def test_claim_reset_boundary_preserves_roll_for_fresh_claim_state(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        status_source = ast.get_source_segment(self.source, functions["check_status"])
        message_source = ast.get_source_segment(self.source, functions["on_message"])

        self.assertIn("_claim_reset_rolls_pending", status_source)
        self.assertIn("Processing {len(deferred_rolls)} roll(s) saved at the claim reset boundary.", status_source)
        self.assertIn("await handle_mudae_messages(", status_source)
        self.assertIn("client.collected_rolls.append(message)", message_source)
        self.assertIn('request_status_refresh({"claim"}, reason="near-claim-reset-boundary", urgent=True)', message_source)

    def test_cached_status_wait_cannot_start_duplicate_cycles(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        run_source = ast.get_source_segment(self.source, functions["run_bot"])
        status_source = ast.get_source_segment(self.source, functions["check_status"])

        self.assertIn("_status_cycle_not_before_monotonic", run_source)
        self.assertIn("_status_cycle_not_before_monotonic", status_source)
        self.assertIn("not status_dirty_fields(client)", status_source)
        self.assertIn('"Skipping $tu (using cached status)."', status_source)

    def test_humanized_reset_wait_ignores_stale_wake_events(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        wait_source = ast.get_source_segment(
            self.source,
            functions["humanized_wait_and_proceed"],
        )
        self.assertIn("deadline = time.monotonic() + wait_seconds", wait_source)
        self.assertIn("while True:", wait_source)
        self.assertIn("status_dirty_fields(client) or client.scheduled_roll_due", wait_source)

    def test_slash_interaction_success_does_not_depend_on_response_payload(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        trigger_source = ast.get_source_segment(
            self.source,
            functions["_trigger_mudae_slash"],
        )
        post_source = ast.get_source_segment(
            self.source,
            functions["post_interaction"],
        )

        self.assertIn('await client.http.request(Route("POST", "/interactions")', post_source)
        self.assertIn("return True", post_source)
        self.assertIn("paced_mudae_action(\n                post_interaction", trigger_source)
        self.assertNotIn(
            'lambda: client.http.request(Route("POST", "/interactions")',
            trigger_source,
        )

    def test_auto_us_cycle_failure_flag_is_initialized(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.FunctionDef)
        }
        source = ast.get_source_segment(self.source, functions["run_bot"])
        self.assertIn("client.us_failed_this_cycle = False", source)

    def test_roll_command_is_bound_before_message_owner_detection(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        run_source = ast.get_source_segment(self.source, functions["run_bot"])
        owner_source = ast.get_source_segment(self.source, functions["detect_roll_owner"])
        self.assertIn("client.roll_command =", run_source)
        self.assertIn('getattr(client, "roll_command", "")', owner_source)

    def test_bulk_us_requests_the_full_remaining_limit(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        status_source = ast.get_source_segment(self.source, functions["check_rolls_left_tu"])
        send_source = ast.get_source_segment(self.source, functions["send_auto_us"])
        self.assertIn("amount = remaining if client.bulk_us_enabled else min(20, remaining)", status_source)
        self.assertIn("chunks = [20] * (amount // 20)", send_source)
        self.assertIn("client._us_pending_amount = sent", send_source)
        self.assertIn("min(requested, us_rolls_left)", status_source)

    def test_auto_us_in_flight_is_released_when_normal_rolls_remain(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        status_source = ast.get_source_segment(self.source, functions["check_rolls_left_tu"])
        self.assertIn("0.0 if total_rolls > 0 else time.monotonic() + 30", status_source)
        self.assertIn(
            "Auto $us was not acknowledged while normal rolls remain",
            status_source,
        )

    def test_snipe_only_ready_claim_completes_initial_handshake(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        source = ast.get_source_segment(self.source, functions["snipe_only_status_loop"])
        self.assertIn("client.claim_right_available or client.next_claim_reset_at_utc", source)

    def test_status_treats_missing_rt_as_optional_after_warning(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        source = ast.get_source_segment(self.source, functions["check_status"])
        self.assertIn(
            'required_fields = {"claim", "rolls"} if proceed_to_rolls else {"claim"}',
            source,
        )
        self.assertIn('"rt" not in getattr(client, "_tu_missing_categories", set())', source)
        self.assertIn("required_fields - fresh_fields", source)

    def test_mk_interrupts_do_not_dirty_status_or_repeat_tu(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        source = ast.get_source_segment(self.source, functions["process_mk_rolls"])
        self.assertNotIn('reason="mk-interrupted"', source)
        self.assertNotIn('reason="mk-delay-interrupted"', source)
        self.assertNotIn('reason="mk-post-send-interrupted"', source)

    def test_free_kakera_does_not_require_known_power(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        claim_source = ast.get_source_segment(self.source, functions["claim_character"])
        self.assertIn("if cost > 0 and current_pow is None", claim_source)
        self.assertIn("if cost > 0 and current_pow < cost", claim_source)
        self.assertIn('else "unknown"', claim_source)

    def test_hybrid_panic_handles_kakera_before_deferred_claim_processing(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        source = ast.get_source_segment(self.source, functions["on_message"])
        deferred_source = ast.get_source_segment(self.source, functions["handle_mudae_messages"])
        self.assertIn("# Hybrid panic still needs real-time Kakera handling.", source)
        self.assertGreaterEqual(
            source.count("await claim_character(client, message.channel, message, is_kakera=True)"),
            2,
        )
        self.assertNotIn("k_claims", deferred_source)

    def test_auto_dk_supports_a_custom_trigger_power(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        run_source = ast.get_source_segment(self.source, functions["run_bot"])
        dk_source = ast.get_source_segment(self.source, functions["handle_dk_power_management"])
        self.assertIn("client.auto_dk_min_power", run_source)
        self.assertIn("client.auto_dk_min_power or cost", dk_source)

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

    def test_edited_sphere_bonus_is_counted_once(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        capture_source = ast.get_source_segment(self.source, functions["capture_sphere_game_bonus"])
        edit_source = ast.get_source_segment(self.source, functions["on_message_edit"])
        board_source = ast.get_source_segment(self.source, functions["play_sphere_game"])
        self.assertIn("getattr(embed, 'fields'", capture_source)
        self.assertIn("_sphere_game_bonus_counts", capture_source)
        self.assertIn("capture_sphere_game_bonus(after)", edit_source)
        self.assertIn("timeout=5.0", board_source)

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
        self.assertIn("client.oh_use_individually", available_source)
        self.assertIn("[1] * available", available_source)
        self.assertIn("remaining -= batch_size", available_source)

    def test_cached_status_sleep_is_capped_by_cache_expiry(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        status_source = ast.get_source_segment(self.source, functions["check_status"])
        wait_source = ast.get_source_segment(
            self.source,
            functions["humanized_wait_and_proceed"],
        )
        self.assertIn("tu_cache_seconds_remaining(", status_source)
        self.assertIn('"cached status refresh"', status_source)
        self.assertIn("is_cache_refresh", wait_source)
        self.assertIn("0 if is_cache_refresh", wait_source)
        self.assertIn("and not is_cache_refresh", wait_source)
        self.assertNotIn('"timing threshold" in reason.lower()', wait_source)

    def test_idle_status_wait_uses_known_reset_instead_of_thirty_minute_refresh(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        status_source = ast.get_source_segment(self.source, functions["check_status"])
        self.assertIn("known_idle_boundary = bool(", status_source)
        self.assertIn("cache_seconds_remaining > 0 or known_idle_boundary", status_source)
        self.assertIn("if not known_idle_boundary:", status_source)

    def test_shared_roll_reset_dirties_exhausted_local_roll_cache(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        shared_reset_source = ast.get_source_segment(
            self.source,
            functions["_apply_shared_reset_snapshot"],
        )
        self.assertIn("reconcile_shared_roll_deadline(", shared_reset_source)
        self.assertIn('mark_status_dirty(client, {"rolls"}', shared_reset_source)
        self.assertIn('reason="shared-roll-boundary"', shared_reset_source)
        self.assertIn("_immediate_check_event", shared_reset_source)

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

    def test_portuguese_daily_ready_text_is_supported(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        status_source = ast.get_source_segment(self.source, functions["check_status"])
        self.assertIn('"$daily está pronto"', status_source)
        self.assertIn('"$daily esta pronto"', status_source)

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

    def test_known_claim_and_rt_deadlines_enable_targets_during_long_rolls(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        refresh_source = ast.get_source_segment(
            self.source,
            functions["refresh_predicted_claim_and_rt"],
        )
        allowed_source = ast.get_source_segment(
            self.source,
            functions["is_character_snipe_allowed"],
        )
        key_source = ast.get_source_segment(
            self.source,
            functions["is_key_mode_kakera_only"],
        )
        status_source = ast.get_source_segment(self.source, functions["check_status"])
        self.assertIn("client.claim_right_available = True", refresh_source)
        self.assertIn("client.rt_available = True", refresh_source)
        self.assertIn('reason="predicted-claim-reset"', refresh_source)
        self.assertIn('reason="predicted-rt-reset"', refresh_source)
        self.assertIn("refresh_predicted_claim_and_rt()", allowed_source)
        self.assertIn("refresh_predicted_claim_and_rt()", key_source)
        self.assertIn("client.rt_available_at_utc = cooldown_deadline", status_source)

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
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        handler_source = ast.get_source_segment(
            self.source,
            functions["schedule_farm_release_after_other_claim"],
        )
        edit_source = ast.get_source_segment(self.source, functions["on_message_edit"])
        message_source = ast.get_source_segment(self.source, functions["on_message"])
        self.assertIn("client.farm_forcedivorce_after_other_claim", handler_source)
        self.assertIn("is_claim_announcement_for_character", handler_source)
        self.assertIn("farm_claim_evidence.outcome != ClaimOutcome.SUCCESS", handler_source)
        self.assertIn("classify_claim_owner", handler_source)
        self.assertIn("owner != previous_owner", handler_source)
        self.assertIn("schedule_farm_release_after_other_claim(after", edit_source)
        self.assertIn("schedule_farm_release_after_other_claim(message)", message_source)

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
                "power_token = reserve_kakera_power_click",
                "await click_kakera_with_confirmation(",
            )
            positions = [block_source.index(action) for action in ordered_actions]
            self.assertEqual(positions, sorted(positions), function_name)
            self.assertNotIn(
                "client.current_dk_power = max(0, get_current_dk_power() - cost)",
                block_source,
            )

    def test_external_kakera_click_timeouts_release_power_without_tu(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        reconcile_source = ast.get_source_segment(
            self.source,
            functions["schedule_external_kakera_power_reconcile"],
        )
        reserve_source = ast.get_source_segment(
            self.source,
            functions["reserve_kakera_power_click"],
        )
        claim_source = ast.get_source_segment(self.source, functions["claim_character"])
        message_source = ast.get_source_segment(self.source, functions["on_message"])

        self.assertIn("client.kakera_power_ledger.clear()", reconcile_source)
        self.assertIn("released reserved power without $tu", reconcile_source)
        self.assertIn("client.loop.call_later(8.0, reconcile)", reconcile_source)
        self.assertNotIn("request_status_refresh", reconcile_source)
        self.assertIn("schedule_external_kakera_power_reconcile()", reserve_source)
        self.assertIn("reserve_kakera_power_click(name, cost)", claim_source)
        self.assertIn("parse_kakera_result(", message_source)
        self.assertIn("confirm_kakera_power_click(kakera_result.emoji_name)", message_source)
        self.assertIn("Estimated Pw", claim_source)

    def test_kakera_clicks_wait_for_account_result_and_retry(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        click_source = ast.get_source_segment(
            self.source,
            functions["click_kakera_with_confirmation"],
        )
        message_source = ast.get_source_segment(self.source, functions["on_message"])
        refresh_source = ast.get_source_segment(
            self.source,
            functions["collect_refreshed_purple_after_claim"],
        )

        self.assertIn("register_kakera_result_waiter(emoji_name)", click_source)
        self.assertIn("attempt_limit = 3 if is_purple else 2", click_source)
        self.assertIn("for attempt in range(attempt_limit)", click_source)
        self.assertIn("await channel.fetch_message(msg.id)", click_source)
        self.assertIn('label = "Purple Kakera" if is_purple', click_source)
        self.assertIn('f"{label} confirmed', click_source)
        self.assertIn("is_ambiguous_component_interaction_error(error)", click_source)
        self.assertIn('reason="kakera-interaction-ambiguous"', click_source)
        self.assertIn("Power will be verified with $tu", click_source)
        self.assertGreaterEqual(
            self.source.count("await click_kakera_with_confirmation("),
            2,
        )
        self.assertIn(
            "resolve_kakera_result_waiters(kakera_result.emoji_name, kakera_result.amount)",
            message_source,
        )
        self.assertIn("for attempt in range(8)", refresh_source)

    def test_dynamic_dk_uses_estimated_power_but_waits_for_click_confirmation(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        run_source = ast.get_source_segment(self.source, functions["run_bot"])
        refill_source = ast.get_source_segment(
            self.source,
            functions["should_auto_refill_dk"],
        )
        reserve_source = ast.get_source_segment(
            self.source,
            functions["reserve_kakera_power_click"],
        )
        confirm_source = ast.get_source_segment(
            self.source,
            functions["confirm_kakera_power_click"],
        )
        status_source = ast.get_source_segment(self.source, functions["check_status"])
        claim_source = ast.get_source_segment(self.source, functions["claim_character"])
        roll_source = ast.get_source_segment(self.source, functions["start_roll_commands"])

        self.assertIn("client.kakera_power_ledger = KakeraPowerLedger()", run_source)
        self.assertIn("client.dk_power_revision = 0", run_source)
        self.assertIn(
            "power_is_confirmed=not client.kakera_power_ledger.has_pending",
            refill_source,
        )
        self.assertIn("client.kakera_power_ledger.reserve", reserve_source)
        self.assertIn("client.kakera_power_ledger.confirm", confirm_source)
        self.assertIn("client.current_dk_power = max(0, base_power - cost)", confirm_source)
        self.assertIn(
            "tu_power_revision == client.dk_power_revision",
            status_source,
        )
        self.assertIn("or tu_may_reconcile_pending_power", status_source)
        self.assertIn(
            "if power_snapshot_is_authoritative:",
            status_source,
        )
        self.assertIn("and power_snapshot_is_authoritative", status_source)
        for action_source in (claim_source, roll_source):
            self.assertIn("reserve_kakera_power_click(name, cost)", action_source)
            self.assertIn("cancel_kakera_power_click(power_token)", action_source)
            self.assertNotIn(
                "client.current_dk_power = max(0, get_current_dk_power() - cost)",
                action_source,
            )

    def test_rolls_and_rt_wait_for_mudae_reaction_ack(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        run_source = ast.get_source_segment(self.source, functions["run_bot"])
        ack_source = ast.get_source_segment(
            self.source,
            functions["send_mudae_reaction_command"],
        )
        reaction_source = ast.get_source_segment(
            self.source,
            functions["on_raw_reaction_add"],
        )
        roll_status_source = ast.get_source_segment(
            self.source,
            functions["check_rolls_left_tu"],
        )

        self.assertIn("client._mudae_command_ack_waiters = {}", run_source)
        self.assertIn("await guarded_send(channel, content)", ack_source)
        self.assertIn("asyncio.wait_for", ack_source)
        self.assertIn("mudae_command_ack_matches", reaction_source)
        self.assertIn("send_mudae_reaction_command", roll_status_source)
        self.assertIn("rolls_usage_is_active", roll_status_source)
        self.assertNotIn("rolls_used_this_interval_utc != client.roll_reset_at_utc", roll_status_source)
        self.assertIn("_last_normal_roll_count", roll_status_source)
        self.assertIn("$rolls acknowledged; continuing with", roll_status_source)
        self.assertIn("await start_roll_commands(", roll_status_source)

        rt_send_count = self.source.count(
            'send_mudae_reaction_command(channel, f"{client.mudae_prefix}rt"'
        )
        self.assertGreaterEqual(rt_send_count, 5)

    def test_failed_rt_invalidates_cached_state_and_refreshes_claim_status(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        run_source = ast.get_source_segment(self.source, functions["run_bot"])
        claim_source = ast.get_source_segment(self.source, functions["claim_character"])
        message_source = ast.get_source_segment(self.source, functions["handle_mudae_messages"])

        self.assertIn("client._rt_failed_message_ids = set()", run_source)
        self.assertIn("def invalidate_rt_after_failed_attempt", self.source)
        self.assertIn("client.rt_available = False", self.source)
        self.assertIn(
            'request_status_refresh({"claim", "rt"}, reason=reason, urgent=True)',
            self.source,
        )
        self.assertIn("invalidate_rt_after_failed_attempt(msg.id)", claim_source)
        self.assertIn('reason="rt-target-stale"', claim_source)
        self.assertIn("msg.id in failed_rt_messages", message_source)
        self.assertIn("invalidate_rt_after_failed_attempt(msg_rt.id)", message_source)

    def test_kakera_bonus_rolls_require_this_accounts_confirmed_kakera_c(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        run_source = ast.get_source_segment(self.source, functions["run_bot"])
        message_source = ast.get_source_segment(self.source, functions["on_message"])

        self.assertIn("client._confirmed_kakera_c_bonus_until = 0.0", run_source)
        self.assertIn(
            'kakera_result.emoji_name.rstrip("2").casefold() == "kakerac"',
            message_source,
        )
        self.assertIn("confirmed_cost is not None", message_source)
        self.assertIn("bonus_from_confirmed_kakera_c", message_source)
        self.assertIn("m_bonus and bonus_from_confirmed_kakera_c", message_source)
        self.assertIn("client._confirmed_kakera_c_bonus_until = 0.0", message_source)
        self.assertNotIn("bonus_addresses_self", message_source)

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

    def test_kakera_snipe_channels_are_separate_with_legacy_fallback(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        run_source = ast.get_source_segment(self.source, functions["run_bot"])
        handler_source = ast.get_source_segment(self.source, functions["on_message"])

        self.assertIn("kakera_snipe_channels_preset=None", run_source)
        self.assertIn(
            "configured_kakera_snipe_channels = kakera_snipe_channels_preset or snipe_channels_preset or []",
            run_source,
        )
        self.assertIn("message.channel.id in client.snipe_channels", handler_source)
        self.assertIn("message.channel.id in client.kakera_snipe_channels", handler_source)

    def test_op5_filter_requires_the_authoritative_sp_marker(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        claim_source = ast.get_source_segment(self.source, functions["claim_character"])
        filter_source = ast.get_source_segment(self.source, functions["regular_kakera_filter_reason"])

        self.assertIn("op5_only=client.op_perk_5_only", filter_source)
        self.assertIn("marker_text = kakera_embed_text(embed)", filter_source)
        self.assertIn("has_op5=has_op_perk_five_marker(marker_text)", filter_source)
        self.assertNotIn('any(f"sp"', filter_source)
        self.assertIn("filter_reason = regular_kakera_filter_reason", claim_source)
        self.assertIn("has_sp_perk = has_perk_eight_discount(kakera_embed_text(embed))", claim_source)

    def test_purple_kakera_bypass_is_controlled_per_preset(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        claim_source = ast.get_source_segment(self.source, functions["claim_character"])
        handler_source = ast.get_source_segment(self.source, functions["on_message"])
        helper_source = ast.get_source_segment(self.source, functions["kakera_button_is_eligible"])

        self.assertIn("client.collect_purple_kakera", claim_source)
        self.assertIn("client.collect_purple_kakera", handler_source)
        self.assertIn('if clean == "kakeraP":', helper_source)
        self.assertIn("return client.collect_purple_kakera", helper_source)
        self.assertIn("filter_reason and not has_purple_kakera and not has_targeted_sphere", claim_source)
        self.assertIn('if clean == "kakeraP":', helper_source)
        self.assertIn("return client.collect_purple_kakera", helper_source)
        self.assertIn("has_collectible_kakera_button(message.components, all_k)", handler_source)
        self.assertIn("Purple Kakera skipped: Collect Purple Kakera is disabled", handler_source)

    def test_enabled_purple_kakera_bypasses_tu_and_reaction_status(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        allowed_source = ast.get_source_segment(
            self.source,
            functions["is_kakera_reaction_allowed"],
        )
        claim_source = ast.get_source_segment(self.source, functions["claim_character"])
        roll_source = ast.get_source_segment(self.source, functions["start_roll_commands"])

        self.assertIn("is_free_purple=False", allowed_source)
        self.assertIn(
            "if is_free_purple and client.collect_purple_kakera:",
            allowed_source,
        )
        self.assertIn(
            "is_kakera_reaction_allowed(is_free_purple=has_purple_kakera)",
            claim_source,
        )
        self.assertIn("is_free_purple = name_clean == 'kakeraP'", claim_source)
        self.assertIn("is_free_purple = name.rstrip('2') == 'kakeraP'", roll_source)

    def test_kakera_cooldown_blocks_free_buttons_and_learns_from_ku(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        claim_source = ast.get_source_segment(self.source, functions["claim_character"])
        roll_source = ast.get_source_segment(self.source, functions["start_roll_commands"])
        cooldown_source = ast.get_source_segment(
            self.source,
            functions["process_kakera_reaction_cooldown_message"],
        )
        handler_source = ast.get_source_segment(self.source, functions["on_message"])

        self.assertNotIn("has_free_button", claim_source)
        self.assertIn("has_reaction_cooldown_bypass", claim_source)
        self.assertIn("reaction became unavailable before", claim_source)
        self.assertIn("reaction is on cooldown before queued", roll_source)
        self.assertIn("can't react to kakera", cooldown_source)
        self.assertIn("client.kakera_react_available = False", cooldown_source)
        self.assertIn("process_kakera_reaction_cooldown_message(message)", handler_source)

    def test_successful_claim_refreshes_the_roll_for_late_purple_kakera(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        refresh_source = ast.get_source_segment(
            self.source,
            functions["collect_refreshed_purple_after_claim"],
        )
        claim_source = ast.get_source_segment(self.source, functions["claim_character"])

        self.assertIn("await channel.fetch_message(msg.id)", refresh_source)
        self.assertIn("has_purple_kakera_button(refreshed.components)", refresh_source)
        self.assertIn("is_kakera=True", refresh_source)
        self.assertIn("is_snipe=is_snipe", refresh_source)
        self.assertGreaterEqual(
            claim_source.count("await collect_refreshed_purple_after_claim"),
            2,
        )
        self.assertGreaterEqual(
            claim_source.count("claim_outcome == ClaimOutcome.SUCCESS"),
            2,
        )

    def test_spheres_bypass_kakera_only_filters_without_unblocking_regular_kakera(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        claim_source = ast.get_source_segment(self.source, functions["claim_character"])
        sphere_source = ast.get_source_segment(self.source, functions["has_targeted_sphere_button"])
        eligibility_source = ast.get_source_segment(self.source, functions["kakera_button_is_eligible"])

        self.assertIn("has_targeted_sphere = has_targeted_sphere_button", claim_source)
        self.assertIn("filter_reason and not has_purple_kakera and not has_targeted_sphere", claim_source)
        self.assertIn("return filter_reason is None", eligibility_source)
        self.assertIn("client.sphere_click_targets", sphere_source)
        self.assertIn("sphere_target_matches", sphere_source)

    def test_megasphere_is_a_supported_default_sphere_target(self):
        self.assertIn("'spM'", self.source)
        self.assertIn('"spM", "spU"', self.source)
        self.assertIn("'spR', 'sp'", self.source)

    def test_missing_context_overrides_inherit_regular_kakera_selection(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        run_source = ast.get_source_segment(self.source, functions["run_bot"])
        self.assertIn("else list(client.kakera_emojis)", run_source)
        self.assertIn("if sphere_click_targets_preset is None", run_source)

    def test_ouroperk_eight_counts_as_half_power_for_chaos_only(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        filter_source = ast.get_source_segment(self.source, functions["regular_kakera_filter_reason"])
        self.assertIn("has_chaos_discount=chaos_count > 0", filter_source)
        self.assertIn("has_perk_eight_discount=has_perk_eight_discount(marker_text)", filter_source)

    def test_manual_self_roll_kakera_is_not_treated_as_external(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        handler_source = ast.get_source_segment(self.source, functions["on_message"])
        self.assertIn("is_snipe=not is_manual_self_roll", handler_source)
        self.assertIn("and not is_manual_self_roll", handler_source)

    def test_deferred_collection_reuses_regular_kakera_filters(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        roll_source = ast.get_source_segment(self.source, functions["start_roll_commands"])
        self.assertIn("filter_reason = regular_kakera_filter_reason", roll_source)
        self.assertIn("filter_reason is None and regular_match", roll_source)

    def test_claim_click_ack_timeout_verifies_without_duplicate_click(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        click_source = ast.get_source_segment(self.source, functions["send_claim_click"])
        claim_source = ast.get_source_segment(self.source, functions["claim_character"])
        verify_source = ast.get_source_segment(self.source, functions["verify_snipe_outcome"])

        self.assertIn("asyncio.wait_for(asyncio.shield(task)", click_source)
        self.assertIn("return True, False", click_source)
        self.assertIn("click_sent, acknowledged = await send_claim_click", claim_source)
        self.assertIn("verification_seconds = (", verify_source)
        self.assertIn("if pending.get(\"consumes_claim\")", verify_source)
        self.assertIn("else 5.0", verify_source)

    def test_ready_claim_retries_once_without_a_tu_round_trip(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        retry_source = ast.get_source_segment(
            self.source,
            functions["retry_pending_claim_from_cached_state"],
        )
        verify_source = ast.get_source_segment(self.source, functions["verify_snipe_outcome"])

        self.assertIn('or not pending.get("claim_was_available")', retry_source)
        self.assertIn("client.claim_retry_counts[message_id] = retry_count + 1", retry_source)
        self.assertIn("retry_pending_claim_after_release", retry_source)
        self.assertIn("retry_pending_claim_from_cached_state(pending, channel)", verify_source)
        self.assertIn("without $tu", verify_source)

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
        self.assertIn("find_refreshed_component_button", claim_source)
        self.assertIn("find_refreshed_component_button", roll_source)

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

    def test_panic_claim_does_not_spend_rt_on_low_value_cards(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        handler_source = ast.get_source_segment(self.source, functions["on_message"])
        self.assertGreaterEqual(handler_source.count("can_spend_restore_on_character"), 2)
        self.assertIn("client.min_kakera", handler_source)

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

    def test_manual_claim_cooldown_does_not_force_a_redundant_tu(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        cooldown_source = ast.get_source_segment(
            self.source,
            functions["process_claim_cooldown_message"],
        )
        pending_guard = cooldown_source.index('if pending and pending.get("consumes_claim"):')
        refresh_call = cooldown_source.index('request_status_refresh({"claim", "rt"}')
        authoritative_branch = cooldown_source.index("The rejection itself authoritatively locks a manual claim")
        self.assertLess(pending_guard, refresh_call)
        self.assertLess(refresh_call, authoritative_branch)

    def test_verified_claims_become_terminal_cross_account_messages(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        success_source = ast.get_source_segment(
            self.source,
            functions["finalize_successful_claim"],
        )
        verify_source = ast.get_source_segment(
            self.source,
            functions["verify_snipe_outcome"],
        )
        self.assertIn("_claim_coordinator.mark_completed", success_source)
        self.assertIn("_claim_coordinator.mark_completed", verify_source)

    def test_all_visible_tu_snapshots_feed_the_shared_server_clock(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        handler_source = ast.get_source_segment(self.source, functions["on_message"])
        observer_source = ast.get_source_segment(
            self.source,
            functions["observe_shared_tu_resets"],
        )
        self.assertIn("observe_shared_tu_resets(message)", handler_source)
        self.assertIn("looks_like_tu_status_snapshot", observer_source)
        self.assertIn("_server_reset_coordinator.observe", observer_source)

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

    def test_perk_six_free_claims_can_be_disabled_per_preset(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        handler_source = ast.get_source_segment(self.source, functions["on_message"])

        self.assertIn("client.auto_free_claim_enabled and has_free_claim_button", handler_source)
        self.assertIn("client.auto_free_claim_enabled = bool(auto_free_claim_preset)", self.source)
        self.assertIn('preset_data.get("auto_free_claim", True)', self.source)

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
        self.assertIn("str(reason or \"\").strip().casefold()", helper_source)
        self.assertIn("async with client._farm_release_lock", helper_source)
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

    def test_smart_timing_contract(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        roll_source = ast.get_source_segment(self.source, functions["start_roll_commands"])
        message_source = ast.get_source_segment(self.source, functions["on_message"])

        self.assertIn("client.is_timing_mode_active = is_timing_mode_active", roll_source)
        self.assertIn("Smart Timing: Processing {len(client.collected_rolls)} collected roll(s) at claim reset.", roll_source)
        self.assertIn("client.claim_right_available = True", roll_source)
        self.assertIn("client._claim_reset_rolls_pending = True", roll_source)
        self.assertIn("client.is_timing_mode_active = False", roll_source)
        self.assertIn("getattr(client, 'is_timing_mode_active', False)", message_source)
        self.assertIn("Smart Timing: Saved {c_name} for claim at reset.", message_source)

    def test_smart_timing_bypasses_disabled_in_timing_window(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        status_source = ast.get_source_segment(self.source, functions["check_status"])
        self.assertIn("client.time_rolls_to_claim_reset", status_source)
        self.assertIn("claim_reset_m_check <= 60.0", status_source)
        self.assertIn("can_bypass = False", status_source)

    def test_farm_forcedivorce_harem_busy_retry_contract(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        forcedivorce_source = ast.get_source_segment(self.source, functions["execute_farm_forcedivorce"])
        self.assertIn("for attempt in range(3):", forcedivorce_source)
        self.assertIn("harem", forcedivorce_source)
        self.assertIn("being processed", forcedivorce_source)

    def test_smart_timing_ignores_shared_roll_boundaries_during_cooldown(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        shared_reset_source = ast.get_source_segment(
            self.source,
            functions["_apply_shared_reset_snapshot"],
        )
        self.assertIn("timing_delay_active = bool(", shared_reset_source)
        self.assertIn("time_rolls_to_claim_reset", shared_reset_source)
        self.assertIn("not timing_delay_active", shared_reset_source)

    def test_smart_timing_sleep_prioritizes_timing_threshold(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        status_source = ast.get_source_segment(self.source, functions["check_status"])
        tu_source = ast.get_source_segment(self.source, functions["check_rolls_left_tu"])
        self.assertIn("is_timing_waiting = bool(", status_source)
        self.assertIn("is_timing_wait_bypass = bool(", status_source)
        self.assertIn("is_timing_wait_tu = bool(", tu_source)
        self.assertIn("timing threshold arrival", status_source)
        self.assertIn("timing window arrival", tu_source)

    def test_check_status_parses_rolls_count_and_roll_reset_tu(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        status_source = ast.get_source_segment(self.source, functions["check_status"])
        self.assertIn('rolls_match = re.search(REGEX_PATTERNS["ROLLS_COUNT"]', status_source)
        self.assertIn("client.rolls_left = parsed_rolls", status_source)
        self.assertIn('ROLL_RESET_TU', status_source)


if __name__ == "__main__":
    unittest.main()
