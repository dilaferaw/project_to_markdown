"""Shared constants and utility functions – backed by JSON config."""

from core.config import get_config

# Load config once at import time
_cfg = get_config()
DEFAULT_TEXT_EXTENSIONS = _cfg.text_extensions
DEFAULT_EXCLUDED_DIRS   = _cfg.excluded_dirs
MAX_FILE_SIZE_KB        = _cfg.max_file_size_kb


def reload_config():
    """Update the module‑level constants from the config file.

    Call this after changing settings at runtime.

    Note: modules that did ``from utils import DEFAULT_EXCLUDED_DIRS`` keep the
    *old object* no matter what happens here, which is why the core modules now
    call :func:`get_text_extensions`, :func:`get_excluded_dirs` and
    :func:`get_max_file_size_kb` instead of importing the constants directly.
    """
    global DEFAULT_TEXT_EXTENSIONS, DEFAULT_EXCLUDED_DIRS, MAX_FILE_SIZE_KB
    fresh = get_config()
    DEFAULT_TEXT_EXTENSIONS = fresh.text_extensions
    DEFAULT_EXCLUDED_DIRS   = fresh.excluded_dirs
    MAX_FILE_SIZE_KB        = fresh.max_file_size_kb


# --- Live accessors (always reflect the current config) ---------------------

def get_text_extensions():
    """Text file extensions as currently configured."""
    return get_config().text_extensions


def get_excluded_dirs():
    """Directory names to skip, as currently configured."""
    return get_config().excluded_dirs


def get_max_file_size_kb() -> int:
    """Maximum file size to scan, in KB, as currently configured."""
    return get_config().max_file_size_kb


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