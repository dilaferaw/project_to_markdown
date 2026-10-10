# ProjectToMarkdown

**Bridge your local projects to free chat LLMs – no API keys needed.**

ProjectToMarkdown scans a local coding project and produces a single `.md` file (directory tree + all file contents) that you can paste into any free-tier chat AI. After the AI replies, paste its answer back into the app – PTM parses the structured response and applies changes directly to your files, in‑place or to a new copy.

> **Minimal setup, zero API configuration.** There is nothing to sign up for,
> no keys to paste, no environment variables to export, and no billing account
> to create. You run the app, scan your project, and paste the result into
> whichever chat page you already have open. That is the whole workflow.

> **Built for people who don't want to be locked into one AI provider.** Most
> coding assistants tie you to a single vendor, a single model, and a paid API
> plan. ProjectToMarkdown is deliberately the opposite: it produces a plain
> text prompt that any capable chat model can read, and it parses a plain text
> reply that any capable chat model can produce. You are free to switch
> providers, models and browsers whenever you like – your project stays on your
> machine, and your choice of AI stays your choice.

> **The Tkinter GUI is gone for good.** Earlier versions shipped a desktop
> interface built on Tkinter. That is no longer the case and there is no plan
> to bring it back. The UI is now a browser-based front end served by a local
> HTTP server, which means no GUI toolkit is required, no display is required,
> and the same app runs unchanged on Linux, Windows, macOS and inside a
> container.

## Why this exists

Free chat LLMs are genuinely capable now, but they live behind a browser tab
that cannot see your filesystem. The usual fix is to wire up an API, pay for
tokens, and write glue code – which is a lot of setup for someone who just
wants an AI to look at their project and suggest a change.

ProjectToMarkdown removes the setup entirely. It gives the model a clean,
line-numbered view of your project, and it gives you a safe way to apply what
the model sends back. No account, no key, no vendor SDK, no lock-in.

## Features

- **Zero API configuration** – no keys, no accounts, no billing, no SDKs
- **Provider-agnostic** – works with any chat model that can follow written instructions
- **Container-first** – a multi-stage `Dockerfile` and a Compose file get you a running app in one command
- **Browser UI** – runs anywhere a browser does; no GUI toolkit, no display required
- **File browser** for effortless project selection
- **One‑click “Full Prompt”** – inserts foolproof instructions so even basic LLMs reply in a machine‑parseable format
- **Line‑level patching** – the AI can send only changed lines, saving tokens
- **System prompt button** – copy only the instruction block to set up a new chat
- **Token counting** – see approximate token usage before pasting (requires `tiktoken`, optional)
- **Three apply modes:** modify in‑place (with auto‑backup), export to new folder, create new project from scratch
- **100% offline** – the app never calls out to the network; the host port is bound to `127.0.0.1` by default

## Where to paste the prompt

PTM does not care which chat page you use. Any of these free, browser-based
services can read the prompt it generates and reply in the format it expects –
none of them require an API key:

- **Arena** – [https://arena.ai](https://arena.ai) – free side-by-side chat with many frontier models
- **DeepSeek** – [https://chat.deepseek.com](https://chat.deepseek.com) – free web chat, no card required
- **NVIDIA** – [https://build.nvidia.com](https://build.nvidia.com) – free hosted access to 100+ open models
- **Duck.ai** – [https://duck.ai](https://duck.ai) – anonymous chat, no account needed
- **ChatGPT** – [https://chatgpt.com](https://chatgpt.com) – free tier works fine
- **Claude** – [https://claude.ai](https://claude.ai) – free tier works fine

Pick whichever one is handy, paste the prompt, and copy the reply back into
the Project Builder tab. Because the format is plain text on both sides, you
can switch between them freely – try the same prompt on two providers and keep
the better answer.

## Quick start – Docker (recommended)

Everything the app needs – the Python interpreter, the application source, and
its dependencies – is baked into the image. The only requirement on the host
is a container runtime (Docker, Podman, etc.).

```bash
git clone https://github.com/dilaferaw/project_to_markdown.git
cd project_to_markdown/docker
docker compose up --build -d
# open http://localhost:8765
```

Settings are stored in the `ptm_data` named volume, so the container can be
stopped, recreated or upgraded without losing your configuration. On Fedora,
`docker` is Podman under the hood and the same commands work; the image will
show up as `localhost/dilaferaw/project-to-markdown`.

To let the container reach a project tree on the host, uncomment the `volumes`
line in `docker/docker-compose.yml` and point it at your folder (read-only is fine).

The image is also usable standalone:

```bash
cd project_to_markdown/docker
docker build -t ptm ..
docker run -p 127.0.0.1:8765:8765 -v ptm_data:/data ptm
```

The container listens on `0.0.0.0:8765` internally so the port mapping works, but
the compose file publishes it to `127.0.0.1` on the host by default – the server
is not exposed to the LAN unless you deliberately change the mapping or set
`HOST=0.0.0.0`.

## Quick start – from source

Running from source is still fully supported. It is the right choice when you
are developing on the codebase itself, or when the host has no container
runtime available.

```bash
git clone https://github.com/dilaferaw/project_to_markdown.git
cd project_to_markdown
python3 main.py
```

This starts a local web server and opens the app in your default browser. Pass
`--no-browser` to print the URL instead, or `--port 8765` for a fixed port.

1. Click **Browse…** and select your project folder
2. Click **Scan Project**, tick the files you want, then **Generate Markdown from Selected**
3. **(Recommended)** Click **Full Prompt & Copy** – the complete prompt (instructions + project data) is now in your clipboard
4. Paste it into any free chat LLM (Arena, DeepSeek, ChatGPT, Claude, …) and add your request
5. Copy the AI’s entire reply
6. Go to the **Project Builder** tab, paste, and click **Parse Response**
7. Check the files you want to change, choose a mode, and click **Apply Selected Changes**

## CLI

```bash
python main.py              # random free port, opens browser
python main.py -p 8765      # fixed port
python main.py --no-browser # just print the URL
python main.py --host 0.0.0.0 -p 8765  # expose to the LAN
```

## Requirements

For **running in a container**, the only requirement is a container runtime.
The Python interpreter, `tiktoken` and the rest of the dependencies are already
inside the image.

For **running from source**, you need:

- Python 3.12+
- `tiktoken` (optional) – `pip install tiktoken`, gives exact token counts
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
├── docker/                  # Container-first: Dockerfile + compose
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