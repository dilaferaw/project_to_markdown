"""Local HTTP server backing the ProjectToMarkdown web UI.

Standard library only: a ``ThreadingHTTPServer`` bound to ``127.0.0.1`` that
serves a small JSON API under ``/api/`` and the static frontend from ``web/``.

Security model
--------------
* Loopback only -- nothing outside this machine can reach the server.
* A random token is generated at startup and injected into the served
  ``index.html``.  Every ``/api/`` call must echo it back in the
  ``X-PTM-Token`` header.  Cross-origin pages cannot read the token (no CORS
  headers are ever sent), so they cannot forge API calls: this blocks CSRF
  from any other tab or website the user has open.
* Static assets (HTML/CSS/JS) are inert on their own and need no token.
"""

import json
import secrets
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import utils
from core import config as config_module
from core.applier import ChangeApplier
from core.file_utils import generate_tree
from core.markdown_builder import export_project, scan_project_files
from core.prompt_template import FOOLPROOF_PROMPT_TEMPLATE, generate_full_prompt
from core.response_parser import AIResponseParser
from utils import count_tokens

WEB_DIR = Path(__file__).resolve().parent / "web"
_STATIC_FILES = {
    "app.js": "application/javascript; charset=utf-8",
    "style.css": "text/css; charset=utf-8",
}


class _ApiError(Exception):
    """An error whose message is safe and useful to show to the user."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class _Handler(BaseHTTPRequestHandler):
    server_version = "ProjectToMarkdown"

    # -- plumbing -----------------------------------------------------------

    def log_message(self, fmt, *args):
        """Keep the console quiet; real failures are printed explicitly."""
        pass

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _error(self, status: int, message: str) -> None:
        self._send_json({"error": message}, status)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b""
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise _ApiError(400, "Request body is not valid JSON.")
        if not isinstance(data, dict):
            raise _ApiError(400, "Request body must be a JSON object.")
        return data

    def _authorised(self) -> bool:
        supplied = self.headers.get("X-PTM-Token", "")
        return secrets.compare_digest(str(supplied), self.server.token)

    # -- request handlers ---------------------------------------------------

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        try:
            if path == "/":
                html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
                html = html.replace("__PTM_TOKEN__", self.server.token)
                self._send_bytes(html.encode("utf-8"), "text/html; charset=utf-8")
            elif path.startswith("/static/"):
                name = path[len("/static/"):]
                if name not in _STATIC_FILES:
                    return self._error(404, "Not found.")
                body = (WEB_DIR / name).read_bytes()
                self._send_bytes(body, _STATIC_FILES[name])
            else:
                self._error(404, "Not found.")
        except OSError as exc:
            self._error(500, f"Could not read asset: {exc}")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if not path.startswith("/api/"):
            return self._error(404, "Not found.")
        if not self._authorised():
            return self._error(403, "Missing or invalid token.")
        try:
            data = self._read_json()
            route = path[len("/api/"):]
            handler = _API_ROUTES.get(route)
            if handler is None:
                return self._error(404, f"Unknown endpoint: {route}")
            self._send_json(handler(data))
        except _ApiError as exc:
            self._error(exc.status, str(exc))
        except (ValueError, FileExistsError) as exc:
            # Domain errors raised by the applier: the user can act on these.
            self._error(400, str(exc))
        except OSError as exc:
            self._error(500, f"Filesystem error: {exc}")
        except Exception as exc:  # noqa: BLE001 - last-resort guard
            traceback.print_exc(file=sys.stderr)
            self._error(500, f"Internal error: {exc}")



def _require_dir(data: dict, key: str = "root") -> Path:
    raw = str(data.get(key) or "").strip()
    if not raw:
        raise _ApiError(400, "Please select a valid project folder.")
    path = Path(raw).expanduser()
    if not path.is_dir():
        raise _ApiError(400, f"Not a directory: {raw}")
    return path


def _api_fs_list(data: dict) -> dict:
    """Directory listing used by the frontend's folder-picker modal."""
    raw = str(data.get("path") or "").strip() or str(Path.home())
    path = Path(raw).expanduser()
    if not path.is_dir():
        raise _ApiError(400, f"Not a directory: {raw}")
    path = path.resolve()
    try:
        entries = []
        for child in path.iterdir():
            try:
                entries.append({"name": child.name, "is_dir": child.is_dir()})
            except OSError:
                continue
    except PermissionError:
        raise _ApiError(400, f"Cannot read directory: {path}")
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    parent = str(path.parent) if path.parent != path else None
    return {"path": str(path), "parent": parent, "entries": entries}


def _api_scan(data: dict) -> dict:
    root = _require_dir(data)
    files = scan_project_files(root)
    if not files:
        raise _ApiError(400, "No text files found in the selected folder.")
    return {"root": str(root), "files": files, "tree": generate_tree(root)}


def _api_export(data: dict) -> dict:
    root = _require_dir(data)
    selected = data.get("files")
    if not isinstance(selected, list) or not selected:
        raise _ApiError(400, "No files selected. Check at least one file.")
    md, contents, encodings = export_project(root, include_only=set(selected))
    return {
        "markdown": md,
        "contents": contents,
        "encodings": encodings,
        "tokens": count_tokens(md),
    }


