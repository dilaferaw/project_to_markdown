"""Tests for core.applier.

The rule under test: a change that cannot be applied safely is skipped and
reported, never half-applied.  A half-applied patch is far harder to notice --
and to undo -- than one that was refused.
"""

import pytest

from core.applier import (
    ApplyReport,
    ChangeApplier,
    _apply_changes_to,
    _split_content,
    _validate_patch_set,
)

ORIGINAL = "l1\nl2\nl3\nl4\nl5\nl6\n"


@pytest.fixture
def project(tmp_path):
    """A project containing a.py with six numbered lines."""
    (tmp_path / "a.py").write_text(ORIGINAL, encoding="utf-8")
    return tmp_path


def read(project, name="a.py"):
    return (project / name).read_text(encoding="utf-8")


def apply(project, changes, contents=None, encodings=None):
    return _apply_changes_to(
        project, changes, contents if contents is not None else {}, encodings
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestValidChanges:
    def test_whole_file_content_replaces_the_file(self, project):
        report = apply(project, {"a.py": {"action": "modify", "content": "brand new\n"}})
        assert read(project) == "brand new\n"
        assert report.ok

    def test_creates_a_missing_file(self, project):
        report = apply(project, {"new.py": {"action": "modify", "content": "x = 1\n"}})
        assert read(project, "new.py") == "x = 1\n"
        assert report.ok

    def test_creates_missing_parent_directories(self, project):
        apply(project, {"deep/nested/new.py": {"action": "modify", "content": "x\n"}})
        assert (project / "deep" / "nested" / "new.py").read_text() == "x\n"

    def test_single_line_patch(self, project):
        report = apply(
            project,
            {"a.py": {"action": "modify", "patches": [
                {"start": 2, "end": 2, "content": "TWO"}]}},
            {"a.py": ORIGINAL},
        )
        assert read(project) == "l1\nTWO\nl3\nl4\nl5\nl6\n"
        assert report.ok

    def test_range_patch(self, project):
        apply(
            project,
            {"a.py": {"action": "modify", "patches": [
                {"start": 2, "end": 4, "content": "A\nB"}]}},
            {"a.py": ORIGINAL},
        )
        assert read(project) == "l1\nA\nB\nl5\nl6\n"

    def test_multiple_non_overlapping_patches(self, project):
        apply(
            project,
            {"a.py": {"action": "modify", "patches": [
                {"start": 2, "end": 3, "content": "AAA"},
                {"start": 5, "end": 6, "content": "BBB"}]}},
            {"a.py": ORIGINAL},
        )
        assert read(project) == "l1\nAAA\nl4\nBBB\n"

    def test_patches_given_out_of_order_still_apply(self, project):
        apply(
            project,
            {"a.py": {"action": "modify", "patches": [
                {"start": 5, "end": 6, "content": "BBB"},
                {"start": 2, "end": 3, "content": "AAA"}]}},
            {"a.py": ORIGINAL},
        )
        assert read(project) == "l1\nAAA\nl4\nBBB\n"

    def test_adjacent_patches_do_not_count_as_overlapping(self, project):
        apply(
            project,
            {"a.py": {"action": "modify", "patches": [
                {"start": 2, "end": 2, "content": "A"},
                {"start": 3, "end": 3, "content": "B"}]}},
            {"a.py": ORIGINAL},
        )
        assert read(project) == "l1\nA\nB\nl4\nl5\nl6\n"

    def test_delete_removes_the_file(self, project):
        report = apply(project, {"a.py": {"action": "delete", "content": None}})
        assert not (project / "a.py").exists()
        assert "a.py" in report.applied

    def test_patch_that_expands_the_file(self, project):
        apply(
            project,
            {"a.py": {"action": "modify", "patches": [
                {"start": 2, "end": 2, "content": "A\nB\nC"}]}},
            {"a.py": ORIGINAL},
        )
        assert read(project) == "l1\nA\nB\nC\nl3\nl4\nl5\nl6\n"

    def test_patch_that_shrinks_the_file(self, project):
        apply(
            project,
            {"a.py": {"action": "modify", "patches": [
                {"start": 2, "end": 5, "content": "ONLY"}]}},
            {"a.py": ORIGINAL},
        )
        assert read(project) == "l1\nONLY\nl6\n"


# ---------------------------------------------------------------------------
# Bug regressions -- each of these destroyed or corrupted data before
# ---------------------------------------------------------------------------

class TestUnsafePatchesAreSkippedNotHalfApplied:
    def test_overlapping_patches_leave_the_file_untouched(self, project):
        report = apply(
            project,
            {"a.py": {"action": "modify", "patches": [
                {"start": 2, "end": 3, "content": "AAA"},
                {"start": 4, "end": 5, "content": "BBB"},
                {"start": 2, "end": 5, "content": "WHOLE"}]}},
            {"a.py": ORIGINAL},
        )
        assert read(project) == ORIGINAL
        assert not report.ok
        assert any("overlap" in s for s in report.skipped)

    def test_inverted_range_is_skipped(self, project):
        # This used to *insert* text, growing the file and shifting everything.
        report = apply(
            project,
            {"a.py": {"action": "modify", "patches": [
                {"start": 6, "end": 2, "content": "X"}]}},
            {"a.py": ORIGINAL},
        )
        assert read(project) == ORIGINAL
        assert any("inverted" in s for s in report.skipped)

    def test_out_of_bounds_range_is_skipped(self, project):
        report = apply(
            project,
            {"a.py": {"action": "modify", "patches": [
                {"start": 10, "end": 12, "content": "X"}]}},
            {"a.py": ORIGINAL},
        )
        assert read(project) == ORIGINAL
        assert any("past the end" in s for s in report.skipped)

    def test_range_starting_before_line_one_is_skipped(self, project):
        report = apply(
            project,
            {"a.py": {"action": "modify", "patches": [
                {"start": 0, "end": 1, "content": "X"}]}},
            {"a.py": ORIGINAL},
        )
        assert read(project) == ORIGINAL
        assert any("before line 1" in s for s in report.skipped)

    def test_one_bad_patch_invalidates_the_whole_file(self, project):
        # Partial application is worse than none: the user cannot tell which
        # patches actually landed.
        report = apply(
            project,
            {"a.py": {"action": "modify", "patches": [
                {"start": 2, "end": 2, "content": "GOOD"},
                {"start": 99, "end": 100, "content": "BAD"}]}},
            {"a.py": ORIGINAL},
        )
        assert read(project) == ORIGINAL
        assert "GOOD" not in read(project)


class TestRefusesToDestroyFiles:
    def test_patch_without_original_content_is_skipped(self, project):
        # Used to write an empty file, silently destroying the real one.
        report = apply(
            project,
            {"a.py": {"action": "modify", "patches": [
                {"start": 1, "end": 1, "content": "x = 1"}]}},
            {},
        )
        assert read(project) == ORIGINAL
        assert any("no original content" in s for s in report.skipped)

    def test_change_with_no_content_does_not_truncate(self, project):
        (project / "precious.py").write_text("important code\n", encoding="utf-8")
        report = apply(project, {"precious.py": {"action": "modify"}})
        assert read(project, "precious.py") == "important code\n"
        assert any("neither content nor patches" in s for s in report.skipped)

    def test_empty_patch_list_is_skipped(self, project):
        report = apply(
            project,
            {"a.py": {"action": "modify", "patches": []}},
            {"a.py": ORIGINAL},
        )
        assert read(project) == ORIGINAL
        assert not report.ok

    def test_deleting_a_directory_is_refused(self, project):
        (project / "src").mkdir()
        report = apply(project, {"src": {"action": "delete", "content": None}})
        assert (project / "src").is_dir()
        assert any("directory" in s for s in report.skipped)

    def test_deleting_a_missing_file_is_reported(self, project):
        report = apply(project, {"ghost.py": {"action": "delete", "content": None}})
        assert any("does not exist" in s for s in report.skipped)




class TestPathTraversal:
    def test_parent_escape_is_blocked(self, project):
        report = apply(project, {"../escape.txt": {"action": "modify", "content": "x"}})
        assert not (project.parent / "escape.txt").exists()
        assert any("escapes" in s for s in report.skipped)

    def test_nested_escape_is_blocked(self, project):
        report = apply(
            project, {"a/../../escape.txt": {"action": "modify", "content": "x"}}
        )
        assert not (project.parent / "escape.txt").exists()
        assert report.skipped


class TestEncodingPreservation:
    def test_cp1252_bytes_survive_a_patch(self, project):
        # Reading with errors='replace' used to bake U+FFFD into the original,
        # and the applier wrote it back out, destroying the file for good.
        (project / "latin.py").write_bytes(b"# caf\xe9\nprint('ok')\n")
        report = apply(
            project,
            {"latin.py": {"action": "modify", "patches": [
                {"start": 2, "end": 2, "content": "print('changed')"}]}},
            {"latin.py": "# caf\xe9\nprint('ok')\n"},
            {"latin.py": "cp1252"},
        )
        assert report.ok
        assert (project / "latin.py").read_bytes() == b"# caf\xe9\nprint('changed')\n"

    def test_new_files_default_to_utf8(self, project):
        apply(project, {"new.py": {"action": "modify", "content": "x\n"}})
        assert (project / "new.py").read_bytes() == b"x\n"


class TestWindowsStylePaths:
    def test_backslash_path_resolves(self, project):
        (project / "pkg").mkdir()
        (project / "pkg" / "m.py").write_text("l1\nl2\n", encoding="utf-8")
        report = apply(
            project,
            {"pkg\\m.py": {"action": "modify", "patches": [
                {"start": 1, "end": 1, "content": "CHANGED"}]}},
            {"pkg/m.py": "l1\nl2\n"},
        )
        assert report.ok
        assert (project / "pkg" / "m.py").read_text() == "CHANGED\nl2\n"


class TestHelpers:
    def test_split_content_only_splits_on_newline(self):
        # str.splitlines() also breaks on \x0b and , which are not line
        # separators in this format.
        assert _split_content("a\x0bb") == ["a\x0bb"]

    def test_split_content_keeps_trailing_blank_lines(self):
        assert _split_content("x\n\n\n") == ["x", "", "", ""]

    def test_split_content_on_empty_string(self):
        assert _split_content("") == [""]

    def test_validate_patch_set_returns_sorted_bottom_up(self):
        usable, problems = _validate_patch_set(
            "a.py",
            [{"start": 2, "end": 2, "content": "A"},
             {"start": 5, "end": 6, "content": "B"}],
            10,
        )
        assert problems == []
        assert [(p["start"], p["end"]) for p in usable] == [(5, 6), (2, 2)]


class TestApplyReport:
    def test_ok_is_false_when_anything_was_skipped(self):
        report = ApplyReport()
        report.note_applied("a.py")
        assert report.ok
        report.note_skipped("b.py", "because")
        assert not report.ok

    def test_summary_counts_both_lists(self):
        report = ApplyReport()
        report.note_applied("a.py")
        report.note_skipped("b.py", "it was unsafe")
        summary = report.summary()
        assert "Applied 1 change" in summary
        assert "Skipped 1 change" in summary
        assert "b.py" in summary

    def test_empty_summary_still_reads_sensibly(self):
        assert "Applied 0 change" in ApplyReport().summary()



class TestChangeApplierEntryPoints:
    def test_export_to_new_copies_then_applies(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("original\n", encoding="utf-8")
        dest = tmp_path / "out"

        report = ChangeApplier.export_to_new(
            src, dest, {"a.py": {"action": "modify", "content": "changed\n"}}
        )
        assert (dest / "a.py").read_text() == "changed\n"
        assert report.ok
        # The source project is left untouched.
        assert (src / "a.py").read_text() == "original\n"

    def test_export_into_the_source_folder_is_refused(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        with pytest.raises(ValueError, match="inside the source"):
            ChangeApplier.export_to_new(
                src, src / "nested", {"a.py": {"action": "modify", "content": "x"}}
            )

    def test_export_onto_the_source_itself_is_refused(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        with pytest.raises(ValueError):
            ChangeApplier.export_to_new(src, src, {})

    def test_export_to_an_existing_destination_is_refused(self, tmp_path):
        src, dest = tmp_path / "src", tmp_path / "dest"
        src.mkdir()
        dest.mkdir()
        with pytest.raises(FileExistsError):
            ChangeApplier.export_to_new(src, dest, {})

    def test_create_new_builds_a_project_from_scratch(self, tmp_path):
        dest = tmp_path / "brand_new"
        report = ChangeApplier.create_new(
            dest, {"app.py": {"action": "modify", "content": "print('hi')\n"}}
        )
        assert (dest / "app.py").read_text() == "print('hi')\n"
        assert report.ok

    def test_create_new_refuses_an_existing_destination(self, tmp_path):
        dest = tmp_path / "existing"
        dest.mkdir()
        with pytest.raises(FileExistsError):
            ChangeApplier.create_new(dest, {})

    def test_apply_inplace_backs_up_first(self, tmp_path):
        src = tmp_path / "proj"
        src.mkdir()
        (src / "a.py").write_text("original\n", encoding="utf-8")

        report = ChangeApplier.apply_inplace(
            src, {"a.py": {"action": "modify", "content": "changed\n"}}
        )
        assert (src / "a.py").read_text() == "changed\n"
        assert report.ok
        backups = [p for p in tmp_path.iterdir() if "backup" in p.name]
        assert backups, "no backup was created"
        assert (backups[0] / "a.py").read_text() == "original\n"

    def test_apply_inplace_twice_does_not_collide_on_the_backup(self, tmp_path):
        src = tmp_path / "proj"
        src.mkdir()
        (src / "a.py").write_text("v1\n", encoding="utf-8")

        ChangeApplier.apply_inplace(
            src, {"a.py": {"action": "modify", "content": "v2\n"}}
        )
        ChangeApplier.apply_inplace(
            src, {"a.py": {"action": "modify", "content": "v3\n"}}
        )

        backups = sorted(p.name for p in tmp_path.iterdir() if "backup" in p.name)
        assert len(backups) == 2, backups
        assert (src / "a.py").read_text() == "v3\n"
