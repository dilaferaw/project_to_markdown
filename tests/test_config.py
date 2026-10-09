"""Tests for core.config.

A corrupted or hand-edited config file must never take the app down, and a
setting change must actually reach the code that uses it -- the old frozen
``from utils import DEFAULT_EXCLUDED_DIRS`` bindings meant it silently did not.
"""

import json

import pytest

from core.config import (
    DEFAULT_CONFIG,
    Config,
    _coerce_bool,
    _coerce_int,
    _normalise_dirs,
    _normalise_extensions,
    reload_config,
)


def fresh_copy(config):
    """Build another Config pointing at the same temp files."""
    clone = Config.__new__(Config)
    clone.config_dir = config.config_dir
    clone.config_file = config.config_file
    clone.data = {}
    clone.load()
    return clone


@pytest.fixture
def config(tmp_path):
    """A Config whose files live under a temp directory."""
    cfg = Config.__new__(Config)
    cfg.config_dir = tmp_path / "config-dir"
    cfg.config_file = cfg.config_dir / "config.json"
    cfg.data = {}
    cfg.load()
    return cfg


class TestNormalisation:
    def test_extensions_gain_a_leading_dot(self):
        # Typing "py" in the settings box is natural; without this it silently
        # disabled all text-file detection.
        assert _normalise_extensions(["py", ".rs", "js"]) == [".py", ".rs", ".js"]

    def test_extensions_are_lowercased_and_deduped(self):
        assert _normalise_extensions([".PY", ".py", " .PY "]) == [".py"]

    def test_blank_and_non_string_entries_are_dropped(self):
        assert _normalise_extensions(["", "   ", None, 42, ".py"]) == [".py"]

    @pytest.mark.parametrize("value", [[], None, "not a list", 42])
    def test_extensions_fall_back_when_nothing_usable(self, value):
        assert _normalise_extensions(value) == DEFAULT_CONFIG["text_extensions"]

    def test_dirs_are_stripped_of_slashes(self):
        assert _normalise_dirs(["build/", "/dist", "node_modules"]) == [
            "build", "dist", "node_modules"
        ]

    def test_dirs_drop_blanks_and_non_strings(self):
        assert _normalise_dirs(["", "  ", None, 7, "out"]) == ["out"]

    def test_dirs_allow_an_empty_list(self):
        assert _normalise_dirs([]) == []


class TestCoercion:
    @pytest.mark.parametrize("value", [10, "10", 10.7, True])
    def test_coerce_int_accepts_numbers(self, value):
        assert _coerce_int(value, 500) == int(value)

    @pytest.mark.parametrize("value", [0, -5, "abc", None, [], "12x"])
    def test_coerce_int_falls_back_on_nonsense(self, value):
        # A corrupted config used to reach the scan as `size_kb > "abc"` and
        # blow up with a TypeError.
        assert _coerce_int(value, 500) == 500

    @pytest.mark.parametrize("value,expected", [
        (True, True), (False, False),
        ("true", True), ("False", False), ("yes", True), ("0", False),
        (1, True), (0, False), (None, False),
    ])
    def test_coerce_bool(self, value, expected):
        assert _coerce_bool(value, False) is expected

    def test_coerce_bool_falls_back_for_junk_strings(self):
        assert _coerce_bool("maybe", True) is True
        assert _coerce_bool("maybe", False) is False

    def test_coerce_bool_falls_back_for_junk_strings(self):
        assert _coerce_bool("maybe", True) is True
        assert _coerce_bool("maybe", False) is False


