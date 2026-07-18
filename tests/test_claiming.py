import datetime
import unittest

from mudae_core.claiming import (
    ClaimOutcome,
    classify_claim_owner,
    classify_claim_text,
    cooldown_deadline,
)


class ClaimingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
