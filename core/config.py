"""JSON‑based configuration for ProjectToMarkdown."""

import json
from pathlib import Path
from typing import List, Set


DEFAULT_CONFIG = {
    "text_extensions": [
        ".py", ".rs", ".html", ".css", ".js", ".ts", ".json", ".yaml", ".yml",
        ".toml", ".md", ".txt", ".c", ".cpp", ".h", ".hpp", ".java", ".go",
        ".rb", ".php", ".swift", ".kt", ".kts", ".sh", ".bash", ".zsh",
        ".xml", ".svg", ".cf", ".conf", ".ini", ".cfg", ".sql", ".r", ".lua",
        ".pl", ".pm", ".dart", ".ex", ".exs", ".erl", ".hrl", ".hs", ".lhs",
        ".vim", ".emacs", ".dockerfile", ".makefile", ".cmake", ".gradle"
    ],
    "excluded_dirs": [
        ".git", "node_modules", "target", "venv", ".venv", "__pycache__",
        "build", "dist", ".next", ".nuxt", "out", "bin", "obj"
    ],
    "max_file_size_kb": 500,
    "output_auto_save": False,
    "output_folder": ".output-md"
}


def _normalise_extensions(value) -> List[str]:
    """Coerce a config value into a clean list of ``.ext`` strings.

    Without this a user typing ``py`` instead of ``.py`` (perfectly natural in
    the settings box) would silently disable *all* text-file detection, and a
    corrupted config holding a non-list would crash the whole scan.
    """
    if not isinstance(value, (list, tuple, set)):
        return list(DEFAULT_CONFIG["text_extensions"])
    cleaned = []
    for item in value:
        if not isinstance(item, str):
            continue
        item = item.strip().lower()
        if not item:
            continue
        if not item.startswith("."):
            item = "." + item
        if item not in cleaned:
            cleaned.append(item)
    return cleaned or list(DEFAULT_CONFIG["text_extensions"])


def _normalise_dirs(value) -> List[str]:
    """Coerce a config value into a clean list of directory names."""
    if not isinstance(value, (list, tuple, set)):
        return list(DEFAULT_CONFIG["excluded_dirs"])
    cleaned = []
    for item in value:
        if not isinstance(item, str):
            continue
        item = item.strip().strip("/\\")
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned


def _coerce_int(value, default: int) -> int:
    """Coerce to a positive int, falling back to the default."""
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return result if result > 0 else default


def _coerce_bool(value, default: bool) -> bool:
    """Coerce to a bool, falling back to the default for anything unrecognised."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("1", "true", "yes", "on"):
            return True
        if text in ("0", "false", "no", "off", ""):
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default



class Config:
    """Application configuration loaded from a JSON file."""
    
    def __init__(self):
        self.config_dir = Path.home() / ".config" / "project-to-markdown"
        self.config_file = self.config_dir / "config.json"
        self.data = {}
        self.load()
    
    def load(self):
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            # A read-only home directory must not stop the app from starting;
            # we simply fall back to defaults held in memory.
            self.data = dict(DEFAULT_CONFIG)
            return

        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                if not isinstance(self.data, dict):
                    self.data = {}
            except (json.JSONDecodeError, PermissionError, UnicodeDecodeError, OSError):
                self.data = {}

        self.data = self._sanitised(self.data)
        self.save()

    @staticmethod
    def _sanitised(data: dict) -> dict:
        """Merge user data over the defaults and coerce every value.

        A hand-edited or corrupted config file used to crash the scan later with
        something opaque like ``TypeError: '>' not supported between 'float'
        and 'str'``.  Validating once, here, keeps that class of bug out of the
        scanning code entirely.
        """
        return {
            "text_extensions": _normalise_extensions(
                data.get("text_extensions", DEFAULT_CONFIG["text_extensions"])
            ),
            "excluded_dirs": _normalise_dirs(
                data.get("excluded_dirs", DEFAULT_CONFIG["excluded_dirs"])
            ),
            "max_file_size_kb": _coerce_int(
                data.get("max_file_size_kb", DEFAULT_CONFIG["max_file_size_kb"]),
                DEFAULT_CONFIG["max_file_size_kb"],
            ),
            "output_auto_save": _coerce_bool(
                data.get("output_auto_save", DEFAULT_CONFIG["output_auto_save"]),
                DEFAULT_CONFIG["output_auto_save"],
            ),
            "output_folder": (
                data.get("output_folder") or DEFAULT_CONFIG["output_folder"]
            ),
        }

    def save(self):
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except OSError:
            # Nothing useful to do if the config cannot be persisted; the
            # in-memory values still work for this session.
            pass

    
    @property
    def text_extensions(self) -> Set[str]:
        return set(self.data.get("text_extensions", DEFAULT_CONFIG["text_extensions"]))
    
    @text_extensions.setter
    def text_extensions(self, value: List[str]):
        self.data["text_extensions"] = _normalise_extensions(value)
        self.save()
    
    @property
    def excluded_dirs(self) -> Set[str]:
        return set(self.data.get("excluded_dirs", DEFAULT_CONFIG["excluded_dirs"]))
    
    @excluded_dirs.setter
    def excluded_dirs(self, value: List[str]):
        self.data["excluded_dirs"] = _normalise_dirs(value)
        self.save()
    
    @property
    def max_file_size_kb(self) -> int:
        return self.data.get("max_file_size_kb", DEFAULT_CONFIG["max_file_size_kb"])
    
    @max_file_size_kb.setter
    def max_file_size_kb(self, value: int):
        self.data["max_file_size_kb"] = _coerce_int(
            value, DEFAULT_CONFIG["max_file_size_kb"]
        )
        self.save()
    
    @property
    def output_auto_save(self) -> bool:
        return self.data.get("output_auto_save", DEFAULT_CONFIG["output_auto_save"])
    
    @output_auto_save.setter
    def output_auto_save(self, value: bool):
        self.data["output_auto_save"] = _coerce_bool(
            value, DEFAULT_CONFIG["output_auto_save"]
        )
        self.save()
    
    @property
    def output_folder(self) -> str:
        return self.data.get("output_folder", DEFAULT_CONFIG["output_folder"])
    
    @output_folder.setter
    def output_folder(self, value: str):
        self.data["output_folder"] = (
            value.strip()
            if isinstance(value, str) and value.strip()
            else DEFAULT_CONFIG["output_folder"]
        )
        self.save()

    def reload(self) -> "Config":
        """Re-read the config from disk, discarding any in-memory edits."""
        self.data = {}
        self.load()
        return self


# Singleton instance
_config: Config = None

def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config


def reload_config() -> Config:
    """Discard the singleton and rebuild it from disk."""
    global _config
    _config = Config()
    return _config