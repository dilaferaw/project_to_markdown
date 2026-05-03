"""Parse the structured AI response and return a dictionary of changes."""

import re
from typing import Dict, List, Union


class AIResponseParser:
    @staticmethod
    def parse(text: str) -> Dict[str, Dict]:
        """
        Returns: {filepath: {"action": "modify"/"create"/"delete",
                             "content": str or None,
                             "patches": list of dicts (optional)}}
        """
        changes = {}
        # Pre‑process: replace backtick placeholders with real backticks
        # The AI is instructed to use [BACK3] and [BACK] to avoid escaping issues.
        text = text.replace("[BACK3]", "```").replace("[BACK]", "`")

        # Primary: --- FILE_START: path --- ... --- FILE_END ---
        pattern = r'---\s+FILE_START:\s*(.+?)\s*---\s*\n(.*?)---\s+FILE_END\s*---'
        for match in re.finditer(pattern, text, re.DOTALL):
            path = match.group(1).strip()
            body = match.group(2)

            # Remove outer ```text fence if present
            body = re.sub(r'^```(?:\w*text\w*)?\s*\n', '', body, count=1, flags=re.IGNORECASE | re.DOTALL)
            body = re.sub(r'\n```\s*$', '', body, count=1, flags=re.IGNORECASE | re.DOTALL)

            # Extract everything between [CODE language] and [/CODE]
            code_match = re.search(r'\[CODE\s+\w*\]\s*\n(.*?)\n\s*\[/CODE\]', body, re.DOTALL | re.IGNORECASE)
            if code_match:
                code_body = code_match.group(1).strip()
            else:
                code_body = body.strip()

            # Check for line‑patch markers
            patch_pattern = r'\[LINE\s+(\d+)(?:\s*-\s*(\d+))?\s*\](.*?)\[/LINE\s+\1(?:-\2)?\s*\]'
            patch_matches = list(re.finditer(patch_pattern, code_body, re.DOTALL))
            if patch_matches:
                patches = []
                for pm in patch_matches:
                    start = int(pm.group(1))
                    end_str = pm.group(2)
                    end = int(end_str) if end_str else start
                    raw = pm.group(3)
                    if raw.startswith('\n'):
                        raw = raw[1:]
                    if raw.endswith('\n'):
                        raw = raw[:-1]
                    patches.append({
                        "type": "replace",
                        "start": start,
                        "end": end,
                        "content": raw
                    })
                changes[path] = {"action": "modify", "patches": patches}
            else:
                changes[path] = {"action": "modify", "content": code_body}

        # Deletions: --- DELETE_FILE: path ---
        delete_pattern = r'---\s+DELETE_FILE:\s*(.+?)\s*---'
        for match in re.finditer(delete_pattern, text):
            path = match.group(1).strip()
            changes[path] = {"action": "delete", "content": None}

        # Fallback: code fences with path annotation ```lang path
        if not changes:
            alt_pattern = r'```(?:\w+)?\s+(.+?)\n(.*?)```'
            for match in re.finditer(alt_pattern, text, re.DOTALL):
                path = match.group(1).strip()
                content = match.group(2).strip()
                if '/' in path or path.endswith('.') or path.startswith('.'):
                    changes.setdefault(path, {"action": "modify", "content": content})

        return changes