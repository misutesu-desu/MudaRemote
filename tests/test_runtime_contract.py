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
        self.assertIn('revealed != "spP"', board_source)
        self.assertIn("for click_attempt in range(2)", board_source)
        self.assertIn("_sphere_board_update_events", board_source)
        self.assertIn("collecting bonus spheres", board_source)
        self.assertIn('status.available_for("oc")', available_source)

    def test_unknown_control_commands_are_ignored_without_tracebacks(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        handler_source = ast.get_source_segment(self.source, functions["on_command_error"])
        self.assertIn("commands.CommandNotFound", handler_source)
        self.assertIn("return", handler_source)

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
        self.assertLess(
            helper_source.index('f"{client.mudae_prefix}forcedivorce {char_name}"'),
            helper_source.index('guarded_send(channel, "y")'),
        )
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
