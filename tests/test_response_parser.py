"""Tests for core.response_parser.

Every test here corresponds to a real data-loss or silent-corruption bug that
shipped at some point.  The parser's contract is: *parse what is unambiguous,
and refuse -- loudly -- everything else.*  A block that gets guessed at is how
an AI's prose ends up overwriting a source file.
"""

import pytest

from core.response_parser import AIResponseParser, ParseResult, expand_backticks


def parse(text, **kwargs):
    """Convenience wrapper returning just the ParseResult."""
    return AIResponseParser(**kwargs).parse(text)


# ---------------------------------------------------------------------------
# Happy path -- the format working as designed
# ---------------------------------------------------------------------------

class TestWellFormed:
    def test_single_file_whole_content(self):
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\nprint('hi')\n[/CODE]\n--- FILE_END ---\n"
        )
        assert result.changes == {
            "a.py": {"action": "modify", "content": "print('hi')"}
        }
        assert result.ok

    def test_language_tag_is_accepted(self):
        result = parse(
            "--- FILE_START: a.py ---\n[CODE python]\nx = 1\n[/CODE]\n--- FILE_END ---\n"
        )
        assert result.changes["a.py"]["content"] == "x = 1"

    def test_language_tag_containing_a_bracket(self):
        # The old `[^\]]+` pattern could not match a tag with a `]` in it.
        result = parse(
            "--- FILE_START: a.py ---\n[CODE python [extra]]\nx = 1\n[/CODE]\n--- FILE_END ---\n"
        )
        assert result.changes["a.py"]["content"] == "x = 1"

    def test_backtick_placeholders_expand_per_file(self):
        result = parse(
            '--- FILE_START: test.py ---\n[CODE python]\n'
            't = "[BACK3]test[BACK]"\n[/CODE]\n--- FILE_END ---\n'
        )
        assert result.changes["test.py"]["content"] == 't = "```test`"'

    def test_multiple_fences_inside_one_file_survive(self):
        # Expanding [BACK3] up front used to let the fence-stripping regexes
        # eat the inner fences and mangle the file.
        result = parse(
            "--- FILE_START: notes.md ---\n[CODE markdown]\n"
            "[BACK3]text\nA\n[BACK3]\n\n[BACK3]text\nB\n[BACK3]\n"
            "[/CODE]\n--- FILE_END ---\n"
        )
        assert result.changes["notes.md"]["content"] == (
            "```text\nA\n```\n\n```text\nB\n```"
        )

    def test_multiple_files_in_one_bundle(self):
        result = parse(
            "```text\n"
            "--- FILE_START: utils.py ---\n[CODE]\ndef f():\n    pass\n[/CODE]\n--- FILE_END ---\n"
            "--- FILE_START: main.py ---\n[CODE]\nf()\n[/CODE]\n--- FILE_END ---\n"
            "```\n"
        )
        assert set(result.changes) == {"utils.py", "main.py"}
        assert result.changes["main.py"]["content"] == "f()"

    def test_patch_single_line(self):
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\n[LINE 12]\nreplacement\n[/LINE 12]\n"
            "[/CODE]\n--- FILE_END ---\n"
        )
        assert result.changes["a.py"]["patches"] == [
            {"start": 12, "end": 12, "content": "replacement"}
        ]

    def test_patch_line_range(self):
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\n[LINE 5-7]\nb1\nb2\n[/LINE 5-7]\n"
            "[/CODE]\n--- FILE_END ---\n"
        )
        assert result.changes["a.py"]["patches"] == [
            {"start": 5, "end": 7, "content": "b1\nb2"}
        ]

    def test_patch_preserves_intentional_leading_blank_line(self):
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\n[LINE 10]\n\ndef f():\n    pass\n"
            "[/LINE 10]\n[/CODE]\n--- FILE_END ---\n"
        )
        patch = result.changes["a.py"]["patches"][0]
        assert patch["content"].startswith("\n")
        assert patch["content"] == "\ndef f():\n    pass"

    def test_multiple_non_overlapping_patches(self):
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\n[LINE 2]\ntwo\n[/LINE 2]\n"
            "[LINE 5-6]\nfive\nsix\n[/LINE 5-6]\n[/CODE]\n--- FILE_END ---\n"
        )
        patches = result.changes["a.py"]["patches"]
        assert [(p["start"], p["end"]) for p in patches] == [(2, 2), (5, 6)]

    def test_delete_file(self):
        result = parse("--- DELETE_FILE: old.py ---\n")
        assert result.changes == {"old.py": {"action": "delete", "content": None}}

    def test_modify_and_delete_different_files(self):
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\nx\n[/CODE]\n--- FILE_END ---\n"
            "--- DELETE_FILE: b.py ---\n"
        )
        assert result.changes["a.py"]["content"] == "x"
        assert result.changes["b.py"]["action"] == "delete"

    def test_crlf_input(self):
        result = parse(
            "--- FILE_START: a.py ---\r\n[CODE]\r\nx = 1\r\n[/CODE]\r\n--- FILE_END ---\r\n"
        )
        assert result.changes["a.py"]["content"] == "x = 1"

    def test_markers_are_case_insensitive(self):
        result = parse(
            "--- file_start: a.py ---\n[code]\nx\n[/code]\n--- file_end ---\n"
        )
        assert result.changes["a.py"]["content"] == "x"

    def test_path_with_internal_dashes_is_not_truncated(self):
        # The old non-greedy path regex cut the path at the first " --- ".
        result = parse(
            "--- FILE_START: a --- weird.py ---\n[CODE]\nx\n[/CODE]\n--- FILE_END ---\n"
        )
        assert "a --- weird.py" in result.changes

    def test_empty_input_is_not_an_error(self):
        result = parse("")


