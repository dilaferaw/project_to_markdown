# ProjectToMarkdown

**Bridge your local projects to free chat LLMs – no API keys needed.**

ProjectToMarkdown scans a local coding project and produces a single `.md` file (directory tree + all file contents) that you can paste into any free-tier chat AI. After the AI replies, paste its answer back into the app – PTM parses the structured response and applies changes directly to your files, in‑place or to a new copy.

## Features

- **Local web UI** – runs in your browser on Linux, Windows and macOS; no GUI toolkit required
- **File browser** for effortless project selection
- **One‑click “Full Prompt”** – inserts foolproof instructions so even basic LLMs reply in a machine‑parseable format
- **Line‑level patching** – the AI can send only changed lines, saving tokens
- **System prompt button** – copy only the instruction block to set up a new chat
- **Token counting** – see approximate token usage before pasting (requires `tiktoken`, optional)
- **Three apply modes:** modify in‑place (with auto‑backup), export to new folder, create new project from scratch
- **100% offline** – no API calls, no telemetry (the server binds to `127.0.0.1` only)

## Installation

### Linux (Debian/Ubuntu/Pop!_OS)

```bash
sudo apt update
sudo apt install python3 tree
pip install tiktoken   # optional, for accurate token counting
```

### Other platforms (Windows, macOS, BookwormPup64, etc.)

1. Install **Python 3.12+** from [python.org](https://www.python.org/downloads/)
2. Install `tiktoken` (optional): `pip install tiktoken`
3. No GUI toolkit is required – the app runs in your browser.

## Quick start

```bash
git clone https://github.com/dilaferaw/project_to_markdown.git
cd project_to_markdown
python3 main.py
```

This starts a local web server and opens the app in your default browser
(pass `--no-browser` to print the URL instead, or `--port 8765` for a fixed port).

1. Click **Browse…** and select your project folder
2. Click **Scan Project**, tick the files you want, then **Generate Markdown from Selected**
3. **(Recommended)** Click **Full Prompt & Copy** – the complete prompt (instructions + project data) is now in your clipboard
4. Paste it into any free chat LLM (ChatGPT, Claude, etc.) and add your request
5. Copy the AI’s entire reply
6. Go to the **Project Builder** tab, paste, and click **Parse Response**
7. Check the files you want to change, choose a mode, and click **Apply Selected Changes**

## Docker (optional)

The app runs in a lightweight Alpine-based container. The `Dockerfile`
multi-stage build compiles dependencies in the first stage and ships a minimal
runtime image. Settings, backups and parse history persist in a named Docker
volume, so the container can be recreated or restarted freely.

```bash
git clone https://github.com/dilaferaw/project_to_markdown.git
cd project_to_markdown/docker
docker compose up --build -d
# open http://localhost:8765
```

To mount a local project tree so the *server* can reach it, uncomment the
`volumes` section in `docker/docker-compose.yml` and point it at your folder.

The image is also usable standalone:

```bash
docker build -t ptm ..
docker run -p 8765:8765 -v ptm_data:/data ptm
```

> The server still binds to `127.0.0.1` by default (loopback only, CSRF-safe).
> Pass `--host 0.0.0.0` via `main.py`'s CLI (or set `HOST=0.0.0.0` in
> `docker-compose.yml`) to expose it to the LAN.

## CLI

```bash
python main.py              # random free port, opens browser
python main.py -p 8765      # fixed port
python main.py --no-browser # just print the URL
python main.py --host 0.0.0.0 -p 8765  # expose to the LAN
```

## Requirements

- Python 3.12+
- `tiktoken` (optional) – `pip install tiktoken`
- `tree` (optional, Linux) – prettier directory tree output

## Project structure

```text
project_to_markdown/
├── main.py                  # Entry point – starts the local web server
├── server.py                # Loopback HTTP server + JSON API (stdlib only)
├── utils.py                 # Shared constants, token counting
├── core/
│   ├── applier.py           # Applies changes to filesystem
│   ├── config.py            # JSON config, sanitised on load
│   ├── file_utils.py        # File type detection, tree generation
│   ├── markdown_builder.py  # Builds the export Markdown
│   ├── prompt_template.py   # Foolproof system prompt
│   └── response_parser.py   # Parses structured AI replies
├── web/
│   ├── index.html           # App shell (tabs + modals)
│   ├── app.js               # Front-end logic
│   └── style.css            # Dark theme
├── docker/                  # Docker multi-stage build + compose
│   ├── Dockerfile
│   └── docker-compose.yml
├── tests/                   # pytest suite: parser, applier, builder, utils, config, server
├── README.md
├── LICENSE
├── .gitignore
├── requirements.txt
└── install.sh
```

## License

GPL‑3.0 – see [LICENSE](LICENSE) for full text.

## Requirements

- Python 3.12+
- `tiktoken` (optional) – `pip install tiktoken`
- `tree` (optional, Linux) – prettier directory tree output

## Project structure

```text
project_to_markdown/
├── main.py                  # Entry point – starts the local web server
├── server.py                # Loopback HTTP server + JSON API (stdlib only)
├── utils.py                 # Shared constants, token counting
├── core/
│   ├── applier.py           # Applies changes to filesystem
│   ├── config.py            # JSON config, sanitised on load
│   ├── file_utils.py        # File type detection, tree generation
│   ├── markdown_builder.py  # Builds the export Markdown
│   ├── prompt_template.py   # Foolproof system prompt
│   └── response_parser.py   # Parses structured AI replies
├── web/
│   ├── index.html           # App shell (tabs + modals)
│   ├── app.js               # Front-end logic
│   └── style.css            # Dark theme
├── tests/                   # pytest suite: parser, applier, builder, utils, config, server
├── README.md
├── LICENSE
├── .gitignore
├── requirements.txt
└── install.sh
```

## License

GPL‑3.0 – see [LICENSE](LICENSE) for full text.