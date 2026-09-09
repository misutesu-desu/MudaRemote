import unittest

from mudae_core.versioning import (
    CURRENT_VERSION,
    compare_versions,
    get_update_manifest_url,
    get_update_manifest_urls,
    is_newer_version,
    is_prerelease,
    load_update_channel_setting,
    resolve_update_channel,
    save_update_channel_setting,
    ReleaseDiscoveryError,
    fetch_available_releases,
    fetch_manifest_for_version,
)


class VersioningTests(unittest.TestCase):
    def test_numeric_segments_are_not_compared_lexically(self):
        self.assertGreater(compare_versions("4.10.0", "4.9.9"), 0)

    def test_prerelease_precedes_final_release(self):
        self.assertTrue(is_newer_version("5.0.0", "5.0.0-rc1"))
        self.assertFalse(is_newer_version("5.0.0-rc1", "5.0.0"))

    def test_optional_v_prefix_and_missing_segments(self):
        self.assertEqual(compare_versions("v4.6", "4.6.0"), 0)

    def test_is_prerelease_detects_beta_alpha_rc(self):
        self.assertTrue(is_prerelease("4.9.1-beta.2"))
        self.assertTrue(is_prerelease("5.0.0-rc1"))
        self.assertTrue(is_prerelease("1.0.0a1"))
        self.assertFalse(is_prerelease("4.8.10"))
        self.assertFalse(is_prerelease("4.9.0"))
        self.assertTrue(is_prerelease())  # default is CURRENT_VERSION (4.9.1-beta.2)

    def test_resolve_update_channel(self):
        import os
        import tempfile
        # Empty base path keeps the test hermetic: a real settings.json in the
        # working tree must not leak a saved channel into default resolution.
        with tempfile.TemporaryDirectory() as base:
            # Default from CURRENT_VERSION (beta)
            self.assertEqual(resolve_update_channel(base_path=base), "beta")
            # Stable version defaults to main
            self.assertEqual(resolve_update_channel(current_version="4.8.10", base_path=base), "main")
        # Explicit argument overrides
        self.assertEqual(resolve_update_channel(channel="main"), "main")
        self.assertEqual(resolve_update_channel(channel="stable"), "main")
        self.assertEqual(resolve_update_channel(channel="beta"), "beta")
        # Environment variable override
        try:
            os.environ["MUDAREMOTE_UPDATE_CHANNEL"] = "main"
            self.assertEqual(resolve_update_channel(), "main")
            os.environ["MUDAREMOTE_UPDATE_CHANNEL"] = "beta"
            self.assertEqual(resolve_update_channel(current_version="4.8.10"), "beta")
        finally:
            os.environ.pop("MUDAREMOTE_UPDATE_CHANNEL", None)

    def test_get_update_manifest_urls(self):
        beta_urls = get_update_manifest_urls("beta")
        self.assertEqual(len(beta_urls), 3)
        self.assertIn("/beta/", beta_urls[0])
        self.assertIn("/main/", beta_urls[1])

        main_urls = get_update_manifest_urls("main")
        self.assertEqual(len(main_urls), 2)
        self.assertIn("/main/", main_urls[0])
        self.assertEqual(get_update_manifest_url("main"), main_urls[0])

    def test_load_and_save_update_channel_setting(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            # Initially none saved
            self.assertIsNone(load_update_channel_setting(td))
            self.assertEqual(resolve_update_channel(base_path=td), "beta")

            # Toggle beta off -> saves "main"
            saved = save_update_channel_setting("main", base_path=td)
            self.assertEqual(saved, "main")
            self.assertEqual(load_update_channel_setting(td), "main")
            self.assertEqual(resolve_update_channel(base_path=td), "main")

            # Toggle beta on -> saves "beta"
            saved = save_update_channel_setting("beta", base_path=td)
            self.assertEqual(saved, "beta")
            self.assertEqual(load_update_channel_setting(td), "beta")
            self.assertEqual(resolve_update_channel(base_path=td), "beta")


def _release(tag, prerelease=False, assets=()):
    return {
        "tag_name": tag,
        "name": "MudaRemote {}".format(tag),
        "prerelease": prerelease,
        "assets": [{"name": name, "browser_download_url": url} for name, url in assets],
        "published_at": "2026-01-01T00:00:00Z",
    }


class _FakeResponse:
    def __init__(self, payload, link="", error=None):
        self._payload = payload
        self.headers = {"Link": link}
        self._error = error

    def raise_for_status(self):
        if self._error:
            raise RuntimeError(self._error)

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, timeout=None, headers=None):
        self.calls.append(url)
        response = self.routes.get(url)
        if response is None:
            raise RuntimeError("unrouted request: " + url)
        return response