# ---------------------------------------------------------------------------
# Bug regressions -- each of these used to corrupt or destroy data silently
# ---------------------------------------------------------------------------

class TestMissingFileEndDoesNotSwallowSiblings:
    def test_next_block_is_still_parsed(self):
        # The old forward-scanning FILE_END regex consumed the *following*
        # block's FILE_END, so every file after the malformed one vanished.
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\nfirst\n[/CODE]\n\n"
            "--- FILE_START: b.py ---\n[CODE]\nsecond\n[/CODE]\n--- FILE_END ---\n"
        )
        assert set(result.changes) == {"a.py", "b.py"}
        assert result.changes["b.py"]["content"] == "second"

    def test_it_warns_about_the_unclosed_block(self):
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\nfirst\n[/CODE]\n"
            "--- FILE_START: b.py ---\n[CODE]\nsecond\n[/CODE]\n--- FILE_END ---\n"
        )
        assert any("FILE_END" in w for w in result.warnings)

    def test_unclosed_final_block_is_reported_not_dropped(self):
        result = parse("--- FILE_START: a.py ---\n[CODE]\nx\n[/CODE]\n")
        assert result.changes["a.py"]["content"] == "x"
        assert any("FILE_END" in w for w in result.warnings)


class TestMalformedBlocksAreRejectedNotGuessed:
    def test_mismatched_close_line_tag_is_rejected(self):
        # Previously this fell through to whole-file replacement, overwriting
        # the entire file with a 3-line snippet.
        result = parse(
            "--- FILE_START: existing.py ---\n[CODE]\n[LINE 12]\ndef f():\n    pass\n"
            "[/LINE]\n[/CODE]\n--- FILE_END ---\n"
        )
        assert "existing.py" not in result.changes
        assert result.errors

    def test_range_closed_by_single_line_tag_is_rejected(self):
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\n[LINE 10-15]\nbody\n[/LINE 10]\n"
            "[/CODE]\n--- FILE_END ---\n"
        )
        assert "a.py" not in result.changes
        assert any("must name the same lines" in e for e in result.errors)

    def test_unclosed_line_tag_is_rejected(self):
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\n[LINE 12]\nbody\n[/CODE]\n--- FILE_END ---\n"
        )
        assert "a.py" not in result.changes
        assert any("never closed" in e for e in result.errors)

    def test_nested_line_open_is_rejected(self):
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\n[LINE 1]\n[LINE 2]\nbody\n"
            "[/LINE 2]\n[/CODE]\n--- FILE_END ---\n"
        )
        assert "a.py" not in result.changes
        assert result.errors

    def test_missing_code_tags_is_rejected(self):
        # The worst one: the AI's explanation used to be written over the file.
        result = parse(
            "--- FILE_START: a.py ---\nHere is my plan for a.py.\n"
            "I changed three things.\n--- FILE_END ---\n"
        )
        assert "a.py" not in result.changes
        assert result.errors

    def test_inline_close_tag_is_rejected(self):
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\nsingle line[/CODE]\n--- FILE_END ---\n"
        )
        assert "a.py" not in result.changes

    def test_empty_file_start_path_is_rejected(self):
        result = parse("--- FILE_START:  ---\n[CODE]\nx\n[/CODE]\n--- FILE_END ---\n")
        assert result.changes == {}
        assert result.errors

    def test_prose_outside_code_tags_is_not_injected(self):
        # Loose prose is discarded rather than written into the file, and the
        # user is told the AI broke the format.
        result = parse(
            "--- FILE_START: a.py ---\nSome note\n[CODE]\nx\n[/CODE]\n"
            "Trailing note\n--- FILE_END ---\n"
        )
        assert result.changes["a.py"]["content"] == "x"
        assert "Some note" not in result.changes["a.py"]["content"]
        assert "Trailing note" not in result.changes["a.py"]["content"]
        assert any("outside the [CODE] block" in w for w in result.warnings)

    def test_a_stray_marker_before_code_is_rejected(self):
        result = parse(
            "--- FILE_START: a.py ---\n[/LINE 3]\n[CODE]\nx\n[/CODE]\n--- FILE_END ---\n"
        )
        assert "a.py" not in result.changes
        assert result.errors

    def test_whitespace_only_input_is_not_an_error(self):
        result = parse("   \n\n\t\n")
        assert result.changes == {}


