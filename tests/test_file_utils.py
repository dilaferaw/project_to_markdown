"""Tests for core.file_utils.

Binary detection matters because anything classified as text gets pasted into
the prompt.  A JPEG or an .so that slips through costs thousands of tokens and
actively misleads the model.
"""

import pytest

from core.file_utils import generate_tree, is_text_file, looks_binary


class TestLooksBinary:
    @pytest.mark.parametrize("payload", [
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
        b"\xff\xd8\xff\xe0" + b"\xff" * 64,                 # JPEG
        b"%PDF-1.7\n" + b"junk" * 32,                       # PDF
        b"GIF89a" + b"\x00" * 32,                           # GIF
        b"\x7fELF" + b"\x00" * 32,                          # ELF / .so
        b"MZ\x90\x00" + b"\x00" * 32,                       # PE / DLL
        b"PK\x03\x04" + b"\x00" * 32,                       # ZIP / jar
        b"\x1f\x8b\x08\x00" + b"\x00" * 32,                 # gzip
        b"OggS" + b"\x00" * 32,                             # Ogg
        b"RIFF\x00\x00\x00\x00WAVE",                        # WAV
        b"SQLite format 3\x00" + b"\x00" * 16,              # SQLite
        b"\xca\xfe\xba\xbe" + b"\x00" * 32,                 # Java class
    ])
    def test_known_binary_signatures(self, payload):
        assert looks_binary(payload) is True

    def test_jpeg_with_no_nul_bytes_is_still_binary(self):
        # The NUL-only check let this straight through.
        assert looks_binary(b"\xff\xd8\xff\xe0" + b"A" * 4096 + b"\xff\xd9") is True

    def test_control_character_ratio(self):
        assert looks_binary(b"hello" + bytes([1, 2, 3, 7, 11, 13]) * 50) is True

    def test_nul_byte_anywhere_is_binary(self):
        assert looks_binary(b"perfectly fine text\x00then not") is True

    @pytest.mark.parametrize("payload", [
        b"",
        b"plain ascii text\n",
        b"# caf\xc3\xa9 utf-8\n",
        b"\xef\xbb\xbfutf-8 with a BOM\n",
        b"line1\nline2\r\nline3\n",
        b"import os\nimport sys\n",
        b'{"json": true, "nested": [1, 2, 3]}\n',
    ])
    def test_text_is_not_binary(self, payload):
        assert looks_binary(payload) is False

    def test_utf16_bom_is_treated_as_text(self):
        assert looks_binary("hello\n".encode("utf-16")) is False


class TestIsTextFile:
    def test_known_extension_short_circuits(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("x = 1\n", encoding="utf-8")
        assert is_text_file(f) is True

    def test_unknown_extension_is_sniffed(self, tmp_path):
        good = tmp_path / "Makefile"
        good.write_text("all:\n\techo hi\n", encoding="utf-8")
        assert is_text_file(good) is True

    def test_binary_with_a_known_extension_still_passes(self, tmp_path):
        # A .py file that is actually a PNG is bizarre, but the extension is a
        # deliberately strong hint -- documented behaviour, not a bug.
        f = tmp_path / "fake.py"
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        assert is_text_file(f, check_size=False) is True

    def test_binary_with_an_unknown_extension_is_rejected(self, tmp_path):
        f = tmp_path / "image.dat"
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        assert is_text_file(f, check_size=False) is False

    def test_oversized_file_is_rejected(self, tmp_path):
        f = tmp_path / "big.py"
        f.write_text("x\n" * 200, encoding="utf-8")
        assert is_text_file(f, check_size=True) is True
        # With the limit lowered below the file's size it must be rejected.
        from core import file_utils
        original = file_utils.get_max_file_size_kb
        file_utils.get_max_file_size_kb = lambda: 0.0001
        try:
            assert is_text_file(f, check_size=True) is False
        finally:
            file_utils.get_max_file_size_kb = original

    def test_size_check_can_be_skipped(self, tmp_path):
        f = tmp_path / "big.py"
        f.write_text("x\n" * 100000, encoding="utf-8")
        assert is_text_file(f, check_size=False) is True

    def test_missing_file_is_not_text(self, tmp_path):
        assert is_text_file(tmp_path / "nope.py") is False


class TestGenerateTree:
    def test_returns_a_string_mentioning_the_project(self, make_project):
        root = make_project({"a.py": "x\n"})
        tree = generate_tree(root)
        assert isinstance(tree, str)
        assert "a.py" in tree

    def test_excluded_directories_do_not_appear(self, make_project):
        root = make_project({"a.py": "x\n", ".venv/lib/pkg.py": "y\n"})
        assert "pkg.py" not in generate_tree(root)

    def test_nested_files_appear(self, make_project):
        root = make_project({"pkg/mod.py": "x\n"})
        assert "mod.py" in generate_tree(root)

    def test_does_not_raise_when_tree_binary_is_missing(self, make_project, monkeypatch):
        import subprocess

        def _raise(*args, **kwargs):
            raise FileNotFoundError("tree")

        monkeypatch.setattr(subprocess, "run", _raise)
        root = make_project({"a.py": "x\n", "pkg/b.py": "y\n"})
        assert "a.py" in generate_tree(root)

    def test_does_not_raise_when_tree_times_out(self, make_project, monkeypatch):
        import subprocess

        def _raise(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="tree", timeout=1)

        monkeypatch.setattr(subprocess, "run", _raise)
        root = make_project({"a.py": "x\n"})
        assert "a.py" in generate_tree(root)
