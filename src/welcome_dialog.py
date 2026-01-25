# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

from gi.repository import Adw, Gtk

from serigy.define import RESOURCE_PATH
from serigy.settings import Settings


@Gtk.Template(resource_path=f"{RESOURCE_PATH}/gtk/welcome-dialog.ui")
class WelcomeDialog(Adw.Dialog):
    __gtype_name__ = "WelcomeDialog"

    close_button: Gtk.Button = Gtk.Template.Child()
    dont_show_again: Gtk.CheckButton = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.close_button.connect("clicked", self._on_close)

    def _on_close(self, button):
        if self.dont_show_again.get_active():
            Settings.get().show_welcome = False
        self.force_close()
