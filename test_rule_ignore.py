"""Offline rule filtering regressions; no Java or live HTTP."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import main
from test_url_ignore import SITE, response


def match(rule, kind="grammar", offset=0, length=2, replacements=()):
    return SimpleNamespace(rule_id=rule, rule_issue_type=kind, offset=offset,
                           error_length=length, message=rule, replacements=list(replacements))


class RuleIgnoreTests(unittest.TestCase):
    def run_check(self, text, ignored, checker, english=False, caps=True):
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.return_value = response(f"<html><body><p>{text}</p></body></html>")
        def factory(language):
            tool = MagicMock()
            tool.__enter__.return_value = tool
            tool.check.side_effect = lambda text: checker(language, text)
            return tool
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(main, "RULE_ID_IGNORE", ignored))
            stack.enter_context(patch.object(main, "ENGLISH_IGNORE", english))
            stack.enter_context(patch.object(main, "ALL_CAPITAL_LETTERS_IGNORE", caps))
            stack.enter_context(patch.object(main.requests, "Session", return_value=session))
            stack.enter_context(patch.object(main.language_tool_python, "LanguageTool", side_effect=factory))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            path = Path(directory) / "report.json"
            result = main.check_website_grammar(SITE, lang="pl", delay=0, url_ignore=[], report_path=str(path))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), result)
        self.assertEqual(result["pages"][0]["status"], "checked")
        self.assertEqual(result["settings"]["rule_id_ignore"], sorted(set(ignored)))
        return result["pages"][0]["errors"]

    def test_exact_id_and_empty_list(self):
        checker = lambda language, text: [match("AL_UJAZDOWSKIE"), match("AL_UJAZDOWSKIE_OTHER")]
        errors = self.run_check("Al. Piastów", ["AL_UJAZDOWSKIE"], checker)
        self.assertEqual([e["rule_id"] for e in errors], ["AL_UJAZDOWSKIE_OTHER"])
        self.assertEqual(len(self.run_check("Al. Piastów", [], checker)), 2)

    def test_uppercase_secondary_pass(self):
        checker = lambda language, text: [match("SPELL", "misspelling", length=len(text))]
        self.assertEqual(self.run_check("ZZWORD", ["SPELL"], checker, caps=False), [])
        self.assertTrue(self.run_check("ZZWORD", [], checker, caps=False))

    def test_english_dictionary_ignore_does_not_accept_misspellings(self):
        checker = lambda language, text: [match("EN_SPELL" if language == "en-US" else "PL_SPELL", "misspelling", length=len(text))]
        errors = self.run_check("zzword", ["EN_SPELL"], checker, english=True)
        self.assertEqual([e["rule_id"] for e in errors], ["PL_SPELL"])

    def test_hyphen_filter_stays_narrow(self):
        def checker(language, text):
            return [match("DYWIZ", offset=6, length=1, replacements=["—"]),
                    match("DYWIZ", offset=0, length=5, replacements=["other"])]
        with patch.object(main, "HYPHEN_DASH_IGNORE", True):
            errors = self.run_check("tekst - tekst", ["AL_UJAZDOWSKIE"], checker)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["word"], "tekst")


if __name__ == "__main__":
    unittest.main()
