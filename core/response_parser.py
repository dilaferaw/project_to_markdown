"""Parse the structured AI response and return a dictionary of changes.

Design rule: **never guess.**

An earlier version of this module fell back to "treat the block as raw file
content" whenever it failed to understand the markers.  That is what silently
wrote an AI's prose -- or a half-parsed ``[LINE]`` snippet -- over real source
files.  This version instead *rejects* any block it cannot fully understand and
reports why, so the user gets told instead of getting a corrupted repo.

The scanner is a line-oriented state machine rather than a pile of regexes.
That is what makes a missing ``FILE_END`` non-fatal: the block is closed at the
next ``FILE_START`` instead of swallowing every file that follows it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# Placeholders the AI is instructed to use instead of real backtick
# characters.  They are expanded *per file*, after the enclosing code fence
# has been stripped -- expanding them up front (as the old code did) made the
# fence-stripping regexes fight the AI's own content.
# --------------------------------------------------------------------------
BACK3_PLACEHOLDER = "[BACK3]"
BACK_PLACEHOLDER = "[BACK]"


def expand_backticks(text: str) -> str:
    """Turn the [BACK3]/[BACK] placeholders into real backticks."""
    return text.replace(BACK3_PLACEHOLDER, "```").replace(BACK_PLACEHOLDER, "`")


# --------------------------------------------------------------------------
# Marker patterns.  All are anchored to a whole line so that a marker
# appearing mid-line is treated as ordinary file content.
# --------------------------------------------------------------------------
FILE_START_RE = re.compile(r"^-{3,}\s*FILE_START\s*:\s*(.+?)\s*-{3,}\s*$", re.IGNORECASE)
FILE_END_RE = re.compile(r"^-{3,}\s*FILE_END\s*-{3,}\s*$", re.IGNORECASE)
DELETE_FILE_RE = re.compile(r"^-{3,}\s*DELETE_FILE\s*:\s*(.+?)\s*-{3,}\s*$", re.IGNORECASE)

# ``\b`` stops ``[CODEFOO]`` being read as a code marker, while the trailing
# ``(.*)\]`` lets a language tag that itself contains ``]`` through.
CODE_OPEN_RE = re.compile(r"^\[\s*CODE\b(.*)\]\s*$", re.IGNORECASE)
CODE_CLOSE_RE = re.compile(r"^\[\s*/\s*CODE\s*\]\s*$", re.IGNORECASE)
LINE_OPEN_RE = re.compile(r"^\[\s*LINE\s+(\d+)(?:\s*-\s*(\d+))?\s*\]\s*$", re.IGNORECASE)
LINE_CLOSE_RE = re.compile(
    r"^\[\s*/\s*LINE\s+(\d+)(?:\s*-\s*(\d+))?\s*\]\s*$", re.IGNORECASE
)

# A markdown fence line such as ``` or ```text.  The AI wraps its answer in
# one of these, and sometimes (incorrectly) wraps a single file block too.
FENCE_RE = re.compile(r"^\s*(?:`{3,}|~{3,})\s*[\w+.#-]*\s*$")

# Loose prefixes used only to produce a helpful "you malformed a tag" message.
_LINE_PREFIXES = ("[LINE", "[/LINE")
_CODE_PREFIXES = ("[CODE", "[/CODE")
# Any stray marker outside a [CODE] block is suspicious: it cannot be part of
# the file content, so it almost always means the AI mangled the structure.
_STRAY_PREFIXES = _LINE_PREFIXES + _CODE_PREFIXES

# Sentinel: the block is patch mode but at least one patch is invalid.
_INVALID = object()


@dataclass
class ParseResult:
    """Everything the parser learned, including what it refused to do."""

    changes: Dict[str, Dict] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def __bool__(self) -> bool:  # convenient "did anything parse?"
        return bool(self.changes)


def validate_patch(patch: Dict) -> Optional[str]:
    """Return a human-readable problem description, or None if the patch is sane."""
    start, end = patch["start"], patch["end"]
    if start < 1:
        return f"patch starts at line {start}, but lines are numbered from 1."
    if end < start:
        return (
            f"patch range {start}-{end} is inverted (end before start), which would "
            f"insert text instead of replacing lines."
        )
    return None



class AIResponseParser:
    """Convert an AI reply into file change instructions.

    Parameters
    ----------
    strict:
        When True (the default) any block that is not perfectly formed is
        rejected with an error instead of being guessed at.
    allow_legacy:
        When True, fall back to scraping bare ```lang path fences if the reply
        contains no PTM markers at all.  Off by default because that fallback
        happily rewrites files when the AI merely *mentions* a path.
    """

    def __init__(self, strict: bool = True, allow_legacy: bool = False):
        self.strict = strict
        self.allow_legacy = allow_legacy
        self.warnings: List[str] = []
        self.errors: List[str] = []

    # -- public API --------------------------------------------------------

    def parse(self, text: str) -> ParseResult:
        """Parse ``text`` and return a :class:`ParseResult`."""
        self.warnings = []
        self.errors = []
        result = ParseResult()

        if not text or not text.strip():
            return result

        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

        blocks, deletes = self._scan_blocks(lines)
        for path, body, lineno in blocks:
            self._process_block(result.changes, path, body, lineno)

        self._apply_deletes(result.changes, deletes)

        if not blocks and not deletes:
            if self.allow_legacy:
                self.warn(
                    "No PTM markers found; falling back to legacy ```lang path scraping."
                )
                for path, desc in self._legacy_fallback(text).items():
                    self._add(result.changes, path, desc)
            else:
                self.warn(
                    "No '--- FILE_START:' or '--- DELETE_FILE:' markers were found in the "
                    "response, so nothing could be parsed. Check that the AI followed the "
                    "PTM output format."
                )

        result.warnings = list(self.warnings)
        result.errors = list(self.errors)
        return result

    # -- scanning ----------------------------------------------------------

    def _scan_blocks(
        self, lines: List[str]
    ) -> Tuple[List[Tuple[str, List[str], int]], List[Tuple[str, int]]]:
        """Walk the lines once, collecting file blocks and delete directives.

        Returns ``(blocks, deletes)`` where each block is
        ``(path, body_lines, start_lineno)`` and each delete is ``(path, lineno)``.
        """
        blocks: List[Tuple[str, List[str], int]] = []
        deletes: List[Tuple[str, int]] = []

        cur_path: Optional[str] = None
        cur_lines: List[str] = []
        cur_lineno = 0

        def flush(missing_end: bool) -> None:
            nonlocal cur_path, cur_lines
            if missing_end:
                self.warn(
                    f"Line {cur_lineno}: missing '--- FILE_END ---' for '{cur_path}'. "
                    f"The block was closed automatically at the end of the response."
                )
            blocks.append((cur_path, cur_lines, cur_lineno))
            cur_path = None
            cur_lines = []

        for lineno, line in enumerate(lines, start=1):
            # ---- between blocks: only openers and deleters mean anything ----
            if cur_path is None:
                m = FILE_START_RE.match(line)
                if m:
                    cur_path = m.group(1).strip()
                    cur_lineno = lineno
                    cur_lines = []
                    continue
                m = DELETE_FILE_RE.match(line)
                if m:
                    deletes.append((m.group(1).strip(), lineno))
                continue

            # ---- inside a FILE_START / FILE_END block ----
            if FILE_END_RE.match(line):
                blocks.append((cur_path, cur_lines, cur_lineno))
                cur_path = None
                cur_lines = []
                continue

            m = FILE_START_RE.match(line)
            if m:
                # The previous block never got its FILE_END.  Close it *here*
                # instead of letting it swallow this block and every block
                # after it, which is what the old forward-scanning regex did.
                next_path = m.group(1).strip()
                self.warn(
                    f"Line {lineno}: '--- FILE_START: {next_path} ---' started before "
                    f"'{cur_path}' was closed with '--- FILE_END ---'. "
                    f"Closed '{cur_path}' after line {lineno - 1} and carried on."
                )
                blocks.append((cur_path, cur_lines, cur_lineno))
                cur_path = next_path
                cur_lineno = lineno
                cur_lines = []
                continue

            m = DELETE_FILE_RE.match(line)
            if m:
                # Inside a block this is *content*, not a directive.  Honouring
                # it used to delete an unrelated file that the AI merely
                # mentioned in a string literal.  Warn only when the line is a
                # bare directive -- a `print("--- DELETE_FILE: ... ---")` line
                # cannot match this anchored pattern, so there is nothing to
                # warn the user about in that (entirely normal) case.
                self.warn(
                    f"Line {lineno}: '--- DELETE_FILE: {m.group(1).strip()} ---' appeared "
                    f"inside the block for '{cur_path}', so it was kept as file content "
                    f"and NOT applied as a deletion."
                )
                cur_lines.append(line)
                continue

            cur_lines.append(line)

        if cur_path is not None:
            flush(missing_end=True)

        return blocks, deletes

    def _apply_deletes(
        self, changes: Dict[str, Dict], deletes: List[Tuple[str, int]]
    ) -> None:
        """Record deletions, refusing any path that is both modified and deleted."""
        for path, _lineno in deletes:
            if path in changes:
                # Genuinely ambiguous: honouring either half could destroy
                # work, so refuse the path outright.
                self.error(
                    f"'{path}' is both modified and deleted in the same response. "
                    f"Refusing to apply either operation for that file."
                )
                changes.pop(path, None)
                continue
            self._add(changes, path, {"action": "delete", "content": None})

    # -- block processing --------------------------------------------------

    def _process_block(
        self, changes: Dict[str, Dict], path: str, body: List[str], lineno: int
    ) -> None:
        """Turn one FILE_START block into a change, or report why we cannot."""
        if not path:
            self.error(f"Line {lineno}: FILE_START has an empty path; block skipped.")
            return

        inner = self._extract_code_body(path, body, lineno)
        if inner is None:
            return

        patches = self._extract_patches(path, inner, lineno)
        if patches is _INVALID:
            return  # the problem has already been reported

        if patches is None:
            # Whole-file content mode.
            self._add(
                changes,
                path,
                {"action": "modify", "content": expand_backticks("\n".join(inner))},
            )
            return

        if not patches:
            self.error(
                f"'{path}' (line {lineno}): no usable [LINE] patches were found; the block "
                f"was skipped rather than guessing."
            )
            return

        for patch in patches:
            patch["content"] = expand_backticks(patch["content"])
        self._add(changes, path, {"action": "modify", "patches": patches})

    def _strip_surrounding_fence(self, body: List[str]) -> List[str]:
        """Drop blank padding plus one optional wrapping code fence."""
        start, end = 0, len(body)
        while start < end and not body[start].strip():
            start += 1
        while end > start and not body[end - 1].strip():
            end -= 1
        core = body[start:end]
        if core and FENCE_RE.match(core[0]):
            core = core[1:]
        if core and FENCE_RE.match(core[-1]):
            core = core[:-1]
        return core

    def _extract_code_body(
        self, path: str, body: List[str], lineno: int
    ) -> Optional[List[str]]:
        """Return the lines between [CODE] and [/CODE], or None on failure."""
        core = self._strip_surrounding_fence(body)

        open_idx = next(
            (i for i, ln in enumerate(core) if CODE_OPEN_RE.match(ln)), None
        )
        # Search for the close tag from the *end*: file content that legitimately
        # contains "[CODE]" (this tool's own docs, for instance) would otherwise
        # truncate the file at its own first [/CODE].
        close_idx = (
            next(
                (
                    i
                    for i in range(len(core) - 1, open_idx, -1)
                    if CODE_CLOSE_RE.match(core[i])
                ),
                None,
            )
            if open_idx is not None
            else None
        )

        if open_idx is None or close_idx is None:
            if self.strict:
                self.error(
                    f"'{path}' (line {lineno}): could not find a matching "
                    f"[CODE]...[/CODE] pair. Refusing to guess the file contents, which "
                    f"would overwrite the real file with whatever prose was in the block."
                )
                return None
            self.warn(
                f"'{path}' (line {lineno}): no [CODE] tags; treating raw text as file content."
            )
            return core

        if self.strict:
            stray = next(
                (ln for ln in core[:open_idx] if ln.strip().startswith(_STRAY_PREFIXES)),
                None,
            )
            if stray is not None:
                self.error(
                    f"'{path}' (line {lineno}): unexpected text between FILE_START and "
                    f"[CODE] ({stray.strip()!r}). Refusing to inject it into the file."
                )
                return None

            stray = next(
                (
                    ln
                    for ln in core[close_idx + 1 :]
                    if ln.strip().startswith(_STRAY_PREFIXES)
                ),
                None,
            )
            if stray is not None:
                self.error(
                    f"'{path}' (line {lineno}): unexpected text after [/CODE] "
                    f"({stray.strip()!r}). Refusing to inject it into the file."
                )
                return None

            # Ordinary prose either side of the [CODE] block is not file
            # content and is never injected -- but say so, because it means the
            # AI broke the format and the user may want to know.
            loose_before = any(ln.strip() for ln in core[:open_idx])
            loose_after = any(ln.strip() for ln in core[close_idx + 1 :])
            if loose_before or loose_after:
                self.warn(
                    f"'{path}' (line {lineno}): found text outside the [CODE] block. It was "
                    f"discarded rather than written into the file."
                )

        return core[open_idx + 1 : close_idx]

    # -- patches -----------------------------------------------------------

    def _extract_patches(
        self, path: str, inner: List[str], lineno: int
    ) -> Optional[List[Dict]]:
        """Parse the ``[LINE n]`` / ``[/LINE n]`` blocks.

        Returns ``None`` when the block holds whole-file content, a list of
        patches on success, ``[]`` when patch mode was implied but nothing
        usable came out, and :data:`_INVALID` when a patch was malformed.
        """
        open_positions = [i for i, ln in enumerate(inner) if LINE_OPEN_RE.match(ln)]
        if not open_positions:
            if self.strict and any(
                ln.strip().startswith(_LINE_PREFIXES) for ln in inner
            ):
                self.error(
                    f"'{path}' (line {lineno}): found a [LINE] tag that is not well formed. "
                    f"Refusing to treat the block as whole-file content, because that "
                    f"would replace the entire file."
                )
                return _INVALID
            return None

        patches: List[Dict] = []
        covered: List[Tuple[int, int]] = []

        for i in open_positions:
            if any(a <= i <= b for a, b in covered):
                self.error(
                    f"'{path}' (line {lineno}): overlapping [LINE] blocks. "
                    f"Applying overlapping patches would corrupt the file, so the whole "
                    f"patch set was rejected."
                )
                return _INVALID

            patch = self._read_patch(path, inner, i, lineno)
            if patch is None:
                return _INVALID
            covered.append((i, patch.pop("_end_index")))
            patches.append(patch)

        for patch in patches:
            problem = validate_patch(patch)
            if problem:
                self.error(f"'{path}' (line {lineno}): {problem} Patch set rejected.")
                return _INVALID

        # Catch overlaps on the *line numbers*, since those are what actually
        # collide inside the target file.
        ordered = sorted(patches, key=lambda p: p["start"])
        for prev, nxt in zip(ordered, ordered[1:]):
            if nxt["start"] <= prev["end"]:
                self.error(
                    f"'{path}' (line {lineno}): patches for lines {prev['start']}-"
                    f"{prev['end']} and {nxt['start']}-{nxt['end']} overlap. "
                    f"Applying both would corrupt the file, so the patch set was rejected."
                )
                return _INVALID

        return patches

    def _read_patch(
        self, path: str, inner: List[str], open_idx: int, lineno: int
    ) -> Optional[Dict]:
        """Read a single patch starting at ``open_idx``.

        The returned dict carries a temporary ``_end_index`` key recording the
        closing tag's position, which the caller pops.
        """
        m = LINE_OPEN_RE.match(inner[open_idx])
        assert m is not None  # caller only passes matching lines
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        label = f"{start}" if end == start else f"{start}-{end}"

        body: List[str] = []
        for j in range(open_idx + 1, len(inner)):
            cm = LINE_CLOSE_RE.match(inner[j])
            if cm:
                c_start = int(cm.group(1))
                c_end = int(cm.group(2)) if cm.group(2) else c_start
                if (c_start, c_end) != (start, end):
                    self.error(
                        f"'{path}' (line {lineno}): [LINE {label}] is closed by "
                        f"[/LINE {c_start if c_start == c_end else f'{c_start}-{c_end}'}]. "
                        f"Open and close tags must name the same lines, so this patch "
                        f"was rejected."
                    )
                    return None
                return {
                    "start": start,
                    "end": end,
                    "content": "\n".join(body),
                    "_end_index": j,
                }

            if LINE_OPEN_RE.match(inner[j]):
                self.error(
                    f"'{path}' (line {lineno}): [LINE {label}] is never closed -- another "
                    f"[LINE] tag starts first. Patch rejected."
                )
                return None

            body.append(inner[j])

        self.error(
            f"'{path}' (line {lineno}): [LINE {label}] is never closed with a matching "
            f"[/LINE ...] tag. Patch rejected."
        )
        return None

    # -- helpers -----------------------------------------------------------

    def _add(self, changes: Dict[str, Dict], path: str, desc: Dict) -> None:
        if path in changes:
            self.warn(f"Duplicate entry for '{path}' – overwriting previous.")
        changes[path] = desc

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)

    # -- legacy scraping (opt-in via allow_legacy) --------------------------

    @staticmethod
    def _legacy_fallback(text: str) -> Dict[str, Dict]:
        """Fallback for standard markdown code fences with a path annotation.

        Only used when ``allow_legacy`` is set.  Kept deliberately strict: the
        path has to look like a real path, otherwise this would happily rewrite
        files the AI merely talked about.
        """
        changes: Dict[str, Dict] = {}
        pat = re.compile(
            r"^[ \t]*`{3,}[ \t]*[\w+.#-]*[ \t]+(.+?)[ \t]*\n(.*?)^[ \t]*`{3,}",
            re.DOTALL | re.MULTILINE | re.IGNORECASE,
        )
        known_suffixes = (
            ".py", ".rs", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".json",
            ".yaml", ".yml", ".toml", ".md", ".txt", ".c", ".h", ".cpp", ".hpp",
            ".java", ".go", ".rb", ".php", ".sh", ".bash", ".zsh", ".kt", ".kts",
            ".swift", ".sql", ".lua", ".dart", ".ex", ".exs", ".vim", ".cfg",
            ".ini", ".conf", ".xml", ".svg",
        )
        for m in pat.finditer(text):
            pth = m.group(1).strip()
            if "/" in pth or "\\" in pth or pth.lower().endswith(known_suffixes):
                changes[pth] = {
                    "action": "modify",
                    "content": expand_backticks(m.group(2).strip()),
                }
        return changes
