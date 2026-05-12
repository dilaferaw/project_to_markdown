"""JSON‑based configuration for ProjectToMarkdown."""

import json
import os
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


class Config:
    """Application configuration loaded from a JSON file."""
    
    def __init__(self):
        self.config_dir = Path.home() / ".config" / "project-to-markdown"
        self.config_file = self.config_dir / "config.json"
        self.data = {}
        self.load()
    
    def load(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except (json.JSONDecodeError, PermissionError):
                self.data = {}
        # Merge with defaults for any missing keys
        for key, default in DEFAULT_CONFIG.items():
            if key not in self.data:
                self.data[key] = default
        self.save()
    
    def save(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
    
    @property
    def text_extensions(self) -> Set[str]:
        return set(self.data.get("text_extensions", DEFAULT_CONFIG["text_extensions"]))
    
    @text_extensions.setter
    def text_extensions(self, value: List[str]):
        self.data["text_extensions"] = value
        self.save()
    
    @property
    def excluded_dirs(self) -> Set[str]:
        return set(self.data.get("excluded_dirs", DEFAULT_CONFIG["excluded_dirs"]))
    
    @excluded_dirs.setter
    def excluded_dirs(self, value: List[str]):
        self.data["excluded_dirs"] = value
        self.save()
    
    @property
    def max_file_size_kb(self) -> int:
        return self.data.get("max_file_size_kb", DEFAULT_CONFIG["max_file_size_kb"])
    
    @max_file_size_kb.setter
    def max_file_size_kb(self, value: int):
        self.data["max_file_size_kb"] = value
        self.save()
    
    @property
    def output_auto_save(self) -> bool:
        return self.data.get("output_auto_save", DEFAULT_CONFIG["output_auto_save"])
    
    @output_auto_save.setter
    def output_auto_save(self, value: bool):
        self.data["output_auto_save"] = value
        self.save()
    
    @property
    def output_folder(self) -> str:
        return self.data.get("output_folder", DEFAULT_CONFIG["output_folder"])
    
    @output_folder.setter
    def output_folder(self, value: str):
        self.data["output_folder"] = value
        self.save()


# Singleton instance
_config: Config = None

def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config