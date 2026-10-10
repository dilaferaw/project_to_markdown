"""Tests for the PTM system prompt (core/prompt_template.py).

The prompt is the contract between the AI and the parser: if a marker the
parser recognises disappears from the prompt — or a stated rule contradicts
what the applier really does — responses silently stop applying.  These
tests derive the required markers from the parser's own regexes so the two
cannot drift apart, and pin the tone and size choices made in the stern
rewrite (accurate consequences, no fiction, token ceiling).
"""

import pytest

from core import response_parser
from core.applier import ChangeApplier
from core.prompt_template import FOOLPROOF_PROMPT_TEMPLATE, generate_full_prompt
from utils import count_tokens

# (the regex the parser actually keys on, the literal the prompt must teach)
REQUIRED_MARKERS = [
    (response_parser.FILE_START_RE, "FILE_START"),
    (response_parser.FILE_END_RE, "FILE_END"),
    (response_parser.DELETE_FILE_RE, "DELETE_FILE"),
    (response_parser.LINE_OPEN_RE, "[LINE"),
    (response_parser.LINE_CLOSE_RE, "[/LINE"),
    (response_parser.CODE_OPEN_RE, "[CODE"),
    (response_parser.CODE_CLOSE_RE, "[/CODE"),
]


class TestPromptMatchesParser:
    @pytest.mark.parametrize("regex,literal", REQUIRED_MARKERS)
    def test_prompt_documents_every_parser_marker(self, regex, literal):
        # The literal must genuinely be what the parser keys on ...
        assert literal.lstrip("[/") in regex.pattern
        # ... and the prompt must teach it.
        assert literal in FOOLPROOF_PROMPT_TEMPLATE

    def test_prompt_covers_backtick_placeholders(self):
        assert "[BACK]" in FOOLPROOF_PROMPT_TEMPLATE
        assert "[BACK3]" in FOOLPROOF_PROMPT_TEMPLATE

    def test_prompt_covers_rules_the_parser_enforces(self):
        text = FOOLPROOF_PROMPT_TEMPLATE.lower()
        # _extract_patches rejects overlapping ranges:
        assert "overlap" in text
        # _apply_deletes refuses modify+delete of the same path:
        assert "modified and deleted" in text
        # exports record forward-slash relative paths:
        assert "forward slashes" in text
        # an empty patch blanks the range instead of deleting it:
        assert "empty patch" in text


class TestGenerateFullPrompt:
    def test_instructions_first_project_data_last(self):
        result = generate_full_prompt("# PROJECT DATA")
        assert result == FOOLPROOF_PROMPT_TEMPLATE + "\n" + "# PROJECT DATA"
        assert result.startswith("## STRICT INSTRUCTIONS")
        assert result.endswith("# PROJECT DATA")


class TestToneAndBudget:
    def test_token_ceiling(self):
        # The prompt rides along on every export; keep it lean.
        assert count_tokens(FOOLPROOF_PROMPT_TEMPLATE) <= 1400

    def test_no_fiction_or_threats(self):
        # The stern rewrite dropped the $20k-fine / promotion theatre and
        # every claim that contradicts the hardened parser and applier.
        text = FOOLPROOF_PROMPT_TEMPLATE.lower()
        for banned in ("$20,000", "penalty", "promotion", "manager",
                       "human-in-the-loop", "silently corrupt",
                       "entire block ignored", "will not recognize"):
            assert banned not in text, f"stale/fiction phrase present: {banned}"


class TestPatchSemanticsDocumented:
    """The prompt's behavioural promises must match the real pipeline."""

    RESPONSE = (
        "--- FILE_START: a.py ---\n"
        "[CODE python]\n"
        "{patch}"
        "[/CODE]\n"
        "--- FILE_END ---\n"
    )
    ORIGINAL = "line1\nline2\nline3\n"

    def _apply(self, tmp_path, patch):
        result = response_parser.AIResponseParser().parse(
            self.RESPONSE.format(patch=patch)
        )
        assert result.ok, result.errors
        assert "a.py" in result.changes
        (tmp_path / "a.py").write_text(self.ORIGINAL, encoding="utf-8")
        report = ChangeApplier.apply_inplace(
            tmp_path, result.changes, {"a.py": self.ORIGINAL}
        )
        assert report.ok, report.summary()
        return (tmp_path / "a.py").read_text(encoding="utf-8")

    def test_empty_patch_blanks_the_line(self, tmp_path):
        # Prompt rule: "An empty patch replaces the range with a single
        # blank line — it does not delete."
        content = self._apply(tmp_path, "[LINE 2]\n[/LINE 2]\n")
        assert content == "line1\n\nline3\n"

    def test_range_replacement_omits_deleted_lines(self, tmp_path):
        # Prompt rule: "widen the range ... and omit the deleted lines."
        content = self._apply(tmp_path, "[LINE 1-2]\nline1\n[/LINE 1-2]\n")
        assert content == "line1\nline3\n"
