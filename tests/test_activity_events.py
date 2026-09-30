"""Activity events: real bot log lines become structured events; technical lines stay out of the feed."""

import os
import unittest

from mudae_core.activity_events import ActivityClassifier

SOURCE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mudae_bot.py")


def one(classifier, level, message):
    events = classifier.classify(level, message)
    assert len(events) == 1, events
    return events[0]


class ActivityEventTests(unittest.TestCase):
    def test_a_successful_claim_is_an_event_with_the_character_and_the_attempt_kakera(self):
        c = ActivityClassifier()
        assert one(c, "CLAIM", "Claim attempt: Rem (350 ka)")[0] == "claim_attempt"
        kind, data = one(c, "CLAIM", "Claim Verification: SUCCESS! We got Rem. (message edit)")
        assert kind == "claim" and data["character"] == "Rem" and data["kakera"] == 350 and data["snipe"] is False
        assert data["message"] == "Claimed Rem (350 ka)" and data["source"] == "message edit"
        kind, data = one(c, "CLAIM", "Snipe Verification: SUCCESS! We got Emilia (Re:Zero). (reaction)")
        assert kind == "claim" and data["character"] == "Emilia (Re:Zero)" and data["snipe"] is True and data["kakera"] is None
        assert data["message"] == "Sniped Emilia (Re:Zero)"


    def test_missed_claims_attempts_by_reaction_and_names_with_parentheses(self):
        c = ActivityClassifier()
        kind, data = one(c, "CLAIM", "Claiming Ram (Re:Zero) (1,250 ka) (Reaction: \U0001F496)")
        assert kind == "claim_attempt" and data["character"] == "Ram (Re:Zero)" and data["kakera"] == 1250
        kind, data = one(c, "WARN", "Claim Verification: FAILED. Ram (Re:Zero) was not claimed; claim right is still ready.")
        assert kind == "claim_failed" and data["character"] == "Ram (Re:Zero)" and data["kakera"] == 1250
        assert one(c, "INFO", "Claim attempt: Nobody")[1]["kakera"] is None


    def test_rolls_kakera_divorce_and_wishlist_moments(self):
        c = ActivityClassifier()
        assert one(c, "INFO", "Rolling 10 times (Reactive)") == ("roll", {"rolls": 10, "message": "Rolling 10 times"})
        assert one(c, "INFO", "Rolling 1 times")[1]["message"] == "Rolling 1 time"
        kind, data = one(c, "KAKERA", "Kakera click sent: Rem [kakeraP] (Estimated Pw: 72%)")
        assert kind == "kakera" and data["character"] == "Rem" and data["kakera_type"] == "kakeraP"
        kind, data = one(c, "KAKERA", "Auto-Divorce: Divorced Old Character (+25 kakera)")
        assert kind == "divorce" and data["kakera"] == 25 and data["message"] == "Released Old Character (25 ka)"
        assert one(c, "CLAIM", "Wish detected on edited roll: Rem. Checking claim.")[0] == "wishlist"
        assert one(c, "CLAIM", "Main Account Sync (wished by Main): Rem! Priority claiming.")[1]["character"] == "Rem"
        kind, data = one(c, "KAKERA", "Gained +2 extra rolls from Kakera! rolls_left is now 5.")
        assert kind == "kakera" and data["bonus_rolls"] == 2
        assert one(c, "KAKERA", "DK: Activating. (40% < 50%)")[0] == "kakera"            # kakera-level fallback


    def test_technical_lines_no_longer_become_kakera_or_claim_events(self):
        c = ActivityClassifier()
        for level, line in (
            ("INFO", "Claim Thresholds: Base Min Kakera: 175 | Active Round: 3/3 | Effective Min Kakera: 175"),
            ("INFO", "Reset soon (24m). Ignoring Min Kakera."),
            ("CLAIM", "Manual $rt acknowledged; character claims are available again."),
            ("CLAIM", "Smart Timing: Saved Rem for claim at reset."),
            ("CLAIM", "Auto $rt: Sending $rt after claiming Rem."),
            ("INFO", "Scheduled roll mode active. Times: ['10:00']"),
            ("ERROR", "anything at error level is the runtime's job"),
        ):
            assert c.classify(level, line) == [], line
        assert one(c, "RESET", "Timing rolls for claim reset within the safe roll window. Waiting 3.0m.")[0] == "roll_reset"


    def test_the_patterns_still_match_the_wording_in_the_bot(self):
        """If someone rewords these log lines in mudae_bot.py the feed would go quiet again: fail loudly instead."""
        with open(SOURCE, encoding="utf-8") as handle:
            source = handle.read()
        for fragment in ('lbl = "Snipe Verification" if is_snipe_action else "Claim Verification"',
                         '{lbl}: SUCCESS! We got {char_name}. ({verification_source})',
                         "Claim Verification: FAILED. {pending['character_name']} was not claimed",
                         'Claim attempt: {char_name}{kakera_str}', 'Claiming {char_name}{kakera_str} (Reaction: {reaction_emoji})',
                         'Rolling {rolls_left} times', 'Kakera click sent: {char_name} [{name}]',
                         'Auto-Divorce: Divorced {char_name}', 'Wish detected on edited roll: {embed.author.name}. Checking claim.',
                         'Main Account Sync (wished by Main): {c_name}!', 'Gained +{bonus_amt} extra rolls from Kakera!'):
            assert fragment in source, fragment
        assert 'kakera_str = f" ({val} ka)"' in source


    def test_odd_input_never_raises(self):
        for message in (None, "", "   ", 42):
            assert ActivityClassifier().classify("INFO", message) == [], message


if __name__ == "__main__":
    unittest.main()
