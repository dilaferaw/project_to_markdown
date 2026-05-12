"""Settings tab – allows editing of config values, with a safety reset."""

import tkinter as tk
from tkinter import ttk, messagebox
from core.config import get_config, DEFAULT_CONFIG


class SettingsTab(ttk.Frame):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.config = get_config()
        self.grid_columnconfigure(0, weight=1)

        # ----- Extensions editor -----
        ext_frame = ttk.LabelFrame(self, text="Text File Extensions")
        ext_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        ext_frame.columnconfigure(0, weight=1)

        self.ext_text = tk.Text(ext_frame, height=5, bg="#2d2d2d", fg="#dcdcdc", insertbackground="#dcdcdc")
        self.ext_text.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self._populate_extensions(self.config.text_extensions)

        # ----- Excluded directories editor -----
        dir_frame = ttk.LabelFrame(self, text="Excluded Directories")
        dir_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        self.dir_text = tk.Text(dir_frame, height=4, bg="#2d2d2d", fg="#dcdcdc", insertbackground="#dcdcdc")
        self.dir_text.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self._populate_directories(self.config.excluded_dirs)

        # ----- Max file size -----
        size_frame = ttk.Frame(self)
        size_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        ttk.Label(size_frame, text="Max File Size (KB):").pack(side=tk.LEFT)
        self.size_var = tk.StringVar(value=str(self.config.max_file_size_kb))
        self.size_entry = ttk.Entry(size_frame, textvariable=self.size_var, width=10)
        self.size_entry.pack(side=tk.LEFT, padx=5)

        # ----- Auto-save toggle -----
        self.auto_save_var = tk.BooleanVar(value=self.config.output_auto_save)
        auto_save_cb = ttk.Checkbutton(self, text="Auto‑save output to project folder",
                                       variable=self.auto_save_var)
        auto_save_cb.grid(row=3, column=0, sticky="w", padx=10, pady=5)

        # ----- Buttons -----
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=10)

        reset_btn = ttk.Button(btn_frame, text="Reset to Defaults", command=self._on_reset)
        reset_btn.pack(side=tk.LEFT, padx=(0, 5))

        save_btn = ttk.Button(btn_frame, text="Save Settings", command=self._on_save)
        save_btn.pack(side=tk.LEFT, padx=(0, 5))

        # About button
        about_btn = ttk.Button(self, text="About", command=self.app.show_about_dialog)
        about_btn.grid(row=5, column=0, pady=5, padx=10, sticky="w")

    def _populate_extensions(self, exts):
        self.ext_text.delete("1.0", tk.END)
        self.ext_text.insert("1.0", "\n".join(sorted(exts)))

    def _populate_directories(self, dirs):
        self.dir_text.delete("1.0", tk.END)
        self.dir_text.insert("1.0", "\n".join(sorted(dirs)))

    def _on_save(self):
        # Parse extensions
        ext_lines = self.ext_text.get("1.0", tk.END).strip().splitlines()
        exts = [e.strip().lower() for e in ext_lines if e.strip()]
        if not exts:
            messagebox.showerror("Error", "At least one text extension must be specified.")
            return

        # Parse directories
        dir_lines = self.dir_text.get("1.0", tk.END).strip().splitlines()
        dirs = [d.strip() for d in dir_lines if d.strip()]

        # Parse size
        try:
            size = int(self.size_var.get())
            if size <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Max file size must be a positive integer (KB).")
            return

        # Update config
        self.config.text_extensions = exts
        self.config.excluded_dirs = dirs
        self.config.max_file_size_kb = size
        self.config.output_auto_save = self.auto_save_var.get()

        # Force reload constants in utils so other modules pick up changes
        import utils
        utils.reload_config()

        messagebox.showinfo("Success", "Settings saved. Changes will apply after the next scan.")

    def _on_reset(self):
        if not messagebox.askyesno("Reset Settings",
                                   "Restore all settings to their original defaults?"):
            return
        # Restore config to defaults
        self.config.text_extensions = DEFAULT_CONFIG["text_extensions"]
        self.config.excluded_dirs = DEFAULT_CONFIG["excluded_dirs"]
        self.config.max_file_size_kb = DEFAULT_CONFIG["max_file_size_kb"]
        self.config.output_auto_save = DEFAULT_CONFIG["output_auto_save"]

        # Refresh UI fields
        self._populate_extensions(self.config.text_extensions)
        self._populate_directories(self.config.excluded_dirs)
        self.size_var.set(str(self.config.max_file_size_kb))
        self.auto_save_var.set(self.config.output_auto_save)

        # Also refresh the constants in utils
        import utils
        utils.reload_config()

        messagebox.showinfo("Defaults Restored", "Settings have been reset to defaults.")