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

    def test_authoritative_cooldown_wakes_without_requesting_tu(self):
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
        self.assertIn("clear_status_dirty", called_names)
        self.assertIn("wake_status_loop", called_names)
        self.assertNotIn("request_status_refresh", called_names)

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

    def test_farm_forcedivorce_never_sends_a_bare_confirmation(self):
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
        self.assertFalse(
            any(isinstance(argument, ast.Constant) and argument.value == "y" for argument in guarded_arguments)
        )


if __name__ == "__main__":
    unittest.main()
