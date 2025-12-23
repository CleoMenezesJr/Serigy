# Copyright 2024 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import gi
from serigy.clipboard_manager import ClipboardManager

gi.require_versions({"Gtk": "4.0", "Adw": "1", "GdkPixbuf": "2.0"})

if gi:
    from gi.repository import Adw, GLib, Gtk


@Gtk.Template(
    resource_path="/io/github/cleomenezesjr/Serigy/gtk/copy-alert-window.ui"
)
class CopyAlertWindow(Adw.Window):
    __gtype_name__ = "CopyAlertWindow"

    def __init__(self, main_window, **kwargs):
        super().__init__(**kwargs)

        self.main_window = main_window
        self.application = kwargs["application"]
        self.clipboard_manager = ClipboardManager(
            lambda: self.main_window, self.application
        )

        self.set_opacity(0)

        self.connect("show", lambda _: self.on_show())

    def on_show(self):
        # Initial delay to ensure clipboard is ready/stable
        GLib.timeout_add(100, self._start_processing)

    def _start_processing(self):
        self.clipboard_manager.process_clipboard(on_finish=self.close)
