"""Parse the structured AI response and return a dictionary of changes."""

import re
from typing import Dict, List, Optional, Tuple


class AIResponseParser:
    """Parser that converts an AI reply into file change instructions."""

    warnings: List[str] = []

    @staticmethod
    def parse(text: str) -> Dict[str, Dict]:
        """
        Returns: {filepath: {"action": "modify"/"create"/"delete",
                             "content": str or None,
                             "patches": list of dicts (optional)}}
        """
        AIResponseParser.warnings = []          # fresh warnings

        # Pre‑process backtick placeholders
        text = text.replace("```", "```").replace("`", "`")

        changes = {}

        # --- Helper to add a change while warning on duplicates ------------
        def _add(filepath: str, desc: dict):
            if filepath in changes:
                AIResponseParser.warnings.append(
                    f"Duplicate entry for '{filepath}' – overwriting previous."
                )
            changes[filepath] = desc

        # --- Robust FILE_START / FILE_END extraction ------------------------
        # We use regex to match the opening tag, then manually scan for the
        # closing tag, falling back to the next opening tag or end of text.
        body_pattern = re.compile(
            r'^---\s*FILE_START\s*:\s*(.+?)\s*---\s*\n',
            re.MULTILINE | re.IGNORECASE,
        )

        pos = 0
        while pos < len(text):
            m = body_pattern.search(text, pos)
            if not m:
                break

            filepath = m.group(1).strip()
            content_start = m.end()

            # Search for FILE_END
            end_match = re.compile(
                r'\n---\s*FILE_END\s*---',
                re.IGNORECASE
            ).search(text, content_start)

            if end_match:
                content_end = end_match.start()
                pos = end_match.end()
            else:
                # Missing FILE_END – close at next FILE_START or end of text
                AIResponseParser.warnings.append(
                    f"Missing FILE_END for '{filepath}' – assuming block ends there."
                )
                next_start = body_pattern.search(text, content_start)
                if next_start:
                    content_end = next_start.start()
                    pos = content_end   # next iteration will re‑scan from here
                else:
                    content_end = len(text)
                    pos = content_end

            raw_block = text[content_start:content_end]

            # Strip outer ```text fence if present
            raw_block = raw_block.strip()
            raw_block = re.sub(r'^```(?:\w*text\w*)?\s*\n', '', raw_block, flags=re.IGNORECASE)
            raw_block = re.sub(r'\n```\s*$', '', raw_block, flags=re.IGNORECASE)

            # Process the block (same logic as before)
            code_match = re.search(
                r'\[CODE\s+\w*\]\s*\n(.*?)\n\s*\[/CODE\]',
                raw_block, re.DOTALL | re.IGNORECASE
            )
            if code_match:
                inner = code_match.group(1).strip()
                patches = AIResponseParser._extract_patches(inner)
                if patches:
                    _add(filepath, {"action": "modify", "patches": patches})
                else:
                    _add(filepath, {"action": "modify", "content": inner})
            else:
                # No [CODE] tags – use entire block as content
                AIResponseParser.warnings.append(
                    f"No [CODE] tags for '{filepath}' – treating raw text as file content."
                )
                _add(filepath, {"action": "modify", "content": raw_block.strip()})

        # --- Deletions ------------------------------------------------------
        del_pattern = re.compile(r'^---\s*DELETE_FILE\s*:\s*(.+?)\s*---', re.MULTILINE | re.IGNORECASE)
        for match in del_pattern.finditer(text):
            p = match.group(1).strip()
            _add(p, {"action": "delete", "content": None})

        # --- Legacy fallback -------------------------------------------------
        if not changes:
            alt = AIResponseParser._legacy_fallback(text)
            for p, d in alt.items():
                _add(p, d)

        return changes

    @staticmethod
    def _extract_patches(inner: str) -> Optional[List[Dict]]:
        """Return list of {start, end, content} or None if no patches found."""
        pat = re.compile(
            r'\[LINE\s+(\d+)(?:\s*-\s*(\d+))?\s*\](.*?)\[/LINE\s+\1(?:-\2)?\s*\]',
            re.DOTALL | re.IGNORECASE,
        )
        patches = []
        for match in pat.finditer(inner):
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else start
            content = match.group(3)
            if content.startswith('\n'):
                content = content[1:]
            if content.endswith('\n'):
                content = content[:-1]
            patches.append({"start": start, "end": end, "content": content})
        return patches if patches else None

    @staticmethod
    def _legacy_fallback(text: str) -> Dict[str, Dict]:
        """Fallback for standard markdown code fences with path annotation."""
        changes = {}
        pat = re.compile(r'```(?:\w+)?\s+(.+?)\n(.*?)```', re.DOTALL)
        for m in pat.finditer(text):
            pth = m.group(1).strip()
            if '/' in pth or pth.endswith('.') or pth.startswith('.'):
                changes[pth] = {"action": "modify", "content": m.group(2).strip()}
        return changes