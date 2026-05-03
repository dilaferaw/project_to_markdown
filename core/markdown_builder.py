"""Builds the full project markdown (tree + file contents)."""

import os
from pathlib import Path
from core.file_utils import generate_tree, is_text_file
from utils import DEFAULT_EXCLUDED_DIRS


def export_project(project_root: Path) -> tuple[str, dict]:
    """Generate the complete markdown representation of the project.
    Returns (markdown_string, dict_of_original_contents)."""
    tree_str = generate_tree(project_root)

    parts = [
        "# Project Structure\n",
        "```\n" + tree_str + "\n```\n\n",
        "# File Contents\n"
    ]

    collected = []
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in DEFAULT_EXCLUDED_DIRS]
        rel_root = Path(root).relative_to(project_root)
        for fname in sorted(files):
            fpath = Path(root) / fname
            if is_text_file(fpath):
                rel_path = str(rel_root / fname)
                collected.append((rel_path, fpath))

    # Store original content for later patching
    original_contents = {}

    # Generate incremental IDs for each file
    file_counter = 1
    for rel_path, full_path in collected:
        try:
            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                raw_content = f.read()
        except Exception:
            raw_content = "[ERROR READING FILE]"

        # Save original for patching
        original_contents[rel_path] = raw_content

        # Add line numbers
        lines = raw_content.split('\n')
        total = len(lines)
        width = max(4, len(str(total)))
        numbered_lines = []
        for i, line in enumerate(lines, start=1):
            numbered_lines.append(f"{i:>{width}}│{line}")
        content = '\n'.join(numbered_lines)

        ext = Path(rel_path).suffix.lstrip('.')
        lang_map = {
            "py": "python", "rs": "rust", "js": "javascript", "ts": "typescript",
            "html": "html", "css": "css", "json": "json", "yaml": "yaml",
            "md": "markdown", "c": "c", "cpp": "cpp", "java": "java",
            "go": "go", "rb": "ruby", "php": "php", "swift": "swift",
            "kt": "kotlin", "sh": "bash"
        }
        lang = lang_map.get(ext, "")

        file_id = f"[file-{file_counter:03d}]"
        parts.append(f"## `{rel_path}` {file_id}\n")
        parts.append(f"```{lang}\n{content}\n```\n\n")
        file_counter += 1

    return "".join(parts), original_contents