import os
import unittest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_project_file(*parts):
    with open(os.path.join(PROJECT_ROOT, *parts), "r", encoding="utf-8") as handle:
        return handle.read()


class AndroidRuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.activity = read_project_file(
            "android", "app", "src", "main", "java", "com", "mudaremote", "android", "MainActivity.kt"
        )
        cls.service = read_project_file(
            "android", "app", "src", "main", "java", "com", "mudaremote", "android", "MudaRemoteService.kt"
        )
        cls.chips = read_project_file(
            "android", "app", "src", "main", "java", "com", "mudaremote", "android", "ChipListView.kt"
        )
        cls.bridge = read_project_file("android", "app", "src", "main", "python", "android_bridge.py")

    def test_service_uses_immutable_intent_payloads_and_serial_command_execution(self):
        self.assertIn("putExtra(EXTRA_PROFILES, profilesJson)", self.service)
        self.assertIn("putExtra(EXTRA_TOKENS, tokensJson)", self.service)
        self.assertIn("Executors.newSingleThreadScheduledExecutor", self.service)
        self.assertNotIn("launchProfiles", self.service)
        self.assertNotIn("launchTokens", self.service)

    def test_service_reports_structured_bridge_outcomes_instead_of_unconditional_success(self):
        self.assertIn('"started", "added", "already-active"', self.service)
        self.assertIn('"no-runnable-profiles"', self.service)
        self.assertIn('"stopping"', self.service)
        self.assertNotIn("Foreground service started successfully", self.service)

    def test_account_tokens_are_masked_and_have_an_explicit_remove_action(self):
        self.assertIn('private val isSensitive = key == "tokens"', self.chips)
        self.assertIn('text = if (isSensitive) "Remove"', self.chips)
        self.assertIn('minHeight = UiTheme.dp(context, 48)', self.chips)
        self.assertIn('visibility = if (isSensitive) GONE else VISIBLE', self.chips)
        self.assertIn("maskedTokenLabel(item)", self.chips)

    def test_profile_share_and_runtime_staging_strip_all_token_fields(self):
        self.assertIn('exportJson.remove("token")', self.activity)
        self.assertIn('exportJson.remove("tokens")', self.activity)
        self.assertIn('exportJson.remove("additional_tokens")', self.activity)
        self.assertIn('data.pop("token", None)', self.bridge)
        self.assertIn('data.pop("tokens", None)', self.bridge)
        self.assertIn('data.pop("additional_tokens", None)', self.bridge)

    def test_activity_preflight_accepts_canonical_multi_account_tokens(self):
        self.assertIn("allTokensForProfile", self.activity)
        self.assertIn("Selected profile(s) have no usable account token.", self.activity)
        self.assertIn("Start request sent", self.activity)
        self.assertNotIn("Foreground service started successfully", self.activity)

    def test_stop_and_sticky_restart_are_generation_scoped(self):
        self.assertIn("DESIRED_RUNNING_KEY", self.service)
        self.assertIn("lastStopStartId > startId", self.service)
        self.assertIn("scheduleWithFixedDelay", self.service)
        self.assertIn("latestCommandStartId == watchedStartId", self.service)

    def test_legacy_additional_tokens_are_migrated_and_hidden(self):
        self.assertIn("decodeAdditionalTokenValues", self.activity)
        self.assertIn('data.remove("additional_tokens")', self.activity)
        self.assertIn('it != "token" && it != "additional_tokens"', self.activity)
        self.assertIn("existingTokens = allTokensForProfile(name)", self.activity)


if __name__ == "__main__":
    unittest.main()
