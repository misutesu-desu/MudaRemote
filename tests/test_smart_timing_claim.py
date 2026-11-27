"""Smart Timing must not keep rolling once the fresh claim has been used."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from mudae_core.runtime import can_resume_claim_interrupted_rolls


def _finalize_claim_branch():
    source = (Path(__file__).resolve().parents[1] / "mudae_bot.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "finalize_successful_claim":
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.If)
                    and isinstance(child.test, ast.Name)
                    and child.test.id == "consumes_claim"
                ):
                    return child
    raise AssertionError("consumes_claim branch of finalize_successful_claim not found")


class SmartTimingAfterClaimTests(unittest.TestCase):
    def test_used_claim_turns_timing_mode_off(self):
        branch = _finalize_claim_branch()
        cleared = False
        for stmt in branch.body:
            if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
                continue
            target = stmt.targets[0]
            if (
                isinstance(target, ast.Attribute)
                and target.attr == "is_timing_mode_active"
                and isinstance(target.value, ast.Name)
                and target.value.id == "client"
                and isinstance(stmt.value, ast.Constant)
                and stmt.value.value is False
            ):
                cleared = True
        self.assertTrue(cleared)

    def test_rolls_do_not_resume_after_timed_claim_is_used(self):
        client = SimpleNamespace(
            rolling_enabled=True,
            is_paused=False,
            key_limit_hit=False,
            pending_claim=None,
            rolls_left=12,
            key_mode=False,
            claim_right_available=False,
            rt_available=False,
            is_timing_mode_active=False,
        )
        self.assertFalse(can_resume_claim_interrupted_rolls(client))


if __name__ == "__main__":
    unittest.main()
