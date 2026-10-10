"""Apply file changes in-place or to a new folder copy, or create a brand‑new project.

The guiding rule matches the parser's: **never write something we do not
understand.**  A change that cannot be applied safely is reported and skipped
rather than half-applied, because a half-applied patch is much harder to
notice -- and to undo -- than one that was refused outright.
"""

import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from utils import get_excluded_dirs


class ApplyReport:
    """What happened while applying changes, for display in the UI."""

    def __init__(self) -> None:
        self.applied: List[str] = []
        self.skipped: List[str] = []

    def note_applied(self, path: str) -> None:
        self.applied.append(path)

    def note_skipped(self, path: str, reason: str) -> None:
        self.skipped.append(f"{path}: {reason}")

    @property
    def ok(self) -> bool:
        return not self.skipped

    def summary(self) -> str:
        lines = [f"Applied {len(self.applied)} change(s)."]
        if self.skipped:
            lines.append(
                f"\nSkipped {len(self.skipped)} change(s) that could not be applied "
                f"safely:\n"
            )
            lines.extend(f"  • {s}" for s in self.skipped)
        return "\n".join(lines)


def _resolve_within(root: Path, rel_path: str) -> Optional[Path]:
    """Resolve ``rel_path`` under ``root``, or return None if it escapes.

    Backslashes are accepted too, so a path the AI produced on Windows still
    lines up with the forward-slash relative paths recorded at export time.
    """
    candidate = Path(str(rel_path).replace("\\", "/"))
    target = (root / candidate).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


class ChangeApplier:
    @staticmethod
    def apply_inplace(project_root: Path, changes: Dict[str, Dict],
                      original_contents: Optional[Dict[str, str]] = None,
                      original_encodings: Optional[Dict[str, str]] = None) -> ApplyReport:
        """Modify the original project, after creating a timestamped backup."""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = project_root.parent / f"{project_root.name}_backup_{stamp}"
        # Guard against a collision if two runs land in the same second.
        suffix = 1
        while backup_dir.exists():
            backup_dir = (
                project_root.parent / f"{project_root.name}_backup_{stamp}_{suffix}"
            )
            suffix += 1

        shutil.copytree(project_root, backup_dir, symlinks=True,
                        ignore=shutil.ignore_patterns(*get_excluded_dirs()))
        print(f"Backup created at {backup_dir}")

        report = _apply_changes_to(
            project_root, changes, original_contents or {}, original_encodings
        )
        report.note_applied(f"(backup of the original project saved to {backup_dir})")
        return report

    @staticmethod
    def export_to_new(project_root: Path, dest_root: Path, changes: Dict[str, Dict],
                      original_contents: Optional[Dict[str, str]] = None,
                      original_encodings: Optional[Dict[str, str]] = None) -> ApplyReport:
        """Copy the project to a new folder, then apply changes there."""
        resolved_dest = dest_root.resolve()
        resolved_src = project_root.resolve()

        # Check the relationship *before* existence: pointing the destination
        # at the source itself exists by definition, and the user deserves the
        # "that's the source folder" message rather than "already exists".
        if resolved_dest == resolved_src:
            raise ValueError("Destination cannot be the source project folder itself.")
        # is_relative_to() needs no exception juggling and cannot be fooled by
        # an unrelated message that merely contains the word "relative".
        if resolved_dest.is_relative_to(resolved_src):
            raise ValueError("Destination cannot be inside the source project folder.")

        if dest_root.exists():
            raise FileExistsError(f"Destination {dest_root} already exists.")

        def ignore_func(directory, contents):
            excluded = get_excluded_dirs()
            return [c for c in contents if c in excluded]

        shutil.copytree(project_root, dest_root, symlinks=True, ignore=ignore_func)
        return _apply_changes_to(
            dest_root, changes, original_contents or {}, original_encodings
        )

    @staticmethod
    def create_new(dest_root: Path, changes: Dict[str, Dict]) -> ApplyReport:
        """Create a new project at dest_root from scratch using the changes."""
        if dest_root.exists():
            raise FileExistsError(
                f"Destination {dest_root} already exists. Choose a new path."
            )
        dest_root.mkdir(parents=True, exist_ok=False)
        return _apply_changes_to(dest_root, changes, {})



def _split_content(content: str) -> List[str]:
    """Split patch content into lines without eating intentional blank lines.

    ``str.splitlines()`` silently discards trailing blank lines and also splits
    on Unicode line boundaries such as ``\\x0b``, ``\\x0c`` and ``\\u2028``, none
    of which are the newline this format is talking about.  Only ``\\n`` counts
    as a line break here.
    """
    return content.split("\n")


