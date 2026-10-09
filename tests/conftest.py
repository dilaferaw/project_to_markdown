"""Shared pytest fixtures."""

import sys
from pathlib import Path

import pytest

# Make the project root importable, so ``core.*`` and ``utils`` resolve no
# matter which directory pytest is invoked from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def make_project(tmp_path):
    """Return a factory that builds a throwaway project tree.

    Usage::

        root = make_project({"a.py": "line1\nline2\n", "pkg/b.py": "x\n"})
    """

    def _build(files: dict):
        for rel, content in files.items():
            target = tmp_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content, encoding="utf-8")
        return tmp_path

    return _build