class TestLoading:
    def test_defaults_are_created_when_no_file_exists(self, config):
        assert config.text_extensions == set(DEFAULT_CONFIG["text_extensions"])
        assert config.excluded_dirs == set(DEFAULT_CONFIG["excluded_dirs"])
        assert config.max_file_size_kb == DEFAULT_CONFIG["max_file_size_kb"]

    def test_stored_values_are_read_back(self, config):
        config.config_file.write_text(
            json.dumps({"max_file_size_kb": 99}), encoding="utf-8"
        )
        assert fresh_copy(config).max_file_size_kb == 99

    def test_missing_keys_are_filled_from_defaults(self, config):
        config.config_file.write_text(
            json.dumps({"max_file_size_kb": 99}), encoding="utf-8"
        )
        fresh = fresh_copy(config)
        assert fresh.text_extensions == set(DEFAULT_CONFIG["text_extensions"])

    def test_corrupt_json_does_not_raise(self, config):
        config.config_file.write_text("{not valid json", encoding="utf-8")
        fresh = fresh_copy(config)
        assert fresh.max_file_size_kb == DEFAULT_CONFIG["max_file_size_kb"]

    def test_a_json_array_instead_of_object_does_not_raise(self, config):
        config.config_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        fresh = fresh_copy(config)
        assert fresh.max_file_size_kb == DEFAULT_CONFIG["max_file_size_kb"]

    def test_hostile_value_types_are_coerced_on_load(self, config):
        config.config_file.write_text(json.dumps({
            "max_file_size_kb": "not a number",
            "text_extensions": "py",
            "excluded_dirs": {"not": "a list"},
            "output_auto_save": "true",
        }), encoding="utf-8")
        fresh = fresh_copy(config)
        assert fresh.max_file_size_kb == DEFAULT_CONFIG["max_file_size_kb"]
        assert fresh.text_extensions == set(DEFAULT_CONFIG["text_extensions"])
        assert fresh.excluded_dirs == set(DEFAULT_CONFIG["excluded_dirs"])
        assert fresh.output_auto_save is True


class TestSetters:
    def test_setting_extensions_normalises_and_persists(self, config):
        config.text_extensions = ["py", ".RS"]
        assert config.text_extensions == {".py", ".rs"}
        saved = json.loads(config.config_file.read_text(encoding="utf-8"))
        assert saved["text_extensions"] == [".py", ".rs"]

    def test_setting_a_bogus_size_falls_back(self, config):
        config.max_file_size_kb = "huge"
        assert config.max_file_size_kb == DEFAULT_CONFIG["max_file_size_kb"]

    def test_setting_an_empty_output_folder_falls_back(self, config):
        config.output_folder = "   "
        assert config.output_folder == DEFAULT_CONFIG["output_folder"]

    def test_reload_rereads_from_disk(self, config):
        config.max_file_size_kb = 123
        # Simulate another process overwriting the file behind our back.
        config.config_file.write_text(
            json.dumps({"max_file_size_kb": 7}), encoding="utf-8"
        )
        config.reload()
        assert config.max_file_size_kb == 7

    def test_reload_discards_unpersisted_edits(self, config):
        config.data["max_file_size_kb"] = 999  # bypass the setter, so no save
        config.reload()
        assert config.max_file_size_kb == DEFAULT_CONFIG["max_file_size_kb"]


class TestLiveAccessors:
    def test_accessors_reflect_a_change_immediately(self, monkeypatch, tmp_path):
        # The regression that mattered: core modules used to import the
        # constants directly, so reload_config() never reached them.
        import utils

        stub = Config.__new__(Config)
        stub.config_dir = tmp_path / "stub-config"
        stub.config_file = stub.config_dir / "config.json"
        stub.data = {}
        monkeypatch.setattr(utils, "get_config", lambda: stub)

        stub.excluded_dirs = ["only_this"]
        assert utils.get_excluded_dirs() == {"only_this"}
        stub.max_file_size_kb = 42
        assert utils.get_max_file_size_kb() == 42
        stub.text_extensions = ["md"]
        assert utils.get_text_extensions() == {".md"}

    def test_get_config_returns_a_singleton(self):
        from core.config import get_config
        assert get_config() is get_config()

    def test_reload_config_replaces_the_singleton(self):
        import core.config as config_module
        before = config_module.get_config()
        after = reload_config()
        assert after is config_module.get_config()
        assert after is not before
