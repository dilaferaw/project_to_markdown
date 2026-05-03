#!/usr/bin/env python3
"""ProjectToMarkdown – cross‑platform edition (Tkinter)"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from ui.export_tab import ExportTab
from ui.apply_tab import ApplyTab
from ui.settings_tab import SettingsTab

APP_VERSION = "1.0.0"


class ProjectToMarkdownApp:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("ProjectToMarkdown")
        self.window.geometry("1000x700")
        self.window.minsize(800, 500)

        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Shared state
        self.current_project_root = None
        self.generated_markdown = ""
        self.parsed_changes = {}
        self.file_contents = {}   # relative path -> original content (for patching)

        # Tabs
        self.export_tab = ExportTab(self)
        self.apply_tab = ApplyTab(self)
        self.settings_tab = SettingsTab(self)

        self.notebook.add(self.export_tab, text="Export")
        self.notebook.add(self.apply_tab, text="Project Builder")
        self.notebook.add(self.settings_tab, text="Settings")

        self.window.mainloop()

    def show_error(self, message):
        messagebox.showerror("Error", message, parent=self.window)

    def show_info(self, message):
        messagebox.showinfo("Info", message, parent=self.window)

    def show_about_dialog(self):
        messagebox.showinfo(
            "About ProjectToMarkdown",
            f"ProjectToMarkdown v{APP_VERSION}\n\n"
            "Bridge your local projects to free chat LLMs.\n"
            "https://github.com/example/project-to-markdown\n\n"
            "Developed by Your Name",
            parent=self.window,
        )


if __name__ == "__main__":
    ProjectToMarkdownApp()