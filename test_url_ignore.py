"""Offline tests: no website requests and no LanguageTool server."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
import main


SITE = "https://example.com/"


def response(body="", status=200, location=None):
    result = requests.Response()
    result.status_code = status
    result._content = body.encode("utf-8")
    result._content_consumed = True
    result.headers["Content-Type"] = "text/html; charset=utf-8"
    if location:
        result.headers["Location"] = location
    return result


class UrlIgnoreTests(unittest.TestCase):
    def test_section_boundaries_and_query(self):
        roots = main.build_ignored_url_roots(SITE, ["/blog/"])
        for path in ("/blog", "/blog/", "/blog/a/b", "/blog?p=2#x"):
            with self.subTest(path=path):
                self.assertTrue(main.is_ignored_url(SITE.rstrip("/") + path, roots))
        for path in ("/blog-other", "/blogs", "/Blog", "/other/blog"):
            with self.subTest(path=path):
                self.assertFalse(main.is_ignored_url(SITE.rstrip("/") + path, roots))
        self.assertFalse(main.is_ignored_url("https://other.com/blog", roots))

    def test_absolute_unicode_and_normalization(self):
        roots = main.build_ignored_url_roots(SITE, ["http://example.com/oferta/żele/?x=1"])
        self.assertTrue(main.is_ignored_url(SITE + "oferta/%C5%BCele/item", roots))
        self.assertTrue(main.is_ignored_url(SITE + "x/../oferta/żele/item", roots))
        self.assertFalse(main.is_ignored_url(SITE + "oferta/żele/../other", roots))

    def test_empty_list(self):
        self.assertFalse(main.is_ignored_url(SITE, main.build_ignored_url_roots(SITE, [])))

    def test_root_rule(self):
        roots = main.build_ignored_url_roots(SITE, ["/"])
        self.assertTrue(main.is_ignored_url(SITE + "any/page", roots))

    def test_invalid_configuration(self):
        for entries in ("/blog", [""], [None], ["https://other.com/blog"], ["mailto:test@example.com"]):
            with self.subTest(entries=entries):
                with self.assertRaises(ValueError):
                    main.build_ignored_url_roots(SITE, entries)

    def test_blocked_start_does_not_start_tools(self):
        with patch.object(main.language_tool_python, "LanguageTool") as factory:
            with self.assertRaises(ValueError):
                main.check_website_grammar(SITE + "blog/a", url_ignore=["/blog"])
            factory.assert_not_called()

    def test_crawl_and_redirect_never_fetch_ignored_sections(self):
        pages = {
            SITE: response('<html><body><a href="/blog">Blog</a><a href="/blog/a">A</a><iframe src="/blog/frame"></iframe><a href="/blog-other">Keep</a><a href="/go">Redirect</a><a href="https://external.com/">External</a></body></html>'),
            SITE + "blog-other": response('<html><body><a href="/keep/deep">Deep</a><a href="/blog/nested">Blocked</a></body></html>'),
            SITE + "go": response(status=302, location="/blog/secret"),
            SITE + "keep/deep": response('<html><body><p>Tekst</p></body></html>'),
        }
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.side_effect = lambda url, **kwargs: pages[url]
        tool = MagicMock()
        tool.__enter__.return_value = tool
        tool.check.return_value = []
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(main.requests, "Session", return_value=session), patch.object(main.language_tool_python, "LanguageTool", return_value=tool), contextlib.redirect_stdout(io.StringIO()):
                result = main.check_website_grammar(SITE, delay=0, url_ignore=["/blog"], report_path=str(Path(directory) / "report.json"))
        self.assertEqual([call.args[0] for call in session.get.call_args_list], list(pages))
        self.assertEqual(result["pending_urls"], [])
        self.assertEqual(result["settings"]["url_ignore"], ["/blog"])
        redirect = next(page for page in result["pages"] if page["url"] == SITE + "go")
        self.assertEqual(redirect["status"], "ignored")
        self.assertEqual(redirect["redirect_target"], SITE + "blog/secret")
        self.assertNotIn(SITE + "blog", result["discovered_urls"])


if __name__ == "__main__":
    unittest.main()