class TestPatchValidation:
    def test_inverted_range_is_rejected(self):
        # An inverted range used to *insert* text instead of replacing lines.
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\n[LINE 10-5]\nNEW\n[/LINE 10-5]\n"
            "[/CODE]\n--- FILE_END ---\n"
        )
        assert "a.py" not in result.changes
        assert any("inverted" in e for e in result.errors)

    def test_line_zero_is_rejected(self):
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\n[LINE 0]\nx\n[/LINE 0]\n"
            "[/CODE]\n--- FILE_END ---\n"
        )
        assert "a.py" not in result.changes
        assert result.errors

    def test_overlapping_patches_are_rejected(self):
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\n[LINE 5]\nA\n[/LINE 5]\n"
            "[LINE 5-6]\nB\n[/LINE 5-6]\n[/CODE]\n--- FILE_END ---\n"
        )
        assert "a.py" not in result.changes
        assert any("overlap" in e for e in result.errors)

    def test_adjacent_patches_are_allowed(self):
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\n[LINE 5]\nA\n[/LINE 5]\n"
            "[LINE 6]\nB\n[/LINE 6]\n[/CODE]\n--- FILE_END ---\n"
        )
        assert len(result.changes["a.py"]["patches"]) == 2


class TestMarkersInsideFileContent:
    def test_delete_marker_inside_a_block_is_content(self):
        # Honouring it deleted an unrelated file the AI merely mentioned.
        result = parse(
            '--- FILE_START: a.py ---\n[CODE]\n'
            'print("--- DELETE_FILE: path/to/x.py ---")\n[/CODE]\n--- FILE_END ---\n'
        )
        assert set(result.changes) == {"a.py"}
        assert "path/to/x.py" in result.changes["a.py"]["content"]

    def test_it_warns_when_a_bare_delete_marker_sits_inside_a_block(self):
        # A bare directive line inside a block is kept as content, and the user
        # is told it was not treated as a deletion.
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\nx\n[/CODE]\n"
            "--- DELETE_FILE: x.py ---\n--- FILE_END ---\n"
        )
        assert set(result.changes) == {"a.py"}
        assert result.changes["a.py"]["action"] == "modify"
        assert any("DELETE_FILE" in w for w in result.warnings)

    def test_a_delete_marker_mentioned_in_code_is_left_alone(self):
        # A string literal mentioning the syntax must not trigger a warning.
        result = parse(
            '--- FILE_START: a.py ---\n[CODE]\n'
            'print("--- DELETE_FILE: x.py ---")\n[/CODE]\n--- FILE_END ---\n'
        )
        assert set(result.changes) == {"a.py"}
        assert not any("DELETE_FILE" in w for w in result.warnings)

    def test_file_content_containing_code_markers_is_not_truncated(self):
        # The old non-greedy regex stopped at the file's own first [/CODE].
        result = parse(
            "--- FILE_START: README.md ---\n[CODE markdown]\n"
            "Use [CODE] like this\n[/CODE]\nand then keep going\n[/CODE]\n--- FILE_END ---\n"
        )
        assert result.changes["README.md"]["content"] == (
            "Use [CODE] like this\n[/CODE]\nand then keep going"
        )


