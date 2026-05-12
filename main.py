#!/usr/bin/env python3
"""ProjectToMarkdown – cross‑platform edition (Tkinter)"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from ui.export_tab import ExportTab
from ui.apply_tab import ApplyTab
from ui.settings_tab import SettingsTab

APP_VERSION = "1.0.0"


def apply_dark_theme(root):
    """Force a dark colour scheme on the entire app."""
    style = ttk.Style(root)
    # Use a base theme that supports customisation (clam works everywhere)
    style.theme_use("clam")

    # ----- colour palette -----
    bg = "#1e1e1e"
    fg = "#dcdcdc"
    select_bg = "#3a3a3a"
    accent = "#e53935"

    root.configure(bg=bg)

    # General widget defaults
    style.configure(".", background=bg, foreground=fg, fieldbackground=bg)
    style.configure("TLabel", background=bg, foreground=fg)
    style.configure("TFrame", background=bg)
    style.configure("TLabelframe", background=bg, foreground=fg)
    style.configure("TLabelframe.Label", background=bg, foreground=fg)
    style.configure("TNotebook", background=bg, borderwidth=0)
    style.configure("TNotebook.Tab", background=select_bg, foreground=fg, padding=[12, 4])
    style.map("TNotebook.Tab", background=[("selected", accent)], foreground=[("selected", "#ffffff")])

    style.configure("TButton", background=select_bg, foreground=fg, borderwidth=1, padding=6)
    style.map("TButton", background=[("active", accent)], foreground=[("active", "#ffffff")])

    style.configure("TEntry", fieldbackground="#2d2d2d", foreground=fg, insertcolor=fg)
    style.configure("TRadiobutton", background=bg, foreground=fg)
    style.configure("TCheckbutton", background=bg, foreground=fg)

    style.configure("Treeview", background="#2d2d2d", foreground=fg, fieldbackground="#2d2d2d")
    style.map("Treeview", background=[("selected", accent)], foreground=[("selected", "#ffffff")])

    style.configure("TProgressbar", background=accent, troughcolor="#2d2d2d", bordercolor="#2d2d2d")
    style.configure("TScrollbar", background=select_bg, troughcolor=bg, bordercolor=bg, arrowcolor=fg)
    style.map("TScrollbar", background=[("active", accent)])

    style.configure("TSeparator", background=select_bg)

    # Make the window background consistent
    root.configure(bg=bg)


class ProjectToMarkdownApp:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("ProjectToMarkdown")
        self.window.geometry("1000x700")
        self.window.minsize(800, 500)

        # ----- apply dark theme -----------------
        apply_dark_theme(self.window)

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
            "https://github.com/dilaferaw/project-to-markdown\n\n"
            "Developed by Dilaferaw",
            parent=self.window,
        )


if __name__ == "__main__":
    ProjectToMarkdownApp()