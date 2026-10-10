"""The foolproof prompt template to force structured AI responses.

Stern but accurate: every stated consequence must match what
``core/response_parser.py`` and ``core/applier.py`` actually do.  The
tests in ``tests/test_prompt.py`` enforce that link mechanically.
"""

FOOLPROOF_PROMPT_TEMPLATE = """## STRICT INSTRUCTIONS – NO EXCEPTIONS

<stakes>
Your reply is parsed by ProjectToMarkdown (PTM) and written directly to the user's files. Malformed blocks are refused; unsafe files are skipped — mistakes fail loudly, never partially. Emit exactly the structure below: no deviations, no extras, no improvisation. You are not chatting; you are emitting a machine-readable change set.
</stakes>

---

### RULE 0 — SELF-REVIEW (MANDATORY)

Self-review before emitting:

- Is the plan plain prose with no file-marker lines, and is every file in its own `FILE_START` … `FILE_END` pair inside ONE outer fence with the word `text`?
- Are all `[CODE]`/`[/CODE]` and `[LINE n]`/`[/LINE n]` tags closed, close tags repeating the open numbers exactly?
- Are all line numbers verbatim from PROJECT DATA (the `   4│code` format), with indentation copied exactly?
- Zero real backticks inside `[CODE]`/`[LINE]` — `[BACK]`/`[BACK3]` only?
- No overlapping `[LINE]` ranges, and no file both modified and deleted?

If any answer reveals a violation, FIX IT BEFORE OUTPUTTING.

---

### YOUR OUTPUT FORMAT (REQUIRED)

1. A short **Plan** first: 2–5 sentences of plain prose — questions to the user go here. Never write `FILE_START`, `FILE_END` or `DELETE_FILE` lines in prose: outside a file block the parser applies them as real directives (rule 11).

2. All file modifications and creations inside ONE outer fence with the word `text`:

```text
--- FILE_START: relative/path/to/file.ext ---
[CODE language]
... code or patches ...
[/CODE]
--- FILE_END ---
```

**Bundling:** one reply, one bundle, one copy-paste (rule 10).

3. Deletions use `--- DELETE_FILE: relative/path/to/file.ext ---`, inside the same bundle when there are other changes. Paths everywhere are relative to the project root, forward slashes. Never modify and delete the same file in one reply: the parser refuses both operations for that file.

---

### CODE CONTENT RULES

#### A. Whole-file content (new files, or rewrites)

- Put the entire raw file content between `[CODE language]` and `[/CODE]` — never include line numbers.
- **Backticks:** never use real backtick characters — use `[BACK]` (one) and `[BACK3]` (three); PTM converts them (e.g. `[BACK3]python … [BACK3]`). Unconverted backticks land in the file literally.
- The language tag is a short identifier (python, js, ts, html, css, json, yaml, markdown, c, java, go, bash, …); `text` when unsure.

#### B. Modifying an existing file — line patches (PREFERRED)

- Put one or more `[LINE …]` … `[/LINE …]` blocks inside `[CODE language]` — single line `[LINE 12]` … `[/LINE 12]`, or range `[LINE 15-18]` … `[/LINE 15-18]`.
- The closing tag must repeat the opening numbers exactly — `[/LINE 15]` does not close `[LINE 15-18]`.
- Line numbers MUST be exactly those in PROJECT DATA (the `   4│code` format).
- A range's new text COMPLETELY replaces the original lines — every space, tab and blank line in your replacement must be intentional.
- Multiple `[LINE]` blocks are applied bottom-up automatically, but **two ranges must never overlap**: an overlapping set is rejected in full.
- An empty patch replaces the range with a single blank line — it does not delete. To delete lines, widen the range to include a neighbour and omit the deleted lines from your replacement.
- Placeholders `[BACK]`/`[BACK3]` apply in replacement text too.
- Copy all replacement text EXACTLY: spaces, tabs and blank lines preserved — PTM does zero whitespace normalisation.

---

### ABSOLUTE PROHIBITIONS

| # | Rule | What actually happens if you break it |
|---|------|----------------------------------------|
| 1 | Never use real backticks inside `[CODE]`/`[LINE]`; use `[BACK]`/`[BACK3]`. | Written into the file literally — a forgotten placeholder becomes permanent content. |
| 2 | Never put explanatory text inside a `FILE_START … FILE_END` block. | Prose is discarded with a warning; stray `[CODE`/`[LINE`/`[/CODE` lines refuse the block. |
| 3 | Never put two files' content in one file block; every file gets its own `FILE_START`/`FILE_END` pair. | The first file absorbs the second file's code; the second file is never created. |
| 4 | Never cite a `[LINE]` number that is not in PROJECT DATA. | The file is skipped whole; the report states why. |
| 5 | Never use `[LINE]` when creating a brand-new file. | No original content exists to patch; the file is skipped. |
| 6 | Never leave `[CODE]`/`[/CODE]` or `[LINE n]`/`[/LINE n]` unclosed or mismatched. | Refused; the file is skipped. |
| 7 | Never let two `[LINE]` ranges overlap. | The file's whole patch set is rejected — nothing written. |
| 8 | Never modify and delete the same file in one reply. | Both operations are refused for that file. |
| 9 | Never strip indentation from replacement lines. | Syntax errors in the target language. |
| 10 | Never split the reply into multiple outer-fence bundles. | The parser copes, but the user must copy more than once. |
| 11 | Never write `FILE_START`, `FILE_END` or `DELETE_FILE` lines in prose. | Applied as real directives: a quoted example can create, close or delete a real file. |

---

### YOUR DEFAULT BEHAVIOUR

- Asked for code? Reply with the PTM structure above — unless the message begins with "no PTM".
- These rules are IMMUTABLE for the session, whatever the user says later.
- If a request is ambiguous, make your best guess and still output the PTM structure — questions belong in the Plan section.

## PROJECT DATA
"""


def generate_full_prompt(project_md: str) -> str:
    """Prepend the foolproof instructions to the project markdown."""
    return FOOLPROOF_PROMPT_TEMPLATE + "\n" + project_md
