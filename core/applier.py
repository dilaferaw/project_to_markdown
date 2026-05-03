"""Apply file changes in-place or to a new folder copy, or create a brand‑new project."""

import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict
from utils import DEFAULT_EXCLUDED_DIRS


class ChangeApplier:
    @staticmethod
    def apply_inplace(project_root: Path, changes: Dict[str, Dict],
                      original_contents: Dict[str, str]):
        """Modify the original project, after creating a timestamped backup."""
        backup_dir = project_root.parent / f"{project_root.name}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copytree(project_root, backup_dir, symlinks=True, ignore=shutil.ignore_patterns(*DEFAULT_EXCLUDED_DIRS))
        print(f"Backup created at {backup_dir}")
        _apply_changes_to(project_root, changes, original_contents)

    @staticmethod
    def export_to_new(project_root: Path, dest_root: Path, changes: Dict[str, Dict],
                      original_contents: Dict[str, str]):
        """Copy the project to a new folder, then apply changes there."""
        if dest_root.exists():
            raise FileExistsError(f"Destination {dest_root} already exists.")

        def ignore_func(directory, contents):
            return [c for c in contents if c in DEFAULT_EXCLUDED_DIRS]

        shutil.copytree(project_root, dest_root, symlinks=True, ignore=ignore_func)
        _apply_changes_to(dest_root, changes, original_contents)

    @staticmethod
    def create_new(dest_root: Path, changes: Dict[str, Dict]):
        """Create a new project at dest_root from scratch using the changes."""
        if dest_root.exists():
            raise FileExistsError(f"Destination {dest_root} already exists. Choose a new path.")
        dest_root.mkdir(parents=True, exist_ok=False)
        _apply_changes_to(dest_root, changes, {})


def _apply_changes_to(root: Path, changes: Dict[str, Dict],
                      original_contents: Dict[str, str]):
    """Modify/create/delete files inside `root` according to `changes`."""
    for rel_path, change in changes.items():
        target = (root / rel_path).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            print(f"Skipping {rel_path}: path escapes root directory.")
            continue

        if change["action"] == "delete":
            if target.exists():
                target.unlink()
            continue

        # Determine the final content for modify/create
        if "patches" in change:
            # Patch mode: start from original content and apply line patches
            orig = original_contents.get(rel_path, "")
            new_lines = orig.split('\n')
            # Apply patches in reverse line order to avoid index shifting
            patches_sorted = sorted(change["patches"], key=lambda p: p["start"], reverse=True)
            for patch in patches_sorted:
                start_idx = patch["start"] - 1
                end_idx = patch["end"] - 1
                patch_lines = patch["content"].split('\n')
                new_lines[start_idx:end_idx+1] = patch_lines
            final_content = '\n'.join(new_lines)
        else:
            final_content = change.get("content", "")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(final_content, encoding='utf-8')