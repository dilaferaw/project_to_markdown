"""Export tab: project selection, markdown generation, clipboard/save."""

import subprocess
import shutil
import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path
from core.markdown_builder import export_project
from core.prompt_template import generate_full_prompt, FOOLPROOF_PROMPT_TEMPLATE
from utils import count_tokens


class ExportTab(ttk.Frame):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Project selection row ---
        sel_frame = ttk.Frame(self)
        sel_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))

        self.project_entry = ttk.Entry(sel_frame)
        self.project_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.project_entry.insert(0, "Project folder path...")

        browse_btn = ttk.Button(sel_frame, text="Browse...", command=self._on_browse_project)
        browse_btn.pack(side=tk.RIGHT)

        # --- Generate button ---
        self.generate_btn = ttk.Button(self, text="Scan & Generate Markdown", command=self._on_generate)
        self.generate_btn.grid(row=2, column=0, pady=(0, 5), sticky="w")

        # --- Preview area ---
        preview_frame = ttk.Frame(self)
        preview_frame.grid(row=1, column=0, sticky="nsew")
        preview_frame.grid_rowconfigure(0, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)

        self.preview_text = tk.Text(
            preview_frame,
            wrap=tk.NONE,
            bg="#2d2d2d",
            fg="#dcdcdc",
            insertbackground="#dcdcdc",
            relief="flat",
            borderwidth=0,
            padx=8,
            pady=8,
            state=tk.DISABLED,
        )
        self.preview_text.grid(row=0, column=0, sticky="nsew")

        preview_scroll_y = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.preview_text.yview)
        preview_scroll_y.grid(row=0, column=1, sticky="ns")
        preview_scroll_x = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, command=self.preview_text.xview)
        preview_scroll_x.grid(row=1, column=0, sticky="ew")
        self.preview_text.configure(yscrollcommand=preview_scroll_y.set, xscrollcommand=preview_scroll_x.set)

        # --- Action buttons ---
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=3, column=0, pady=(5, 0), sticky="ew")

        self.copy_md_btn = ttk.Button(btn_frame, text="Copy Markdown", command=self._on_copy_md, state=tk.DISABLED)
        self.copy_md_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.save_md_btn = ttk.Button(btn_frame, text="Save Markdown...", command=self._on_save_md, state=tk.DISABLED)
        self.save_md_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.prompt_btn = ttk.Button(btn_frame, text="Full Prompt & Copy", command=self._on_generate_prompt, state=tk.DISABLED)
        self.prompt_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.system_prompt_btn = ttk.Button(btn_frame, text="Copy System Prompt", command=self._on_copy_system_prompt)
        self.system_prompt_btn.pack(side=tk.LEFT)

        # --- Token info ---
        self.token_label = ttk.Label(self, text="")
        self.token_label.grid(row=4, column=0, pady=(5, 0), sticky="w")

    # -----------------------------------------------------------------
    # Clipboard helper
    # -----------------------------------------------------------------
    def _copy_to_clipboard(self, text: str, success_msg: str):
        if shutil.which("xclip"):
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text.encode("utf-8"),
                    check=True,
                )
                self.app.show_info(success_msg)
                return
            except Exception:
                pass
        if shutil.which("wl-copy"):
            try:
                subprocess.run(
                    ["wl-copy"],
                    input=text.encode("utf-8"),
                    check=True,
                )
                self.app.show_info(success_msg)
                return
            except Exception:
                pass
        try:
            self.app.window.clipboard_clear()
            self.app.window.clipboard_append(text)
            self.app.show_info(success_msg)
        except Exception as e:
            self.app.show_error(
                f"Clipboard copy failed.\n\n"
                f"Install xclip (sudo apt install xclip) or wl-clipboard for reliable copying.\n\n"
                f"Error: {e}"
            )

    # -----------------------------------------------------------------
    # Event handlers
    # -----------------------------------------------------------------
    def _on_browse_project(self):
        path = filedialog.askdirectory(title="Select Project Folder", parent=self.app.window)
        if path:
            self.project_entry.delete(0, tk.END)
            self.project_entry.insert(0, path)

    def _on_generate(self):
        project_path = self.project_entry.get().strip()
        if not project_path or not Path(project_path).is_dir():
            self.app.show_error("Please select a valid project folder.")
            return
        self.app.current_project_root = Path(project_path)
        self.generate_btn.configure(text="Generating...", state=tk.DISABLED)
        self.update_idletasks()
        try:
            md, contents = export_project(self.app.current_project_root)
            self.app.generated_markdown = md
            self.app.file_contents = contents
            self._update_preview(md)
        except Exception as e:
            self.app.show_error(f"Export failed: {e}")
        finally:
            self.generate_btn.configure(text="Scan & Generate Markdown", state=tk.NORMAL)

    def _update_preview(self, md):
        self.preview_text.configure(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert(tk.END, md)
        self.preview_text.configure(state=tk.DISABLED)

        self.copy_md_btn.configure(state=tk.NORMAL)
        self.save_md_btn.configure(state=tk.NORMAL)
        self.prompt_btn.configure(state=tk.NORMAL)

        tokens = count_tokens(md)
        self.token_label.configure(text=f"Markdown tokens: ~{tokens}")

    def _on_copy_md(self):
        self._copy_to_clipboard(self.app.generated_markdown, "Markdown copied to clipboard.")

    def _on_save_md(self):
        path = filedialog.asksaveasfilename(
            title="Save Markdown File",
            parent=self.app.window,
            defaultextension=".md",
            filetypes=[("Markdown files", "*.md"), ("All files", "*.*")],
        )
        if path:
            try:
                Path(path).write_text(self.app.generated_markdown, encoding="utf-8")
                self.app.show_info(f"Markdown saved to {path}")
            except Exception as e:
                self.app.show_error(f"Failed to save: {e}")

    def _on_generate_prompt(self):
        full_prompt = generate_full_prompt(self.app.generated_markdown)
        self._copy_to_clipboard(full_prompt, "Full prompt (with foolproof instructions) copied to clipboard.")
        tokens_full = count_tokens(full_prompt)
        tokens_md = count_tokens(self.app.generated_markdown)
        self.token_label.configure(text=f"Markdown tokens: ~{tokens_md}  |  Full prompt tokens: ~{tokens_full}")

    def _on_copy_system_prompt(self):
        self._copy_to_clipboard(FOOLPROOF_PROMPT_TEMPLATE, "System prompt copied to clipboard.")