class FetchAvailableReleasesTests(unittest.TestCase):
    PAGE_ONE = "https://api.github.com/repos/misutesu-desu/MudaRemote/releases?per_page=100&page=1"
    PAGE_TWO = "https://api.github.com/repos/misutesu-desu/MudaRemote/releases?per_page=100&page=2"

    def test_pagination_survives_android_rows_on_the_first_page(self):
        page_one = [_release("android-pre{}".format(i), prerelease=True) for i in range(97)]
        page_one += [_release("v4.9.1-beta.4", prerelease=True), _release("v4.9.0"), _release("v4.9.0-beta.21", prerelease=True)]
        page_two = [_release("v4.9.0-beta.1", prerelease=True), _release("v4.8.10")]
        session = _FakeSession({
            self.PAGE_ONE: _FakeResponse(page_one, link='<{}>; rel="next"'.format(self.PAGE_TWO)),
            self.PAGE_TWO: _FakeResponse(page_two),
        })
        releases = fetch_available_releases(session=session, platform="pc", channel="beta")
        tags = [r["tag"] for r in releases]
        self.assertIn("v4.9.0-beta.1", tags)
        self.assertIn("v4.8.10", tags)
        self.assertEqual([t for t in tags if t.startswith("android-")], [])
        self.assertEqual(session.calls, [self.PAGE_ONE, self.PAGE_TWO])

    def test_channel_filters_prereleases(self):
        releases_page = [_release("v4.9.1-beta.4", prerelease=True), _release("v4.9.0")]
        session = _FakeSession({self.PAGE_ONE: _FakeResponse(releases_page)})
        stable = fetch_available_releases(session=session, platform="pc", channel="main")
        self.assertEqual([r["tag"] for r in stable], ["v4.9.0"])
        beta = fetch_available_releases(session=session, platform="pc", channel="beta")
        self.assertEqual([r["tag"] for r in beta], ["v4.9.1-beta.4", "v4.9.0"])

    def test_apk_asset_url_is_preserved(self):
        page = [_release("android-pre9", prerelease=True, assets=[("Mudaremote.apk", "https://example.com/Mudaremote.apk")])]
        session = _FakeSession({self.PAGE_ONE: _FakeResponse(page)})
        releases = fetch_available_releases(session=session, platform="android", channel="beta")
        self.assertEqual(releases[0]["apk_url"], "https://example.com/Mudaremote.apk")
        self.assertTrue(releases[0]["is_apk"])

    def test_failure_raises_instead_of_fabricating_releases(self):
        class _Boom:
            def get(self, url, **kwargs):
                raise OSError("simulated network failure")

        with self.assertRaises(ReleaseDiscoveryError) as ctx:
            fetch_available_releases(session=_Boom(), platform="pc", channel="beta")
        self.assertNotIn("v4.9.1-beta.3", str(ctx.exception))

    def test_http_error_status_raises(self):
        session = _FakeSession({self.PAGE_ONE: _FakeResponse(None, error="HTTP 403 rate limited")})
        with self.assertRaises(ReleaseDiscoveryError):
            fetch_available_releases(session=session, platform="pc")

    def test_malformed_body_raises(self):
        session = _FakeSession({self.PAGE_ONE: _FakeResponse({"message": "not a list"})})
        with self.assertRaises(ReleaseDiscoveryError):
            fetch_available_releases(session=session, platform="pc")

    def test_empty_catalog_is_an_empty_list(self):
        session = _FakeSession({self.PAGE_ONE: _FakeResponse([])})
        self.assertEqual(fetch_available_releases(session=session, platform="pc", channel="beta"), [])

    def test_duplicate_tags_are_deduplicated(self):
        page = [_release("v4.9.0"), _release("v4.9.0")]
        session = _FakeSession({self.PAGE_ONE: _FakeResponse(page)})
        releases = fetch_available_releases(session=session, platform="pc")
        self.assertEqual([r["tag"] for r in releases], ["v4.9.0"])


