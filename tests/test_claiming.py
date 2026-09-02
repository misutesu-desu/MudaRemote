import datetime
import unittest

from mudae_core.claiming import (
    ClaimOutcome,
    basic_panic_claim_fallback_is_active,
    can_spend_restore_on_character,
    classify_claim_owner,
    classify_claim_text,
    cooldown_deadline,
    has_free_claim_button,
    is_claim_announcement_for_character,
)


class _Style:
    def __init__(self, value):
        self.value = value


class _Emoji:
    def __init__(self, name):
        self.name = name


class _Button:
    def __init__(self, emoji, style):
        self.emoji = _Emoji(emoji)
        self.style = _Style(style)


class _Row:
    def __init__(self, *children):
        self.children = children


class ClaimingTests(unittest.TestCase):
    def test_green_heart_button_is_a_free_claim(self):
        self.assertTrue(has_free_claim_button([_Row(_Button("heart", 3))], ["heart"]))

    def test_non_green_or_non_claim_button_is_not_a_free_claim(self):
        self.assertFalse(has_free_claim_button([_Row(_Button("heart", 1))], ["heart"]))
        self.assertFalse(has_free_claim_button([_Row(_Button("kakeraP", 3))], ["heart"]))

    def test_standard_confirmation_recognizes_username(self):
        evidence = classify_claim_text(
            "**Maliss** and **Satella** are now married!",
            "Satella",
            ["maliss", "Maliss Display"],
            user_id=123,
        )
        self.assertEqual(evidence.outcome, ClaimOutcome.SUCCESS)

    def test_hyperlink_confirmation_recognizes_display_name(self):
        evidence = classify_claim_text(
            "[Maliss Display](https://example.invalid/u) claimed [Shoko Ieiri](https://example.invalid/c)",
            "Shoko Ieiri",
            ["maliss", "Maliss Display"],
        )
        self.assertEqual(evidence.outcome, ClaimOutcome.SUCCESS)

    def test_confirmation_recognizes_discord_mention(self):
        evidence = classify_claim_text(
            "<@123> claimed **Satella**",
            "Satella",
            ["renamed-user"],
            user_id=123,
        )
        self.assertEqual(evidence.outcome, ClaimOutcome.SUCCESS)

    def test_other_winner_is_failure(self):
        evidence = classify_claim_text(
            "**Someone Else** and **Satella** are now married!",
            "Satella",
            ["maliss"],
        )
        self.assertEqual(evidence.outcome, ClaimOutcome.FAILURE)
        self.assertEqual(evidence.winner, "Someone Else")

    def test_claim_announcement_detection_excludes_forcedivorce_prompts(self):
        self.assertTrue(is_claim_announcement_for_character(
            "**Someone Else** and **Yoruichi Shihoin** are now married!",
            "Yoruichi Shihoin",
        ))
        self.assertFalse(is_claim_announcement_for_character(
            "Makima belongs to someone else, do you want to force the divorce?",
            "Makima",
        ))

    def test_unrelated_text_stays_inconclusive(self):
        evidence = classify_claim_text("You have 13 rolls left", "Satella", ["maliss"])
        self.assertEqual(evidence.outcome, ClaimOutcome.INCONCLUSIVE)

    def test_character_name_equal_to_display_name_is_not_false_success(self):
        evidence = classify_claim_text("**Someone Else** and **Satella** are now married!", "Satella", ["Satella"])
        self.assertEqual(evidence.outcome, ClaimOutcome.FAILURE)

    def test_edited_embed_owner_is_authoritative(self):
        self.assertEqual(
            classify_claim_owner("Maliss Display", ["maliss", "Maliss Display"]).outcome,
            ClaimOutcome.SUCCESS,
        )
        self.assertEqual(
            classify_claim_owner("Someone Else", ["maliss"]).outcome,
            ClaimOutcome.FAILURE,
        )

    def test_cooldown_deadline_does_not_truncate_seconds(self):
        now = datetime.datetime(2026, 7, 13, 14, 52, 51, tzinfo=datetime.timezone.utc)
        deadline = cooldown_deadline(now, 42)
        self.assertEqual(deadline, datetime.datetime(2026, 7, 13, 15, 34, 53, tzinfo=datetime.timezone.utc))

    def test_restore_keeps_the_base_value_floor_for_panic_only_candidates(self):
        self.assertFalse(can_spend_restore_on_character(55, 700, False, False))
        self.assertFalse(can_spend_restore_on_character(55, 700, True, False))
        self.assertTrue(can_spend_restore_on_character(55, 700, True, True))
        self.assertTrue(can_spend_restore_on_character(700, 700, False, False))

    def test_basic_panic_fallback_is_limited_to_an_enabled_final_round_with_claim_right(self):
        now = datetime.datetime(2026, 9, 2, 12, tzinfo=datetime.timezone.utc)
        self.assertTrue(basic_panic_claim_fallback_is_active(
            enabled=True,
            claim_right_available=True,
            next_claim_reset_at_utc=now + datetime.timedelta(minutes=30),
            now_utc=now,
        ))
        self.assertFalse(basic_panic_claim_fallback_is_active(
            enabled=True,
            claim_right_available=True,
            next_claim_reset_at_utc=now + datetime.timedelta(minutes=61),
            now_utc=now,
        ))
        self.assertFalse(basic_panic_claim_fallback_is_active(
            enabled=False,
            claim_right_available=True,
            next_claim_reset_at_utc=now + datetime.timedelta(minutes=30),
            now_utc=now,
        ))
        self.assertFalse(basic_panic_claim_fallback_is_active(
            enabled=True,
            claim_right_available=False,
            next_claim_reset_at_utc=now + datetime.timedelta(minutes=30),
            now_utc=now,
        ))


if __name__ == "__main__":
    unittest.main()