class TestConflictingInstructions:
    def test_modify_and_delete_same_file_refuses_both(self):
        # The delete used to be applied last and silently win.
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\nnew\n[/CODE]\n--- FILE_END ---\n"
            "--- DELETE_FILE: a.py ---\n"
        )
        assert "a.py" not in result.changes
        assert result.errors

    def test_duplicate_file_warns_and_keeps_the_last(self):
        result = parse(
            "--- FILE_START: a.py ---\n[CODE]\nfirst\n[/CODE]\n--- FILE_END ---\n"
            "--- FILE_START: a.py ---\n[CODE]\nsecond\n[/CODE]\n--- FILE_END ---\n"
        )
        assert result.changes["a.py"]["content"] == "second"
        assert any("Duplicate" in w for w in result.warnings)


class TestLegacyFallback:
    def test_off_by_default(self):
        # The old fallback rewrote files the AI merely talked about.
        result = parse(
            "```text\nsome explanation\n```\n\n```python ./foo\nx = 1\n```\n"
        )
        assert result.changes == {}
        assert any("FILE_START" in w for w in result.warnings)

    def test_available_when_explicitly_enabled(self):
        result = parse("```python ./foo\nx = 1\n```\n", allow_legacy=True)
        assert "./foo" in result.changes
        assert result.changes["./foo"]["content"] == "x = 1"

    def test_legacy_mode_is_still_strict_about_unmarked_blocks(self):
        result = parse("--- FILE_START: a.py ---\njust prose\n--- FILE_END ---\n")
        assert "a.py" not in result.changes


class TestParserStateIsolation:
    def test_warnings_do_not_leak_between_instances(self):
        # `warnings` used to be mutable class-level state.
        first, second = AIResponseParser(), AIResponseParser()
        first.parse("--- FILE_START: a.py ---\n[CODE]\nx\n[/CODE]\n")
        assert second.warnings == []
        assert second.errors == []

    def test_reparsing_resets_previous_warnings(self):
        parser = AIResponseParser()
        parser.parse("--- FILE_START: a.py ---\n[CODE]\nx\n[/CODE]\n")
        parser.parse("--- FILE_START: b.py ---\n[CODE]\ny\n[/CODE]\n--- FILE_END ---\n")
        assert not any("a.py" in w for w in parser.warnings)

    def test_parse_result_truthiness(self):
        assert not ParseResult()
        assert ParseResult(changes={"a.py": {}})


class TestExpandBackticks:
    def test_placeholder_expansion(self):
        assert expand_backticks("a[BACK]b[BACK3]c") == "a`b```c"

    def test_leaves_ordinary_text_alone(self):
        assert expand_backticks("plain text") == "plain text"