def _validate_patch_set(
    rel_path: str, patches: List[Dict], total_lines: int
) -> Tuple[List[Dict], List[str]]:
    """Return ``(usable_patches, problems)``.

    A patch that cannot be applied safely is reported so the caller can skip
    the file rather than apply half of it.  Survivors come back sorted
    bottom-up, which is what in-place replacement requires.
    """
    problems: List[str] = []
    staged: List[Dict] = []

    for patch in sorted(patches, key=lambda p: (p["start"], p["end"])):
        start, end = patch["start"], patch["end"]
        if start < 1:
            problems.append(f"range {start}-{end} starts before line 1")
            continue
        if end < start:
            problems.append(
                f"range {start}-{end} is inverted (end before start), which would "
                f"insert text instead of replacing lines"
            )
            continue
        if end > total_lines:
            problems.append(
                f"range {start}-{end} runs past the end of the file, which has "
                f"{total_lines} lines"
            )
            continue
        staged.append(patch)

    # Individually valid ranges can still collide with each other, and applying
    # colliding patches would corrupt the file -- so reject every patch that
    # overlaps another one, in both directions.
    collided = set()
    for i, a in enumerate(staged):
        for b in staged[i + 1 :]:
            if a["start"] <= b["end"] and b["start"] <= a["end"]:
                collided.add(id(a))
                collided.add(id(b))
    for patch in staged:
        if id(patch) in collided:
            problems.append(
                f"range {patch['start']}-{patch['end']} overlaps another patch"
            )

    usable = [p for p in staged if id(p) not in collided]
    usable.sort(key=lambda p: p["start"], reverse=True)
    return usable, problems

def _write_file(target: Path, rel_path: str, content: str,
                original_encodings: Dict[str, str]) -> Optional[str]:
    """Write ``content`` in the encoding the file already had.

    Rewriting a latin-1 file as UTF-8 silently mangles every non-ASCII byte in
    it, so the encoding captured at export time is carried through and reused.
    Files the AI created brand new default to UTF-8.
    """
    encoding = original_encodings.get(rel_path, "utf-8")
    try:
        with open(target, "w", encoding=encoding, newline="") as fh:
            fh.write(content)
    except (OSError, UnicodeEncodeError, LookupError) as exc:
        return f"could not write the file ({exc})."
    return None


def _read_original(rel_path: str,
                   original_contents: Dict[str, str]) -> Tuple[str, Optional[str]]:
    """Fetch the original text, tolerating slash-style drift in the keys."""
    if rel_path in original_contents:
        return original_contents[rel_path], None
    alt = rel_path.replace("\\", "/")
    if alt in original_contents:
        return original_contents[alt], None
    return "", (
        "no original content was captured for this file, so line patches cannot be "
        "applied. Re-export the project first, or ask the AI for the whole file "
        "instead of [LINE] patches."
    )


def _build_content(rel_path: str, change: Dict,
                   original_contents: Dict[str, str]) -> Tuple[str, Optional[str]]:
    """Work out the final file text, or explain why we refuse to write it."""
    if "patches" in change:
        patches = change["patches"]
        if not patches:
            return "", "the block contained no usable patches."

        original, problem = _read_original(rel_path, original_contents)
        if problem is not None:
            return "", problem

        new_lines = original.split("\n")
        usable, problems = _validate_patch_set(rel_path, patches, len(new_lines))
        if problems:
            return "", (
                "invalid patches -- "
                + "; ".join(problems)
                + ". Nothing was written for this file."
            )
        if not usable:
            return "", "no patches were safe to apply."

        for patch in usable:
            new_lines[patch["start"] - 1 : patch["end"]] = _split_content(
                patch["content"]
            )
        return "\n".join(new_lines), None

    if change.get("content") is not None:
        return change["content"], None

    # Neither patches nor content: writing an empty string here would truncate
    # a real file, so refuse instead.
    return "", (
        "the change carried neither content nor patches. Refusing to write an empty "
        "file over it."
    )


def _apply_changes_to(root: Path, changes: Dict[str, Dict],
                      original_contents: Dict[str, str],
                      original_encodings: Optional[Dict[str, str]] = None) -> ApplyReport:
    """Modify/create/delete files inside `root` according to `changes`."""
    report = ApplyReport()
    root = root.resolve()
    encodings = original_encodings or {}

    for rel_path, change in changes.items():
        action = change.get("action", "modify")

        target = _resolve_within(root, rel_path)
        if target is None:
            report.note_skipped(rel_path, "path escapes the project directory.")
            continue

        if action == "delete":
            if target.is_dir():
                report.note_skipped(rel_path, "it is a directory, not a file.")
                continue
            if target.exists() or target.is_symlink():
                try:
                    target.unlink()
                except OSError as exc:
                    report.note_skipped(rel_path, f"could not delete it ({exc}).")
                    continue
                report.note_applied(rel_path)
            else:
                report.note_skipped(rel_path, "file does not exist, nothing to delete.")
            continue

        final_content, problem = _build_content(rel_path, change, original_contents)
        if problem is not None:
            report.note_skipped(rel_path, problem)
            continue

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            report.note_skipped(rel_path, f"could not create its folder ({exc}).")
            continue

        problem = _write_file(target, rel_path, final_content, encodings)
        if problem is not None:
            report.note_skipped(rel_path, problem)
            continue

        report.note_applied(rel_path)

    return report

