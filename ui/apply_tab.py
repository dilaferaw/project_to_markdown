"""Apply tab: paste AI response, parse, preview, and apply changes (including patching)."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from core.response_parser import AIResponseParser
from core.applier import ChangeApplier


class ApplyTab(ttk.Frame):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Paste area ---
        lbl = ttk.Label(self, text="Paste AI response below:")
        lbl.grid(row=0, column=0, sticky="w", pady=(0, 2))

        text_frame = ttk.Frame(self)
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        self.ai_response_text = tk.Text(text_frame, wrap=tk.WORD)
        self.ai_response_text.grid(row=0, column=0, sticky="nsew")
        scroll_y = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.ai_response_text.yview)
        scroll_y.grid(row=0, column=1, sticky="ns")
        self.ai_response_text.configure(yscrollcommand=scroll_y.set)

        # --- Parse button ---
        parse_btn = ttk.Button(self, text="Parse Response", command=self._on_parse)
        parse_btn.grid(row=2, column=0, pady=(5, 5), sticky="w")

        # --- Changes tree ---
        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 5))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(tree_frame, columns=("action", "path"), show="tree headings", selectmode="none")
        self.tree.heading("#0", text="Apply?")
        self.tree.heading("path", text="File")
        self.tree.heading("action", text="Action")
        self.tree.column("#0", width=50, stretch=False)
        self.tree.column("action", width=80, stretch=False)
        self.tree.column("path", width=400)
        self.tree.grid(row=0, column=0, sticky="nsew")

        tree_scroll_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        tree_scroll_y.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=tree_scroll_y.set)

        self.tree.bind("<Button-1>", self._on_tree_toggle)

        # --- Mode selection ---
        mode_frame = ttk.Frame(self)
        mode_frame.grid(row=4, column=0, sticky="ew")

        self.mode_var = tk.StringVar(value="inplace")
        ttk.Radiobutton(mode_frame, text="Modify original project (with backup)", variable=self.mode_var,
                        value="inplace").pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(mode_frame, text="Export to new folder from existing project", variable=self.mode_var,
                        value="export").pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(mode_frame, text="Create new project from scratch", variable=self.mode_var,
                        value="create").pack(anchor=tk.W, pady=2)

        # Destination row
        dest_frame = ttk.Frame(self)
        dest_frame.grid(row=5, column=0, sticky="ew", pady=(5, 0))

        self.dest_entry = ttk.Entry(dest_frame)
        self.dest_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.dest_entry.insert(0, "Destination folder...")
        self.dest_entry.configure(state=tk.DISABLED)

        self.dest_browse_btn = ttk.Button(dest_frame, text="Browse...", state=tk.DISABLED, command=self._on_browse_dest)
        self.dest_browse_btn.pack(side=tk.RIGHT)

        self.mode_var.trace_add("write", self._on_mode_changed)

        # --- Apply button ---
        apply_btn = ttk.Button(self, text="Apply Selected Changes", command=self._on_apply)
        apply_btn.grid(row=6, column=0, pady=(10, 0), sticky="w")

    def _on_mode_changed(self, *args):
        mode = self.mode_var.get()
        if mode in ("export", "create"):
            self.dest_entry.configure(state=tk.NORMAL)
            self.dest_browse_btn.configure(state=tk.NORMAL)
        else:
            self.dest_entry.configure(state=tk.DISABLED)
            self.dest_browse_btn.configure(state=tk.DISABLED)

    def _on_browse_dest(self):
        path = filedialog.askdirectory(title="Select Destination Folder", parent=self.app.window)
        if path:
            self.dest_entry.delete(0, tk.END)
            self.dest_entry.insert(0, path)

    def _on_parse(self):
        text = self.ai_response_text.get("1.0", tk.END)
        if not text.strip():
            self.app.show_error("Please paste the AI response first.")
            return
        self.app.parsed_changes = AIResponseParser.parse(text)
        self._populate_tree()

    def _populate_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for path, change in self.app.parsed_changes.items():
            action = change["action"].capitalize()
            self.tree.insert("", "end", text="☑", values=(path, action))

    def _on_tree_toggle(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "tree":
            return
        item = self.tree.identify_row(event.y)
        if not item:
            return
        current_text = self.tree.item(item, "text")
        new_text = "☐" if current_text == "☑" else "☑"
        self.tree.item(item, text=new_text)

    def _on_apply(self):
        mode = self.mode_var.get()
        if mode in ("inplace", "export") and not self.app.current_project_root:
            self.app.show_error("No project loaded. Go to Export tab and scan a project first.")
            return
        if not self.app.parsed_changes:
            self.app.show_error("No parsed changes. Paste and parse an AI response first.")
            return

        selected = {}
        for item in self.tree.get_children():
            if self.tree.item(item, "text") == "☑":
                path = self.tree.item(item, "values")[0]
                if path in self.app.parsed_changes:
                    selected[path] = self.app.parsed_changes[path]

        if not selected:
            self.app.show_error("No changes selected. Check at least one file.")
            return

        try:
            if mode == "inplace":
                answer = messagebox.askyesno("Confirm",
                                             "Modify original project (a backup will be created). Are you sure?",
                                             parent=self.app.window)
                if answer:
                    ChangeApplier.apply_inplace(self.app.current_project_root, selected,
                                                self.app.file_contents)
                    self.app.show_info("Changes applied in-place. Backup created.")
            elif mode == "export":
                dest_path = self.dest_entry.get().strip()
                if not dest_path:
                    self.app.show_error("Please choose a destination folder.")
                    return
                dest = Path(dest_path)
                if dest.exists():
                    self.app.show_error("Destination already exists. Choose a new path.")
                    return
                ChangeApplier.export_to_new(self.app.current_project_root, dest, selected,
                                            self.app.file_contents)
                self.app.show_info(f"Project exported to {dest} with changes applied.")
            elif mode == "create":
                dest_path = self.dest_entry.get().strip()
                if not dest_path:
                    self.app.show_error("Please choose a destination folder.")
                    return
                dest = Path(dest_path)
                if dest.exists():
                    self.app.show_error("Destination already exists. Choose a new path.")
                    return
                ChangeApplier.create_new(dest, selected)
                self.app.show_info(f"New project created at {dest} with all changes applied.")
        except Exception as e:
            self.app.show_error(f"Error applying changes: {e}")