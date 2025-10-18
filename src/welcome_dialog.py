# Copyright 2024 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

# import asyncio
# import os
# from datetime import datetime as dt

from gi.repository import Adw, Gdk, Gio, Gtk

from .settings import Settings
from .setup_shortcut_portal import setup as setup_shortcut_portal


@Gtk.Template(
    resource_path="/io/github/cleomenezesjr/Serigy/gtk/welcome-dialog.ui"
)
class WelcomeDialog(Adw.Dialog):
    __gtype_name__ = "WelcomeDialog"

    # Child widgets
    carousel: Adw.Carousel = Gtk.Template.Child()
    toolbar_view: Adw.ToolbarView = Gtk.Template.Child()
    agreement_btn: Gtk.Button = Gtk.Template.Child()

    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app

    @Gtk.Template.Callback()
    def on_complete_setup(self, *args: tuple) -> None:
        portal_session = setup_shortcut_portal(self.app)
        if portal_session:
            Settings.get().welcome: bool = False
            self.force_close()
