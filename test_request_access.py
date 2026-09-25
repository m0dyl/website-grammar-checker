"""Exercise real requests preparation with an offline transport adapter."""
import base64
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from requests.adapters import BaseAdapter
import main
from test_url_ignore import SITE, response


class OfflineAdapter(BaseAdapter):
    def __init__(self, pages):
        self.pages = pages
        self.seen = []
    def send(self, request, **kwargs):
        self.seen.append(request)
        result = self.pages[request.url]
        result.url = request.url
        result.request = request
        return result
    def close(self):
        pass


class RequestAccessTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for key in ("REQUEST_HEADERS", "REQUEST_COOKIES", "HTTP_BASIC_AUTH"):
            self.stack.enter_context(patch.object(main, key, None))

    def crawl(self, pages):
        session = requests.Session()
        adapter = OfflineAdapter(pages)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        tool = MagicMock()
        tool.__enter__.return_value = tool
        tool.check.return_value = []
        with tempfile.TemporaryDirectory() as directory, patch.object(main.requests, "Session", return_value=session), patch.object(main.language_tool_python, "LanguageTool", return_value=tool), contextlib.redirect_stdout(io.StringIO()):
            path = Path(directory) / "report.json"
            result = main.check_website_grammar(SITE, delay=0, url_ignore=[], report_path=str(path))
            serialized = path.read_text(encoding="utf-8")
            self.assertEqual(json.loads(serialized), result)
        return result, serialized, adapter.seen

    def test_none_preserves_normal_session(self):
        with requests.Session() as session:
            before = dict(session.headers)
            flags = main.configure_request_access(session, "http://example.com/")
            self.assertFalse(any(flags.values()))
            self.assertEqual(dict(session.headers), before)
            self.assertIsNone(session.auth)
            self.assertFalse(list(session.cookies))

    def test_headers_cookies_env_and_same_host_redirect(self):
        with patch.object(main, "REQUEST_HEADERS", {"Authorization": "env:TEST_ACCESS_AUTH"}), patch.object(main, "REQUEST_COOKIES", {"sessionid": "env:TEST_ACCESS_COOKIE"}), patch.dict(main.os.environ, {"TEST_ACCESS_AUTH": "Bearer fake-secret-token", "TEST_ACCESS_COOKIE": "fake-session-secret"}), patch("requests.sessions.get_netrc_auth", return_value=("unexpected", "netrc")):
            result, serialized, seen = self.crawl({SITE: response(status=302, location="/private"), SITE + "private": response("<p>Tekst</p>")})
        self.assertEqual(len(seen), 2)
        for request in seen:
            self.assertEqual(request.headers["Authorization"], "Bearer fake-secret-token")
            self.assertIn("sessionid=fake-session-secret", request.headers["Cookie"])
        self.assertNotIn("fake-secret-token", serialized)
        self.assertNotIn("fake-session-secret", serialized)
        self.assertTrue(result["settings"]["request_access"]["cookies_enabled"])
        self.assertEqual(result["pages"][0]["status"], "checked")

    def test_basic_auth(self):
        with patch.object(main, "HTTP_BASIC_AUTH", ("test-user", "test-pass")):
            _, serialized, seen = self.crawl({SITE: response("<p>Tekst</p>")})
        expected = "Basic " + base64.b64encode(b"test-user:test-pass").decode()
        self.assertEqual(seen[0].headers["Authorization"], expected)
        self.assertNotIn("test-pass", serialized)

    def test_cloudflare_headers(self):
        with patch.object(main, "REQUEST_HEADERS", {"CF-Access-Client-Id": "fake-id", "CF-Access-Client-Secret": "fake-cf-secret"}):
            _, serialized, seen = self.crawl({SITE: response("<p>Tekst</p>")})
        self.assertEqual(seen[0].headers["CF-Access-Client-Secret"], "fake-cf-secret")
        self.assertNotIn("fake-cf-secret", serialized)

    def test_no_credentials_to_http_or_external_redirect(self):
        for target in ("http://example.com/private", "https://external.com/private"):
            with self.subTest(target=target), patch.object(main, "REQUEST_HEADERS", {"Authorization": "Bearer fake-secret"}):
                result, _, seen = self.crawl({SITE: response(status=302, location=target)})
                self.assertEqual(len(seen), 1)
                self.assertEqual(result["pages"][0]["status"], "error")

    def test_start_http_rejected_and_cookie_scoped(self):
        with requests.Session() as session, patch.object(main, "REQUEST_COOKIES", {"sessionid": "fake-cookie"}):
            with self.assertRaises(ValueError):
                main.configure_request_access(session, "http://example.com/")
            main.configure_request_access(session, SITE)
            cookie = next(iter(session.cookies))
            self.assertTrue(cookie.secure)
            self.assertEqual(cookie.domain, "example.com")
            prepared = session.prepare_request(requests.Request("GET", "https://external.com/"))
            self.assertNotIn("Cookie", prepared.headers)

    def test_missing_env_and_invalid_headers_fail_without_values(self):
        with requests.Session() as session:
            for setting in ({"Authorization": "env:TEST_ABSENT_ACCESS_VAR"}, {"Authorization": "secret\nvalue"}, {"Host": "external.com"}, {"Cookie": "session=secret"}):
                with self.subTest(setting=list(setting)), patch.object(main, "REQUEST_HEADERS", setting), patch.dict(main.os.environ, {}, clear=True):
                    with self.assertRaises(ValueError) as caught:
                        main.configure_request_access(session, SITE)
                    self.assertNotIn("secret", str(caught.exception))
            with patch.object(main, "REQUEST_HEADERS", {"Authorization": "Bearer fake"}), patch.object(main, "HTTP_BASIC_AUTH", ("name", "password")):
                with self.assertRaises(ValueError):
                    main.configure_request_access(session, SITE)

    def test_blocked_responses_stop_before_parsing(self):
        for status, challenge in ((200, True), (403, False), (401, False)):
            page = response('<a href="/next">Next</a><p>Challenge text</p>', status=status)
            if challenge:
                page.headers["cf-mitigated"] = "challenge"
            with self.subTest(status=status):
                result, _, seen = self.crawl({SITE: page})
                self.assertEqual(len(seen), 1)
                self.assertEqual(result["pages"][0]["status"], "blocked")
                self.assertEqual(result["pages"][0]["errors"], [])
                self.assertIsNotNone(result["stop_reason"])


if __name__ == "__main__":
    unittest.main()
