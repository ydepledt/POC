import unittest
from unittest.mock import AsyncMock, patch

import httpx
from bs4 import BeautifulSoup

import twikit_compat
from twikit.x_client_transaction import transaction
from twikit.x_client_transaction.transaction import ClientTransaction


class TwikitCompatTests(unittest.IsolatedAsyncioTestCase):
    def test_legacy_and_split_webpack_manifests_resolve_same_script(self):
        expected = "https://abs.twimg.com/responsive-web/client-web/ondemand.s.abc123a.js"
        manifests = [
            '<script>var files={"ondemand.s":"abc123"};</script>',
            '<script>var names={1:"main",600:"ondemand.s"};'
            'var hashes={1600:"bad123",600:"abc123"};</script>',
            "<script>var names={'600' : 'ondemand.s'};"
            "var hashes={'600' : 'abc123'};</script>",
        ]
        for manifest in manifests:
            with self.subTest(manifest=manifest):
                page = BeautifulSoup(manifest, "html.parser")
                self.assertEqual(twikit_compat.ondemand_script_url(page), expected)

    async def test_new_script_with_longer_variable_names_extracts_indices(self):
        page = BeautifulSoup('<script>var names={600:"ondemand.s"};'
                             'var hashes={600:"abc123"};</script>', "html.parser")
        script = httpx.Response(200, text="parseInt(ab[2],16);parseInt(c$[12], 16);"
                                "parseInt(a[14], 16);parseInt(longName[7],16)",
                                request=httpx.Request("GET", "https://abs.twimg.com/script.js"))
        session = AsyncMock()
        session.request.return_value = script
        with patch.object(twikit_compat, "version", return_value="2.3.3"), \
                patch.object(ClientTransaction, "get_indices"), \
                patch.object(transaction, "handle_x_migration"):
            twikit_compat.apply_twikit_compat()
            result = await ClientTransaction().get_indices(page, session, {"User-Agent": "test"})
        self.assertEqual(result, (2, [12, 14, 7]))
        session.request.assert_awaited_once_with(
            method="GET",
            url="https://abs.twimg.com/responsive-web/client-web/ondemand.s.abc123a.js",
            headers={"User-Agent": "test"},
        )

    async def test_missing_script_does_not_request_an_arbitrary_url(self):
        session = AsyncMock()
        for source in ("<html>page incomplete</html>", '<script>var names={600:"ondemand.s"}</script>'):
            with self.subTest(source=source), self.assertRaisesRegex(RuntimeError, "ondemand.s"):
                await twikit_compat._get_indices(
                    ClientTransaction(), BeautifulSoup(source, "html.parser"), session, {},
                )
        session.request.assert_not_awaited()

    async def test_http_block_is_propagated_without_retry(self):
        page = BeautifulSoup('<script>{"ondemand.s":"abc123"}</script>', "html.parser")
        session = AsyncMock()
        session.request.return_value = httpx.Response(
            403, request=httpx.Request("GET", "https://abs.twimg.com/script.js"),
        )
        with self.assertRaises(httpx.HTTPStatusError):
            await twikit_compat._get_indices(ClientTransaction(), page, session, {})
        session.request.assert_awaited_once()

    async def test_homepage_uses_app_route_with_http_errors_preserved(self):
        session = AsyncMock()
        session.request.return_value = httpx.Response(
            200, text='<html><script>{600:"ondemand.s"}</script></html>',
            request=httpx.Request("GET", "https://x.com/home"),
        )
        page = await twikit_compat._load_homepage(session, {"User-Agent": "test"})
        self.assertIsInstance(page, BeautifulSoup)
        session.request.assert_awaited_once_with(
            method="GET", url="https://x.com/home", headers={"User-Agent": "test"},
            follow_redirects=True,
        )
        session.request.reset_mock()
        session.request.return_value = httpx.Response(
            403, request=httpx.Request("GET", "https://x.com/home"),
        )
        with self.assertRaises(httpx.HTTPStatusError):
            await twikit_compat._load_homepage(session, {})
        session.request.assert_awaited_once()

    async def test_incomplete_script_has_explicit_error(self):
        page = BeautifulSoup('<script>{"ondemand.s":"abc123"}</script>', "html.parser")
        session = AsyncMock()
        session.request.return_value = httpx.Response(
            200, text="parseInt(a[2],16)",
            request=httpx.Request("GET", "https://abs.twimg.com/script.js"),
        )
        with self.assertRaisesRegex(RuntimeError, "KEY_BYTE"):
            await twikit_compat._get_indices(ClientTransaction(), page, session, {})

    async def test_logged_out_page_requests_a_local_session(self):
        session = AsyncMock()
        session.request.return_value = httpx.Response(
            200, text='<script src="https://abs.twimg.com/x-web/x-web/'
            'entry-client-logged-out-example.js"></script>',
            request=httpx.Request("GET", "https://x.com/home"),
        )
        with self.assertRaisesRegex(RuntimeError, "X_AUTH_TOKEN et X_CT0"):
            await twikit_compat._load_homepage(session, {})
        session.request.assert_awaited_once()

    def test_future_twikit_version_is_not_modified(self):
        original = ClientTransaction.get_indices
        with patch.object(twikit_compat, "version", return_value="2.3.4"):
            self.assertFalse(twikit_compat.apply_twikit_compat())
        self.assertIs(ClientTransaction.get_indices, original)


if __name__ == "__main__":
    unittest.main()