def _api_prompt(data: dict) -> dict:
    md = data.get("markdown")
    if not isinstance(md, str) or not md.strip():
        raise _ApiError(400, "Generate the markdown first.")
    full = generate_full_prompt(md)
    return {
        "full_prompt": full,
        "tokens_md": count_tokens(md),
        "tokens_full": count_tokens(full),
    }


def _api_system_prompt(data: dict) -> dict:
    return {
        "text": FOOLPROOF_PROMPT_TEMPLATE,
        "tokens": count_tokens(FOOLPROOF_PROMPT_TEMPLATE),
    }


def _api_parse(data: dict) -> dict:
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        raise _ApiError(400, "Please paste the AI response first.")
    result = AIResponseParser().parse(text)
    return {"changes": result.changes, "errors": result.errors,
            "warnings": result.warnings}


def _api_apply(data: dict) -> dict:
    changes = data.get("changes")
    if not isinstance(changes, dict) or not changes:
        raise _ApiError(400,
                        "No changes selected. Parse a response and check at least one file.")
    mode = data.get("mode")
    contents = data.get("contents") or {}
    encodings = data.get("encodings") or {}

    if mode == "inplace":
        root = _require_dir(data)
        report = ChangeApplier.apply_inplace(root, changes, contents, encodings)
    elif mode in ("export", "create"):
        dest_raw = str(data.get("dest") or "").strip()
        if not dest_raw:
            raise _ApiError(400, "Please choose a destination folder.")
        dest = Path(dest_raw).expanduser()
        if mode == "export":
            root = _require_dir(data)
            report = ChangeApplier.export_to_new(root, dest, changes,
                                                 contents, encodings)
        else:
            report = ChangeApplier.create_new(dest, changes)
    else:
        raise _ApiError(400, f"Unknown mode: {mode!r}")

    return {"ok": report.ok, "applied": report.applied,
            "skipped": report.skipped, "summary": report.summary()}


def _settings_payload() -> dict:
    cfg = config_module.get_config()
    return {
        "text_extensions": sorted(cfg.text_extensions),
        "excluded_dirs": sorted(cfg.excluded_dirs),
        "max_file_size_kb": cfg.max_file_size_kb,
        "output_auto_save": bool(cfg.output_auto_save),
    }


def _api_config_get(data: dict) -> dict:
    return _settings_payload()


def _api_config_save(data: dict) -> dict:
    exts = data.get("extensions")
    dirs = data.get("excluded_dirs")
    if not isinstance(exts, list) or not isinstance(dirs, list):
        raise _ApiError(400, "extensions and excluded_dirs must be lists.")
    exts = [str(e).strip().lower() for e in exts if str(e).strip()]
    dirs = [str(d).strip() for d in dirs if str(d).strip()]
    if not exts:
        raise _ApiError(400, "At least one text extension must be specified.")
    size = data.get("max_file_size_kb")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise _ApiError(400, "Max file size must be a positive integer (KB).")

    cfg = config_module.get_config()
    cfg.text_extensions = exts
    cfg.excluded_dirs = dirs
    cfg.max_file_size_kb = size
    cfg.output_auto_save = bool(data.get("output_auto_save"))
    utils.reload_config()
    return _settings_payload()


def _api_config_reset(data: dict) -> dict:
    cfg = config_module.get_config()
    cfg.text_extensions = config_module.DEFAULT_CONFIG["text_extensions"]
    cfg.excluded_dirs = config_module.DEFAULT_CONFIG["excluded_dirs"]
    cfg.max_file_size_kb = config_module.DEFAULT_CONFIG["max_file_size_kb"]
    cfg.output_auto_save = config_module.DEFAULT_CONFIG["output_auto_save"]
    utils.reload_config()
    return _settings_payload()


def _api_save_file(data: dict) -> dict:
    raw = str(data.get("path") or "").strip()
    content = data.get("content")
    if not raw:
        raise _ApiError(400, "No path given.")
    if not isinstance(content, str):
        raise _ApiError(400, "No content given.")
    path = Path(raw).expanduser()
    path.write_text(content, encoding="utf-8")  # OSError -> 500 via do_POST
    return {"ok": True, "path": str(path)}


_API_ROUTES = {
    "fs_list": _api_fs_list,
    "scan": _api_scan,
    "export": _api_export,
    "prompt": _api_prompt,
    "system_prompt": _api_system_prompt,
    "parse": _api_parse,
    "apply": _api_apply,
    "config_get": _api_config_get,
    "config_save": _api_config_save,
    "config_reset": _api_config_reset,
    "save_file": _api_save_file,
}


def create_server(port: int = 0, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """Create (but do not start) the HTTP server.

    ``port=0`` asks the OS for any free port; the real port is available as
    ``server.server_address[1]``.  The per-run CSRF token is ``server.token``.

    ``host`` defaults to loopback so nothing outside this machine can reach
    the server.  ``--host 0.0.0.0`` (from ``main.py``'s ``-p/--port`` and
    ``--host`` flags) is the standard way to expose it to a Docker container
    or the local network.
    """
    server = ThreadingHTTPServer((host, port), _Handler)
    server.token = secrets.token_urlsafe(16)  # type: ignore[attr-defined]
    return server
