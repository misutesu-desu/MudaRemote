import asyncio
import unittest

import discord.utils

import mudae_bot


class _Response:
    def __init__(self, text):
        self._text = text

    async def text(self):
        return self._text


class _Session:
    def __init__(self, pages):
        self.pages = pages
        self.requested = []

    async def get(self, url, **kwargs):
        self.requested.append(url)
        if url not in self.pages:
            raise OSError("unreachable: " + url)
        return _Response(self.pages[url])

    async def request(self, method, url, **kwargs):
        return await self.get(url, **kwargs)


LOGIN_PAGE = (
    '<script src="/assets/web.843cc7edc28c426c.js"></script>'
    '<script src="/assets/sentry.77e23b6dcd52b017.js"></script>'
    '<script src="/assets/41814.16b66adbca89c196.js"></script>'
)


class DiscordLoginFallbackTests(unittest.TestCase):
    def test_build_number_is_read_from_the_sentry_asset(self):
        session = _Session({
            "https://discord.com/login": LOGIN_PAGE,
            "https://discord.com/assets/sentry.77e23b6dcd52b017.js": 'a.NA("buildNumber","634304"),a.NA("builtAt","1")',
        })

        build = asyncio.run(discord.utils._get_build_number(session))

        self.assertEqual(build, 634304)

    def test_unparseable_login_page_falls_back_instead_of_crashing_login(self):
        session = _Session({"https://discord.com/login": "<html>no assets here</html>"})

        build = asyncio.run(discord.utils._get_build_number(session))

        self.assertEqual(build, mudae_bot.DISCORD_FALLBACK_BUILD_NUMBER)

    def test_unreachable_discord_falls_back_instead_of_crashing_login(self):
        build = asyncio.run(discord.utils._get_build_number(_Session({})))

        self.assertEqual(build, mudae_bot.DISCORD_FALLBACK_BUILD_NUMBER)

    def test_broken_user_agent_source_falls_back_to_a_chrome_user_agent(self):
        session = _Session({"https://jnrbsn.github.io/user-agents/user-agents.json": "not json"})

        user_agent = asyncio.run(discord.utils._get_user_agent(session))

        self.assertIn("Chrome/", user_agent)
        self.assertTrue(discord.utils._get_browser_version(user_agent))


if __name__ == "__main__":
    unittest.main()