class ManifestTargetResolutionTests(unittest.TestCase):
    @staticmethod
    def _manifest_url(ref):
        from mudae_core.versioning import MANIFEST_REF_URL_TEMPLATE
        return MANIFEST_REF_URL_TEMPLATE.format(ref=ref)

    def _routes(self, ok_refs):
        routes = {}
        for ref in ok_refs:
            routes[self._manifest_url(ref)] = _FakeResponse({"version": "4.9.1-beta.5" if ref == "beta" else "4.9.0"})
        return routes

    def test_latest_honours_the_selected_channel(self):
        session = _FakeSession(self._routes(["main"]))
        data = fetch_manifest_for_version(session, "latest", channel="main")

        self.assertEqual(data["version"], "4.9.0")
        self.assertEqual(session.calls, [self._manifest_url("main")])

        session = _FakeSession(self._routes(["beta"]))
        data = fetch_manifest_for_version(session, "latest", channel="beta")
        self.assertEqual(data["version"], "4.9.1-beta.5")
        self.assertEqual(session.calls, [self._manifest_url("beta")])

    def test_exact_tag_is_used_verbatim(self):
        routes = {self._manifest_url("v4.9.1-beta.4"): _FakeResponse({"version": "4.9.1-beta.4"})}
        session = _FakeSession(routes)
        data = fetch_manifest_for_version(session, "v4.9.1-beta.4")
        self.assertEqual(data["version"], "4.9.1-beta.4")
        self.assertEqual(session.calls, [self._manifest_url("v4.9.1-beta.4")])

    def test_bare_version_falls_back_to_v_prefix(self):
        routes = {self._manifest_url("v4.9.0"): _FakeResponse({"version": "4.9.0"})}
        session = _FakeSession(routes)
        data = fetch_manifest_for_version(session, "4.9.0")
        self.assertEqual(data["version"], "4.9.0")
        self.assertEqual(session.calls, [self._manifest_url("4.9.0"), self._manifest_url("v4.9.0")])

    def test_branch_name_is_tried_verbatim_before_v_prefix(self):
        routes = {self._manifest_url("hotfix-branch"): _FakeResponse({"version": "4.9.2"})}
        session = _FakeSession(routes)
        data = fetch_manifest_for_version(session, "hotfix-branch")
        self.assertEqual(data["version"], "4.9.2")
        self.assertEqual(session.calls, [self._manifest_url("hotfix-branch")])

    def test_unknown_target_raises_after_every_candidate(self):
        session = _FakeSession({})
        with self.assertRaises(ReleaseDiscoveryError):
            fetch_manifest_for_version(session, "v9.9.9")

    def test_invalid_manifest_shape_raises(self):
        routes = {self._manifest_url("v5.0.0"): _FakeResponse({"nope": True})}
        session = _FakeSession(routes)
        with self.assertRaises(ReleaseDiscoveryError):
            fetch_manifest_for_version(session, "v5.0.0")

    def test_terminal_full_page_without_next_link_is_a_complete_catalog(self):
        base = "https://api.github.com/repos/misutesu-desu/MudaRemote/releases"
        routes = {}
        for p in range(1, 11):
            page = [_release("v2.{}.{}".format(p, i), prerelease=True) for i in range(100)]
            link = '<{}?per_page=100&page={}>; rel="next"'.format(base, p + 1) if p < 10 else ""
            routes["{}?per_page=100&page={}".format(base, p)] = _FakeResponse(page, link=link)
        releases = fetch_available_releases(session=_FakeSession(routes), platform="pc", channel="beta")
        self.assertEqual(len(releases), 1000)

    def test_history_beyond_the_page_limit_raises_instead_of_truncating(self):
        base = "https://api.github.com/repos/misutesu-desu/MudaRemote/releases"
        routes = {}
        for p in range(1, 11):
            page = [_release("v3.{}.{}".format(p, i), prerelease=True) for i in range(100)]
            link = '<{}?per_page=100&page={}>; rel="next"'.format(base, p + 1)
            routes["{}?per_page=100&page={}".format(base, p)] = _FakeResponse(page, link=link)
        with self.assertRaises(ReleaseDiscoveryError):
            fetch_available_releases(session=_FakeSession(routes), platform="pc", channel="beta")
    def test_tagged_manifest_source_urls_are_pinned_to_the_tag(self):
        manifest = {
            "version": "4.9.0",
            "download_url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/beta/mudae_bot.py",
            "source_files": [
                {"path": "mudae_bot.py", "url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/beta/mudae_bot.py", "sha256": "x"},
                {"path": "exe", "url": "https://github.com/misutesu-desu/MudaRemote/releases/download/v4.9.0/MudaRemote.exe", "sha256": "y"},
            ],
        }
        routes = {self._manifest_url("v4.9.0"): _FakeResponse(manifest)}
        session = _FakeSession(routes)
        data = fetch_manifest_for_version(session, "v4.9.0")
        pinned = "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/v4.9.0/"
        self.assertEqual(data["source_files"][0]["url"], pinned + "mudae_bot.py")
        self.assertEqual(data["download_url"], pinned + "mudae_bot.py")
        self.assertEqual(
            data["source_files"][1]["url"],
            "https://github.com/misutesu-desu/MudaRemote/releases/download/v4.9.0/MudaRemote.exe",
        )

    def test_branch_manifests_keep_branch_urls(self):
        manifest = {
            "version": "4.9.1-beta.4",
            "source_files": [
                {"path": "mudae_bot.py", "url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/beta/mudae_bot.py", "sha256": "x"},
            ],
        }
        routes = {self._manifest_url("beta"): _FakeResponse(manifest)}
        session = _FakeSession(routes)
        data = fetch_manifest_for_version(session, "beta")
        self.assertTrue(data["source_files"][0]["url"].endswith("/beta/mudae_bot.py"))


