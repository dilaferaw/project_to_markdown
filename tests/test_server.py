"""End-to-end tests for the loopback web server (server.py).

Each test drives a real ``ThreadingHTTPServer`` over HTTP, so request
parsing, token auth, routing and the core modules are all exercised
together -- the same path the browser takes.
"""

import json
import threading
import urllib.error
import urllib.request

import pytest

import server as server_module
from server import create_server

# The response format PTM instructs AIs to emit.
AI_RESPONSE = (
    "Plan: change the greeting.\n\n"
    "--- FILE_START: a.py ---\n"
    "[CODE python]\n"
    'print("hello from the AI")\n'
    "[/CODE]\n"
    "--- FILE_END ---\n"
)

PROJ = {"a.py": "line1\nline2\nline3\n", "pkg/b.py": "x = 1\n",
        "README.md": "# hi\n"}


@pytest.fixture(scope="module")
def web():
    """A running server, shared by every test in this module."""
    srv = create_server()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


def _url(srv, path):
    return f"http://127.0.0.1:{srv.server_address[1]}{path}"


def post(srv, endpoint, data=None, use_token=True):
    """POST JSON to ``/api/<endpoint>``; return ``(status, body_dict)``."""
    headers = {"Content-Type": "application/json"}
    if use_token:
        headers["X-PTM-Token"] = srv.token
    req = urllib.request.Request(
        _url(srv, "/api/" + endpoint),
        data=json.dumps(data or {}).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def get(srv, path):
    with urllib.request.urlopen(_url(srv, path), timeout=10) as resp:
        return resp.status, resp.read().decode("utf-8")


def exported_payload(srv, root):
    """Scan + export ``root``; return the export body (contents/encodings)."""
    status, scan = post(srv, "scan", {"root": str(root)})
    assert status == 200, scan
    status, exp = post(srv, "export",
                       {"root": str(root), "files": scan["files"]})
    assert status == 200, exp
    return exp


class TestFrontend:
    """Static assets and the token handshake."""

    def test_index_injects_token(self, web):
        status, body = get(web, "/")
        assert status == 200
        assert "ProjectToMarkdown" in body
        assert web.token in body
        assert "__PTM_TOKEN__" not in body

    def test_static_js_served(self, web):
        status, body = get(web, "/static/app.js")
        assert status == 200
        assert "X-PTM-Token" in body

    def test_static_css_served(self, web):
        status, body = get(web, "/static/style.css")
        assert status == 200
        assert "--accent" in body

    def test_unknown_static_is_404(self, web):
        with pytest.raises(urllib.error.HTTPError) as exc:
            get(web, "/static/nope.js")
        assert exc.value.code == 404

    def test_api_rejects_missing_token(self, web):
        status, body = post(web, "scan", {"root": "/"}, use_token=False)
        assert status == 403
        assert "token" in body["error"].lower()

    def test_api_rejects_wrong_token(self, web):
        req = urllib.request.Request(
            _url(web, "/api/scan"),
            data=b"{}",
            headers={"Content-Type": "application/json",
                     "X-PTM-Token": "definitely-wrong"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=10)
        assert exc.value.code == 403


    def test_unknown_endpoint_is_404(self, web):
        status, _ = post(web, "definitely_not_an_endpoint")
        assert status == 404


class TestScanExport:
    """Scan and export endpoints."""

    def test_scan_lists_text_files(self, web, make_project):
        root = make_project(PROJ)
        status, body = post(web, "scan", {"root": str(root)})
        assert status == 200
        assert body["root"] == str(root)
        assert set(body["files"]) == {"a.py", "pkg/b.py", "README.md"}
        assert isinstance(body["tree"], str) and body["tree"]

    def test_scan_missing_root_is_400(self, web):
        status, body = post(web, "scan", {"root": "/does/not/exist"})
        assert status == 400
        assert "directory" in body["error"].lower()

    def test_scan_empty_folder_is_400(self, web, tmp_path):
        (tmp_path / "empty").mkdir()
        status, body = post(web, "scan", {"root": str(tmp_path / "empty")})
        assert status == 400
        assert "No text files" in body["error"]

    def test_scan_without_root_is_400(self, web):
        status, _ = post(web, "scan", {})
        assert status == 400

    def test_export_roundtrip(self, web, make_project):
        root = make_project(PROJ)
        exp = exported_payload(web, root)
        assert "a.py" in exp["markdown"]
        assert exp["contents"]["a.py"] == "line1\nline2\nline3\n"
        assert "a.py" in exp["encodings"]
        assert isinstance(exp["tokens"], int) and exp["tokens"] > 0

    def test_export_honours_selected_files(self, web, make_project):
        root = make_project(PROJ)
        status, exp = post(web, "export",
                           {"root": str(root), "files": ["README.md"]})
        assert status == 200
        assert "README.md" in exp["markdown"]
        assert "a.py" not in exp["contents"]

    def test_export_requires_files(self, web, make_project):
        root = make_project(PROJ)
        status, body = post(web, "export", {"root": str(root), "files": []})
        assert status == 400
        assert "No files selected" in body["error"]


class TestPrompt:
    def test_prompt_wraps_markdown(self, web, make_project):
        root = make_project(PROJ)
        exp = exported_payload(web, root)
        status, body = post(web, "prompt", {"markdown": exp["markdown"]})
        assert status == 200
        assert exp["markdown"] in body["full_prompt"]
        assert body["tokens_full"] >= body["tokens_md"] > 0

    def test_prompt_without_markdown_is_400(self, web):
        status, _ = post(web, "prompt", {})
        assert status == 400


    def test_system_prompt(self, web):
        status, body = post(web, "system_prompt")
        assert status == 200
        assert len(body["text"]) > 100
        assert body["tokens"] > 0


class TestParse:
    def test_valid_response(self, web):
        status, body = post(web, "parse", {"text": AI_RESPONSE})
        assert status == 200
        assert body["errors"] == [] and body["warnings"] == []
        assert body["changes"]["a.py"]["action"] == "modify"
        assert "hello from the AI" in body["changes"]["a.py"]["content"]

    def test_empty_text_is_400(self, web):
        status, body = post(web, "parse", {"text": "   "})
        assert status == 400
        assert "paste" in body["error"].lower()

    def test_response_without_markers_warns(self, web):
        status, body = post(web, "parse", {"text": "Just chatting, no markers."})
        assert status == 200
        assert body["changes"] == {}
        assert body["warnings"]


class TestApply:
    def _parsed(self, web):
        status, body = post(web, "parse", {"text": AI_RESPONSE})
        assert status == 200
        return body["changes"]

    def test_inplace_modifies_file_and_creates_backup(self, web, make_project):
        root = make_project(PROJ)
        exp = exported_payload(web, root)
        status, report = post(web, "apply", {
            "mode": "inplace", "root": str(root),
            "changes": self._parsed(web),
            "contents": exp["contents"], "encodings": exp["encodings"],
        })
        assert status == 200, report
        assert report["ok"] is True
        changed = (root / "a.py").read_text(encoding="utf-8")
        assert "hello from the AI" in changed

        backups = list(root.parent.glob(root.name + "_backup_*"))
        assert backups, "inplace apply must leave a backup behind"
        saved = (backups[0] / "a.py").read_text(encoding="utf-8")
        assert saved == "line1\nline2\nline3\n"
        # untouched files stay untouched
        assert (root / "README.md").read_text(encoding="utf-8") == "# hi\n"

    def test_export_mode_copies_project_then_applies(self, web, make_project):
        base = make_project({"proj/a.py": "line1\nline2\nline3\n",
                             "proj/README.md": "# hi\n"})
        root = base / "proj"
        exp = exported_payload(web, root)
        dest = base / "dest"
        status, report = post(web, "apply", {
            "mode": "export", "root": str(root), "dest": str(dest),
            "changes": self._parsed(web),
            "contents": exp["contents"], "encodings": exp["encodings"],
        })
        assert status == 200, report
        assert report["ok"] is True
        changed = (dest / "a.py").read_text(encoding="utf-8")
        assert "hello from the AI" in changed
        # the source project is left alone
        assert (root / "a.py").read_text(encoding="utf-8") == "line1\nline2\nline3\n"

    def test_export_dest_that_exists_is_400(self, web, make_project):
        base = make_project({"proj/a.py": "x\n"})
        root = base / "proj"
        dest = base / "exists"
        dest.mkdir()
        status, _ = post(web, "apply", {
            "mode": "export", "root": str(root), "dest": str(dest),
            "changes": self._parsed(web),
        })
        assert status == 400

    def test_export_dest_inside_source_is_400(self, web, make_project):
        root = make_project(PROJ)
        status, body = post(web, "apply", {
            "mode": "export", "root": str(root), "dest": str(root / "inside"),
            "changes": self._parsed(web),
        })
        assert status == 400
        assert "inside" in body["error"]

    def test_create_mode_builds_project_from_scratch(self, web, tmp_path):
        dest = tmp_path / "brand_new"
        status, report = post(web, "apply", {
            "mode": "create", "dest": str(dest), "changes": self._parsed(web),
        })
        assert status == 200, report
        assert report["ok"] is True
        created = (dest / "a.py").read_text(encoding="utf-8")
        assert "hello from the AI" in created

    def test_create_mode_dest_exists_is_400(self, web, tmp_path):
        dest = tmp_path / "already_here"
        dest.mkdir()
        status, _ = post(web, "apply", {
            "mode": "create", "dest": str(dest), "changes": self._parsed(web),
        })
        assert status == 400

    def test_apply_without_changes_is_400(self, web, make_project):
        root = make_project(PROJ)
        status, _ = post(web, "apply",
                         {"mode": "inplace", "root": str(root), "changes": {}})
        assert status == 400

    def test_apply_unknown_mode_is_400(self, web):
        status, _ = post(web, "apply", {
            "mode": "sideways",
            "changes": {"a.py": {"action": "modify", "content": "x"}},
        })
        assert status == 400

    def test_apply_inplace_without_root_is_400(self, web):
        status, _ = post(web, "apply", {
            "mode": "inplace",
            "changes": {"a.py": {"action": "modify", "content": "x"}},
        })
        assert status == 400


    def test_apply_export_without_dest_is_400(self, web, make_project):
        root = make_project(PROJ)
        status, _ = post(web, "apply", {
            "mode": "export", "root": str(root),
            "changes": {"a.py": {"action": "modify", "content": "x"}},
        })
        assert status == 400


class TestConfig:
    """Config endpoints, backed by a temp Config so this machine's real
    settings file is never touched by the test run."""

    @pytest.fixture
    def cfg(self, monkeypatch, tmp_path):
        from core.config import Config
        conf = Config.__new__(Config)
        conf.config_dir = tmp_path / "config-dir"
        conf.config_file = conf.config_dir / "config.json"
        conf.data = {}
        conf.load()
        monkeypatch.setattr(server_module.config_module, "get_config",
                            lambda: conf)
        return conf

    def test_get_returns_full_shape(self, web, cfg):
        status, body = post(web, "config_get")
        assert status == 200
        assert set(body) == {"text_extensions", "excluded_dirs",
                             "max_file_size_kb", "output_auto_save"}
        assert body["text_extensions"] and body["excluded_dirs"]

    def test_save_normalises_and_persists(self, web, cfg):
        from core.config import Config
        status, body = post(web, "config_save", {
            "extensions": ["py", ".RS", " "],
            "excluded_dirs": ["build/", "  "],
            "max_file_size_kb": 77,
            "output_auto_save": True,
        })
        assert status == 200, body
        assert ".py" in body["text_extensions"]
        assert ".rs" in body["text_extensions"]
        assert body["excluded_dirs"] == ["build"]
        assert body["max_file_size_kb"] == 77
        assert body["output_auto_save"] is True

        clone = Config.__new__(Config)
        clone.config_dir = cfg.config_dir
        clone.config_file = cfg.config_file
        clone.data = {}
        clone.load()
        assert clone.max_file_size_kb == 77

    def test_save_rejects_non_positive_size(self, web, cfg):
        status, body = post(web, "config_save", {
            "extensions": [".py"], "excluded_dirs": [],
            "max_file_size_kb": 0, "output_auto_save": False,
        })
        assert status == 400
        assert "positive" in body["error"]

    def test_save_rejects_non_integer_size(self, web, cfg):
        status, body = post(web, "config_save", {
            "extensions": [".py"], "excluded_dirs": [],
            "max_file_size_kb": "abc", "output_auto_save": False,
        })
        assert status == 400

    def test_save_rejects_empty_extensions(self, web, cfg):
        status, body = post(web, "config_save", {
            "extensions": [], "excluded_dirs": [],
            "max_file_size_kb": 10, "output_auto_save": False,
        })
        assert status == 400
        assert "extension" in body["error"].lower()

    def test_save_requires_lists(self, web, cfg):
        status, _ = post(web, "config_save", {
            "extensions": "py", "excluded_dirs": [],
            "max_file_size_kb": 10, "output_auto_save": False,
        })
        assert status == 400

    def test_reset_restores_defaults(self, web, cfg):
        from core.config import DEFAULT_CONFIG
        status, _ = post(web, "config_save", {
            "extensions": [".zz"], "excluded_dirs": ["only"],
            "max_file_size_kb": 77, "output_auto_save": True,
        })
        assert status == 200
        status, body = post(web, "config_reset")
        assert status == 200
        assert body["max_file_size_kb"] == DEFAULT_CONFIG["max_file_size_kb"]
        assert set(body["text_extensions"]) == set(DEFAULT_CONFIG["text_extensions"])
        assert set(body["excluded_dirs"]) == set(DEFAULT_CONFIG["excluded_dirs"])


class TestFileSystemHelpers:
    def test_fs_list_shows_dirs_first(self, web, make_project):
        root = make_project({"a/b.txt": "x\n", "c.txt": "y\n"})
        status, body = post(web, "fs_list", {"path": str(root)})
        assert status == 200
        names = [e["name"] for e in body["entries"]]
        assert names[0] == "a"
        by_name = {e["name"]: e for e in body["entries"]}
        assert by_name["a"]["is_dir"] is True
        assert by_name["c.txt"]["is_dir"] is False
        assert body["parent"] is not None

    def test_fs_list_on_a_file_is_400(self, web, make_project):
        root = make_project({"a.txt": "x\n"})
        status, _ = post(web, "fs_list", {"path": str(root / "a.txt")})
        assert status == 400

    def test_fs_list_defaults_to_home(self, web):
        status, body = post(web, "fs_list", {})
        assert status == 200
        assert body["path"]

    def test_save_file_writes_content(self, web, tmp_path):
        target = tmp_path / "out.md"
        status, body = post(web, "save_file",
                            {"path": str(target), "content": "# saved\n"})
        assert status == 200
        assert target.read_text(encoding="utf-8") == "# saved\n"

    def test_save_file_without_path_is_400(self, web):
        status, _ = post(web, "save_file", {"content": "x"})
        assert status == 400

    def test_save_file_into_missing_directory_fails(self, web, tmp_path):
        status, _ = post(web, "save_file", {
            "path": str(tmp_path / "no" / "dir" / "f.md"), "content": "x",
        })
        assert status >= 400
