# ProjectToMarkdown

**Bridge your local projects to free chat LLMs – no API keys needed.**

ProjectToMarkdown scans a local coding project and produces a single `.md` file (directory tree + all file contents) that you can paste into any free-tier chat AI. After the AI replies, paste its answer back into the app – PTM parses the structured response and applies changes directly to your files, in‑place or to a new copy.

## Features

- **Native cross‑platform GUI** – Tkinter, runs on Linux, Windows, macOS
- **File browser** for effortless project selection
- **One‑click “Full Prompt”** – inserts foolproof instructions so even basic LLMs reply in a machine‑parseable format
- **Line‑level patching** – the AI can send only changed lines, saving tokens
- **System prompt button** – copy only the instruction block to set up a new chat
- **Token counting** – see approximate token usage before pasting (requires `tiktoken`, optional)
- **Three apply modes:** modify in‑place (with auto‑backup), export to new folder, create new project from scratch
- **100% offline** – no API calls, no telemetry

## Installation

### Linux (Debian/Ubuntu/Pop!_OS)

```bash
sudo apt update
sudo apt install python3 python3-tk xclip tree
pip install tiktoken   # optional, for accurate token counting
```

### Other platforms (Windows, macOS, BookwormPup64, etc.)

1. Install **Python 3.10+** from [python.org](https://www.python.org/downloads/)
2. Install `tiktoken` (optional): `pip install tiktoken`
3. Tkinter is included with Python on most platforms. If missing, install it via your package manager.

## Quick start

```bash
git clone https://github.com/dilaferaw/project_to_markdown.git
cd project_to_markdown
python3 main.py
```

1. Click **Browse…** and select your project folder
2. Click **Scan & Generate Markdown**
3. **(Recommended)** Click **Full Prompt & Copy** – the complete prompt (instructions + project data) is now in your clipboard
4. Paste it into any free chat LLM (ChatGPT, Claude, etc.) and add your request
5. Copy the AI’s entire reply
6. Go to the **Project Builder** tab, paste, and click **Parse Response**
7. Check the files you want to change, choose a mode, and click **Apply Selected Changes**

## Requirements

- Python 3.8+ (3.10+ recommended)
- `tiktoken` (optional) – `pip install tiktoken`
- `tree` (optional, Linux) – prettier directory tree output
- `xclip` (optional, Linux) – reliable clipboard copying

## Project structure

```text
project_to_markdown/
├── main.py                  # Entry point – Tkinter app
├── utils.py                 # Shared constants, token counting
├── core/
│   ├── applier.py           # Applies changes to filesystem
│   ├── file_utils.py        # File type detection, tree generation
│   ├── markdown_builder.py  # Builds the export Markdown
│   ├── prompt_template.py   # Foolproof system prompt
│   └── response_parser.py   # Parses structured AI replies
├── ui/
│   ├── export_tab.py        # Export tab UI
│   ├── apply_tab.py         # Project Builder tab UI
│   └── settings_tab.py      # Settings tab UI
├── README.md
├── LICENSE
├── .gitignore
├── requirements.txt
└── install.sh
```

## License

GPL‑3.0 – see [LICENSE](LICENSE) for full text.