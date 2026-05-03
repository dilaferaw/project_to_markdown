"""File system utilities: text detection, tree generation."""

import os
import subprocess
from pathlib import Path
from utils import DEFAULT_TEXT_EXTENSIONS, DEFAULT_EXCLUDED_DIRS, MAX_FILE_SIZE_KB


def is_text_file(filepath: Path, check_size: bool = True) -> bool:
    """Return True if file is a readable text file (not binary, not too large)."""
    if check_size:
        try:
            size_kb = filepath.stat().st_size / 1024
            if size_kb > MAX_FILE_SIZE_KB:
                return False
        except OSError:
            return False

    # Strong hint: known extension
    if filepath.suffix.lower() in DEFAULT_TEXT_EXTENSIONS:
        return True

    # Fallback: check for null bytes in first 4 KB
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(4096)
            if b'\0' in chunk:
                return False
    except Exception:
        return False

    return True


def generate_tree(project_root: Path) -> str:
    """Return a string representation of the directory tree."""
    try:
        cmd = [
            "tree",
            "-a",
            "--gitignore",
            "-I", "|".join(DEFAULT_EXCLUDED_DIRS),
            "--noreport",
            "--charset=utf-8",
            str(project_root)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass

    # Fallback: pure Python tree
    tree_lines = [str(project_root)]
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in DEFAULT_EXCLUDED_DIRS]
        level = root.replace(str(project_root), "").count(os.sep)
        indent = "│   " * level + "├── " if level > 0 else ""
        folder_name = os.path.basename(root) if level > 0 else "."
        if level > 0:
            tree_lines.append(f"{indent}{folder_name}/")
        sub_indent = "│   " * (level + 1)
        for file in files:
            tree_lines.append(f"{sub_indent}├── {file}")
    return "\n".join(tree_lines)