"""Tests for core.markdown_builder.

The export is the AI's only view of the project, so the line numbers it emits
have to match reality exactly, and the file list has to be stable -- otherwise
the AI cites a line number that means something different on the next run.
"""

import re

from core.markdown_builder import (
    collect_files,
    export_project,
    scan_project_files,
    _detect_encoding,
    _number_lines,
)


class TestExportContract:
    def test_returns_markdown_contents_and_encodings(self, make_project):
        root = make_project({"a.py": "x = 1\n"})
        md, contents, encodings = export_project(root)
        assert "# Project Structure" in md
        assert "# File Contents" in md
        assert contents == {"a.py": "x = 1\n"}
        assert encodings == {"a.py": "utf-8"}

    def test_file_ids_are_sequential_and_one_based(self, make_project):
        root = make_project({"a.py": "x\n", "b.py": "y\n"})
        md, _, _ = export_project(root)
        assert "[file-001]" in md
        assert "[file-002]" in md

    def test_language_hint_follows_the_extension(self, make_project):
        root = make_project({"a.py": "x\n", "b.rs": "y\n", "c.unknownext": "z\n"})
        md, _, _ = export_project(root)
        assert "```python" in md
        assert "```rust" in md

    def test_include_only_limits_the_contents_section(self, make_project):
        root = make_project({"a.py": "x\n", "b.py": "y\n"})
        _, contents, _ = export_project(root, include_only={"a.py"})
        assert set(contents) == {"a.py"}

    def test_include_only_tolerates_backslash_paths(self, make_project):
        # An AI answering on Windows may hand back backslash-separated paths.
        root = make_project({"pkg/m.py": "x\n", "other.py": "y\n"})
        _, contents, _ = export_project(root, include_only={"pkg\\m.py"})
        assert set(contents) == {"pkg/m.py"}

    def test_empty_selection_yields_no_contents(self, make_project):
        root = make_project({"a.py": "x\n"})
        _, contents, _ = export_project(root, include_only=set())
        assert contents == {}


class TestLineNumbering:
    def test_a_file_ending_in_a_newline_has_no_phantom_line(self):
        # split('\n') yields a trailing '' element, which used to inflate the
        # count by one and send the AI hunting for a line that never existed.
        numbered = _number_lines("a\nb\nc\n")
        assert numbered == "   1│a\n   2│b\n   3│c"
        assert "4│" not in numbered

    def test_a_file_without_a_trailing_newline(self):
        assert _number_lines("a\nb") == "   1│a\n   2│b"

    def test_numbers_are_right_aligned_to_a_fixed_width(self):
        numbered = _number_lines("\n".join(f"line{i}" for i in range(1, 12)) + "\n")
        assert "   1│line1" in numbered
        assert "  10│line10" in numbered

    def test_blank_lines_are_preserved_and_numbered(self):
        assert _number_lines("a\n\nb\n") == "   1│a\n   2│\n   3│b"

    def test_empty_file_produces_no_numbered_lines(self):
        assert _number_lines("") == ""

    def test_exported_numbers_match_the_original_file(self, make_project):
        root = make_project({"a.py": "one\ntwo\nthree\n"})
        md, _, _ = export_project(root)
        block = re.search(r"## `a\.py`.*?\n```python\n(.*?)\n```", md, re.DOTALL).group(1)
        assert [ln.split("│", 1)[1] for ln in block.split("\n")] == ["one", "two", "three"]


class TestDeterminism:
    def test_two_runs_produce_identical_markdown(self, make_project):
        root = make_project({"b.py": "b\n", "a.py": "a\n", "pkg/c.py": "c\n"})
        assert export_project(root)[0] == export_project(root)[0]

    def test_scan_and_export_agree_on_the_file_set(self, make_project):
        root = make_project({"a.py": "x\n", "pkg/b.py": "y\n", "deep/c/d.py": "z\n"})
        _, contents, _ = export_project(root)
        assert set(scan_project_files(root)) == set(contents)

    def test_collect_files_is_sorted(self, make_project):
        root = make_project({"z.py": "1\n", "a.py": "1\n", "pkg/m.py": "1\n"})
        names = [rel for rel, _ in collect_files(root)]
        assert names == sorted(names)

    def test_nested_directories_are_sorted_deterministically(self, make_project):
        root = make_project({
            "zeta/a.py": "1\n", "alpha/z.py": "1\n", "alpha/a.py": "1\n",
        })
        first = [rel for rel, _ in collect_files(root)]
        assert first == [rel for rel, _ in collect_files(root)]
        assert "alpha/a.py" in first


class TestExcludedDirectories:
    def test_venv_and_git_are_skipped(self, make_project):
        root = make_project({
            "real.py": "x\n",
            ".git/config": "nope\n",
            ".venv/lib/site.py": "nope\n",
            "node_modules/pkg/index.js": "nope\n",
            "__pycache__/x.pyc": "nope\n",
        })
        _, contents, _ = export_project(root)
        assert set(contents) == {"real.py"}



class TestEncodingDetection:
    def test_utf8_is_preferred(self):
        assert _detect_encoding(b"plain ascii\n") == "utf-8"
        assert _detect_encoding("café\n".encode("utf-8")) == "utf-8"

    def test_utf8_bom_is_recognised(self):
        assert _detect_encoding(b"\xef\xbb\xbfhello\n") == "utf-8-sig"

    def test_utf16_bom_is_recognised(self):
        assert _detect_encoding("hi\n".encode("utf-16")) == "utf-16"

    def test_latin1_falls_back_losslessly(self):
        # The fallback must never introduce U+FFFD, or patching the file would
        # permanently destroy those bytes.
        assert _detect_encoding(b"# caf\xe9\n") == "cp1252"
        assert _detect_encoding(b"# \xe9\xe8\xea\n") in ("cp1252", "latin-1")

    def test_content_round_trips_without_replacement_chars(self, make_project):
        root = make_project({"latin.py": "placeholder\n"})
        (root / "latin.py").write_bytes(b"# caf\xe9\nprint('ok')\n")
        _, contents, encodings = export_project(root)
        assert "\ufffd" not in contents["latin.py"]
        assert contents["latin.py"] == "# caf\xe9\nprint('ok')\n"
        assert encodings["latin.py"] in ("cp1252", "latin-1")