class TargetReleaseIntegrityTests(unittest.TestCase):
    """An exact release selection must resolve to that release's own metadata."""

    @staticmethod
    def _manifest_url(ref):
        from mudae_core.versioning import MANIFEST_REF_URL_TEMPLATE
        return MANIFEST_REF_URL_TEMPLATE.format(ref=ref)

    def test_manifest_with_disagreeing_identity_is_refused(self):
        # A tag serving a manifest that names a different version would mix
        # channel-head metadata into a historical install; refuse it outright.
        routes = {self._manifest_url("v4.6.4"): _FakeResponse({"version": "4.9.0"})}
        session = _FakeSession(routes)
        with self.assertRaises(ReleaseDiscoveryError) as ctx:
            fetch_manifest_for_version(session, "v4.6.4")
        self.assertIn("identifies itself as version '4.9.0'", str(ctx.exception))

    def test_bare_version_skips_mismatched_ref_and_uses_the_real_tag(self):
        routes = {
            self._manifest_url("4.6.4"): _FakeResponse({"version": "4.9.0"}),
            self._manifest_url("v4.6.4"): _FakeResponse({"version": "4.6.4"}),
        }
        session = _FakeSession(routes)
        data = fetch_manifest_for_version(session, "4.6.4")
        self.assertEqual(data["version"], "4.6.4")
        self.assertEqual(session.calls, [self._manifest_url("4.6.4"), self._manifest_url("v4.6.4")])

    def test_every_candidate_mismatched_surfaces_the_identity_error(self):
        routes = {
            self._manifest_url("4.6.4"): _FakeResponse({"version": "4.9.0"}),
            self._manifest_url("v4.6.4"): _FakeResponse({"version": "4.9.0"}),
        }
        session = _FakeSession(routes)
        with self.assertRaises(ReleaseDiscoveryError) as ctx:
            fetch_manifest_for_version(session, "4.6.4")
        self.assertIn("identifies itself as version", str(ctx.exception))

    def test_historical_manifest_releases_latest_exe_url_is_pinned_to_the_tag(self):
        # Reproduction of the v4.6.4 incident: that published manifest points
        # its executable at the mutable /releases/latest alias, so the pinned
        # historical checksum was compared against a NEWER release's bytes.
        manifest = {
            "version": "4.6.4",
            "exe_download_url": "https://github.com/misutesu-desu/MudaRemote/releases/latest/download/MudaRemote.exe",
            "exe_sha256": "d5b6b900cc1f73a880ae1c8efc8a45d472a1fc8e1a45858d40f82999af517132",
        }
        routes = {self._manifest_url("v4.6.4"): _FakeResponse(manifest)}
        session = _FakeSession(routes)
        data = fetch_manifest_for_version(session, "v4.6.4")
        self.assertEqual(
            data["exe_download_url"],
            "https://github.com/misutesu-desu/MudaRemote/releases/download/v4.6.4/MudaRemote.exe",
        )
        self.assertEqual(
            data["exe_sha256"],
            "d5b6b900cc1f73a880ae1c8efc8a45d472a1fc8e1a45858d40f82999af517132",
        )

    def test_exe_url_naming_a_different_explicit_release_is_refused(self):
        manifest = {
            "version": "4.6.4",
            "exe_download_url": "https://github.com/misutesu-desu/MudaRemote/releases/download/v4.9.0/MudaRemote.exe",
            "exe_sha256": "d5b6b900cc1f73a880ae1c8efc8a45d472a1fc8e1a45858d40f82999af517132",
        }
        routes = {self._manifest_url("v4.6.4"): _FakeResponse(manifest)}
        session = _FakeSession(routes)
        with self.assertRaises(ReleaseDiscoveryError) as ctx:
            fetch_manifest_for_version(session, "v4.6.4")
        self.assertIn("points its executable at release 'v4.9.0'", str(ctx.exception))

    def test_channel_head_manifests_keep_mutable_urls(self):
        # The 'beta'/'main' aliases ARE the channel head; no identity check and
        # no pinning may rewrite their mutable artifacts.
        manifest = {
            "version": "4.9.1-beta.5",
            "exe_download_url": "https://github.com/misutesu-desu/MudaRemote/releases/latest/download/MudaRemote.exe",
        }
        routes = {self._manifest_url("beta"): _FakeResponse(manifest)}
        session = _FakeSession(routes)
        data = fetch_manifest_for_version(session, "beta")
        self.assertTrue(data["exe_download_url"].endswith("/releases/latest/download/MudaRemote.exe"))

    def test_android_release_tags_are_not_pc_version_checked(self):
        # Android tracks have their own version numbers; the historical APK
        # tag must still resolve.
        manifest = {"version": "1.2.7"}
        routes = {self._manifest_url("android-pre9"): _FakeResponse(manifest)}
        session = _FakeSession(routes)
        data = fetch_manifest_for_version(session, "android-pre9")
        self.assertEqual(data["version"], "1.2.7")



if __name__ == "__main__":
    unittest.main()
