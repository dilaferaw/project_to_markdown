"""Shared constants and utility functions."""

DEFAULT_TEXT_EXTENSIONS = {
    ".py", ".rs", ".html", ".css", ".js", ".ts", ".json", ".yaml", ".yml",
    ".toml", ".md", ".txt", ".c", ".cpp", ".h", ".hpp", ".java", ".go",
    ".rb", ".php", ".swift", ".kt", ".kts", ".sh", ".bash", ".zsh",
    ".xml", ".svg", ".cf", ".conf", ".ini", ".cfg", ".sql", ".r", ".lua",
    ".pl", ".pm", ".dart", ".ex", ".exs", ".erl", ".hrl", ".hs", ".lhs",
    ".vim", ".emacs", ".dockerfile", ".makefile", ".cmake", ".gradle"
}

DEFAULT_EXCLUDED_DIRS = {
    ".git", "node_modules", "target", "venv", ".venv", "__pycache__",
    "build", "dist", ".next", ".nuxt", "out", "bin", "obj"
}

MAX_FILE_SIZE_KB = 500

# ── Token counting ────────────────────────────────────────────

def count_tokens(text: str) -> int:
    """
    Return an approximate token count for the given text.
    Uses tiktoken (cl100k_base encoding, used by GPT‑4, GPT‑3.5) if available;
    otherwise falls back to a rough character‑based estimate (len(text) // 4).
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        # Simple fallback – not accurate for non‑English or code,
        # but gives a ballpark figure for plain text.
        return max(1, len(text) // 4)
