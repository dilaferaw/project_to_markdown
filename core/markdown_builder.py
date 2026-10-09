"""Builds the full project markdown (tree + file contents)."""

import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from core.file_utils import generate_tree, is_text_file
from utils import get_excluded_dirs


# Extensions that map onto the language hints shown in the markdown fences.
LANG_MAP = {
    "py": "python", "rs": "rust", "js": "javascript", "ts": "typescript",
    "html": "html", "css": "css", "json": "json", "yaml": "yaml",
    "yml": "yaml", "md": "markdown", "c": "c", "cpp": "cpp", "java": "java",
    "go": "go", "rb": "ruby", "php": "php", "swift": "swift",
    "kt": "kotlin", "sh": "bash", "bash": "bash", "zsh": "bash",
    "sql": "sql", "lua": "lua", "toml": "toml", "xml": "xml",
    "dart": "dart", "ex": "elixir", "exs": "elixir", "hs": "haskell",
    "scala": "scala", "r": "r", "pl": "perl", "vim": "vim",
}


def collect_files(project_root: Path) -> List[Tuple[str, Path]]:
    """Return every includable file as a sorted list of ``(rel_path, abs_path)``.

    Both the scan and the export go through this one function, so the file the
    user ticks in the tree, the order files appear in the markdown, and the
    ``[file-NNN]`` ids the AI cites can never drift apart.  Directories are
    sorted too, which keeps the output stable between runs -- the old export
    left ``dirs`` unsorted, so file ids shuffled around and any line numbers the
    AI quoted could refer to a different file the next time.
    """
    project_root = Path(project_root)
    excluded = get_excluded_dirs()
    collected: List[Tuple[str, Path]] = []

    for root, dirs, files in os.walk(project_root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in excluded)
        rel_root = Path(root).relative_to(project_root)
        for fname in sorted(files):
            fpath = Path(root) / fname
            if is_text_file(fpath):
                collected.append((str(rel_root / fname), fpath))

    collected.sort(key=lambda pair: pair[0])
    return collected


def scan_project_files(project_root: Path) -> List[str]:
    """Return sorted list of relative file paths that would be included in an export."""
    return [rel for rel, _ in collect_files(project_root)]


def _detect_encoding(raw: bytes) -> str:
    """Pick an encoding that round-trips the original bytes.

    Reading with a fixed ``errors='replace'`` used to bake U+FFFD into the
    stored original, and the applier then wrote those replacement characters
    back out -- permanently destroying a latin-1 file's contents the first time
    anyone patched it.  latin-1 is the last resort precisely because it maps
    every byte 1:1, so the round-trip stays lossless.
    """
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    for candidate in ("cp1252", "latin-1"):
        try:
            raw.decode(candidate)
            return candidate
        except (UnicodeDecodeError, LookupError):
            continue
    return "latin-1"


def _read_file(full_path: Path) -> Tuple[str, str]:
    """Read a file as text, returning ``(content, encoding)``.

    The encoding travels alongside the content so the applier can write the file
    back in the same encoding it arrived in.
    """
    try:
        raw = full_path.read_bytes()
    except OSError:
        return "[ERROR READING FILE]", "utf-8"

    encoding = _detect_encoding(raw)
    try:
        return raw.decode(encoding), encoding
    except (UnicodeDecodeError, LookupError):
        # latin-1 cannot fail, so this is effectively unreachable -- but a hard
        # failure here must not take the whole export down with it.
        return raw.decode("latin-1", errors="replace"), "latin-1"


def _number_lines(raw_content: str) -> str:
    """Prefix each line with its 1-based number, as the AI is told to read it.

    ``str.split('\\n')`` yields a trailing empty element for a file ending in a
    newline, which used to inflate the count by one: the AI would be told a
    3-line file had 4 lines and would cite a line that does not exist.  The
    phantom element is dropped for numbering only; the content the applier
    patches keeps its own trailing newline.
    """
    lines = raw_content.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]

    width = max(4, len(str(len(lines))))
    return "\n".join(f"{i:>{width}}│{line}" for i, line in enumerate(lines, start=1))


def export_project(project_root: Path, include_only: Optional[Set[str]] = None) -> tuple:
    """Generate the complete markdown representation of the project.

    Returns ``(markdown_string, dict_of_original_contents, dict_of_encodings)``.

    If ``include_only`` is provided, only files whose relative path is in that
    set are included in the File Contents section (the tree still shows the full
    project structure).
    """
    tree_str = generate_tree(project_root)

    parts = [
        "# Project Structure\n",
        "```\n" + tree_str + "\n```\n\n",
        "# File Contents\n"
    ]

    collected = collect_files(project_root)
    if include_only is not None:
        wanted = {str(p).replace("\\", "/") for p in include_only}
        collected = [(rp, fp) for rp, fp in collected if rp in wanted]

    # Store original content and encoding for later patching
    original_contents: Dict[str, str] = {}
    original_encodings: Dict[str, str] = {}

    for file_counter, (rel_path, full_path) in enumerate(collected, start=1):
        raw_content, encoding = _read_file(full_path)
        original_contents[rel_path] = raw_content
        original_encodings[rel_path] = encoding

        ext = Path(rel_path).suffix.lstrip(".").lower()
        lang = LANG_MAP.get(ext, "")

        file_id = f"[file-{file_counter:03d}]"
        parts.append(f"## `{rel_path}` {file_id}\n")
        parts.append(f"```{lang}\n{_number_lines(raw_content)}\n```\n\n")

    return "".join(parts), original_contents, original_encodings
