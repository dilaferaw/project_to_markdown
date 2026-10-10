"""File system utilities: text detection, tree generation."""

import os
import subprocess
from pathlib import Path
from utils import get_text_extensions, get_excluded_dirs, get_max_file_size_kb


# Characters that never legitimately appear in a text file, other than the
# whitespace we already allow (\t \n \r \f \v).  A file stuffed with these is
# binary whatever its extension claims.
_CONTROL_CHARS = bytes(b for b in range(32) if b not in (9, 10, 11, 12, 13))

# C1 controls: they never appear in real text in any single-byte encoding.
_C1_CHARS = bytes(range(0x80, 0xA0))

# Magic numbers for the binary formats people actually keep in a repo.  A
# NUL-byte check alone misses plenty of these -- a JPEG or PDF whose first few
# kilobytes happen to contain no zero byte is still very much a JPEG, and
# letting it through dumps kilobytes of noise into the prompt.
_MAGIC_NUMBERS = (
    b"\x89PNG\r\n\x1a\n",       # PNG
    b"\xff\xd8\xff",            # JPEG
    b"GIF87a", b"GIF89a",       # GIF
    b"BM",                      # BMP
    b"%PDF",                    # PDF
    b"PK\x03\x04",              # ZIP / docx / xlsx / jar
    b"PK\x05\x06",              # empty ZIP
    b"\x1f\x8b",                # gzip
    b"BZh",                     # bzip2
    b"\xfd7zXZ\x00",            # xz
    b"7z\xbc\xaf\x27\x1c",      # 7-Zip
    b"Rar!\x1a\x07",            # RAR (v4)
    b"\x04\x22\x4d\x18",        # RAR (v5)
    b"ustar",                   # tar (at offset 257)
    b"\x7fELF",                 # ELF executable / .so
    b"MZ",                      # PE / DLL / EXE
    b"\xca\xfe\xba\xbe",        # Java class / Mach-O fat binary
    b"\xcf\xfa\xed\xfe",        # Mach-O 64-bit
    b"\xce\xfa\xed\xfe",        # Mach-O 32-bit
    b"OggS",                    # Ogg
    b"RIFF",                    # WAV / AVI / WEBP
    b"ID3",                     # MP3 with ID3 tag
    b"\x00\x00\x01\x00",        # ICO
    b"\x00\x00\x02\x00",
    b"SQLite format 3\x00",     # SQLite
    b"\x25\x21PS",              # PostScript
)


def looks_binary(chunk: bytes) -> bool:
    """Heuristic binary sniffing on the first bytes of a file."""
    if not chunk:
        return False

    # An unambiguous UTF-16 BOM means text, not binary.
    if chunk.startswith((b"\xff\xfe", b"\xfe\xff")):
        return False

    if any(chunk.startswith(sig) for sig in _MAGIC_NUMBERS):
        return True
    # tar keeps its signature at a fixed offset rather than at byte 0.
    if chunk[257:262] == b"ustar":
        return True

    if b"\x00" in chunk:
        return True

    suspicious = sum(chunk.count(bytes([c])) for c in _CONTROL_CHARS)
    suspicious += sum(chunk.count(bytes([c])) for c in _C1_CHARS)
    return suspicious / len(chunk) > 0.10


def is_text_file(filepath: Path, check_size: bool = True) -> bool:
    """Return True if file is a readable text file (not binary, not too large)."""
    if check_size:
        try:
            size_kb = filepath.stat().st_size / 1024
            if size_kb > get_max_file_size_kb():
                return False
        except OSError:
            return False

    # Strong hint: known extension
    if filepath.suffix.lower() in get_text_extensions():
        return True

    # Fallback: sniff the first 4 KB
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(4096)
            if looks_binary(chunk):
                return False
    except OSError:
        return False

    return True



def _python_tree(project_root: Path) -> str:
    """Pure-Python fallback tree.

    Only used when the external ``tree`` binary is unavailable.  Note that this
    cannot honour ``.gitignore`` (only the ``tree`` binary can, via --gitignore),
    so the two paths are not identical -- see :func:`generate_tree`.
    """
    lines = [str(project_root)]
    for root, dirs, files in os.walk(project_root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in get_excluded_dirs())
        rel = os.path.relpath(root, project_root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1

        if rel != ".":
            indent = "│   " * (depth - 1)
            lines.append(f"{indent}├── {os.path.basename(root)}/")

        child_indent = "│   " * depth
        for name in sorted(files):
            lines.append(f"{child_indent}├── {name}")
    return "\n".join(lines)


def generate_tree(project_root: Path, timeout: int = 30) -> str:
    """Return a string representation of the directory tree.

    Caveat, and it matters: when the ``tree`` binary is present we pass
    ``--gitignore``, so the tree omits anything ``.gitignore`` excludes.  The
    File Contents section, however, is built from a plain ``os.walk`` and does
    *not* honour ``.gitignore``.  The two can therefore disagree -- most
    dangerously, a gitignored ``.env`` full of secrets would appear in File
    Contents but not in the tree.  Callers that care about consistency should
    build both sections from one shared file list; see
    :func:`core.markdown_builder.export_project`.
    """
    try:
        cmd = [
            "tree",
            "-a",
            "--gitignore",
            "-I", "|".join(sorted(get_excluded_dirs())),
            "--noreport",
            "--charset=utf-8",
            str(project_root)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return _python_tree(project_root)