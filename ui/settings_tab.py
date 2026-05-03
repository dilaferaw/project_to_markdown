"""Settings tab (placeholder)."""

import tkinter as tk
from tkinter import ttk


class SettingsTab(ttk.Frame):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.grid_columnconfigure(0, weight=1)

        info = (
            "Edit utils.py to change default text file extensions,\n"
            "excluded directories, or maximum file size.\n\n"
            "Restart the application after changes."
        )
        lbl = ttk.Label(self, text=info, justify=tk.LEFT)
        lbl.grid(row=0, column=0, pady=10, padx=10, sticky="w")

        about_btn = ttk.Button(self, text="About", command=self.app.show_about_dialog)
        about_btn.grid(row=1, column=0, pady=5, padx=10, sticky="w")