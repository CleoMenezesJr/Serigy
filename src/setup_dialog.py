# Copyright 2024 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

# import asyncio
# import os
# from datetime import datetime as dt

from gi.repository import Adw, Gdk, Gio, Gtk

from .settings import Settings


@Gtk.Template(
    resource_path="/io/github/cleomenezesjr/Serigy/gtk/setup-dialog.ui"
)
class SetupDialog(Adw.Dialog):
    __gtype_name__ = "SetupDialog"

    # Child widgets
    carousel: Adw.Carousel = Gtk.Template.Child()
    toolbar_view: Adw.ToolbarView = Gtk.Template.Child()
    stack_modal: Gtk.Stack = Gtk.Template.Child()
    textview_pin_cb: Gtk.TextView = Gtk.Template.Child()
    copy_pin_clipboard_cmd: Gtk.Button = Gtk.Template.Child()
    textview_open_serigy: Gtk.TextView = Gtk.Template.Child()
    copy_open_serigy_cmd: Gtk.Button = Gtk.Template.Child()
    agreement_btn: Gtk.Button = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Initial state
        _pin_clipboard_cmd = (
            "flatpak run io.github.cleomenezesjr.Serigy --copy"
        )
        self.textview_pin_cb.get_buffer().set_text(_pin_clipboard_cmd)
        self.copy_pin_clipboard_cmd.connect(
            "clicked",
            lambda *args: self.copy_to_clipboard(_pin_clipboard_cmd),
        )

        _open_serigy_cmd = "flatpak run io.github.cleomenezesjr.Serigy"
        self.textview_open_serigy.get_buffer().set_text(_open_serigy_cmd)
        self.copy_open_serigy_cmd.connect(
            "clicked",
            lambda *args: self.copy_to_clipboard(_open_serigy_cmd),
        )
        self.carousel.connect("page-changed", self.activate_complete_setup)

    def activate_complete_setup(self, *args: tuple) -> None:
        if self.carousel.get_position() == 5.0:
            self.agreement_btn.props.sensitive = True

    def copy_to_clipboard(self, text):
        clipboard = Gdk.Display().get_default().get_clipboard()
        clipboard.set(text)

    @Gtk.Template.Callback()
    def on_agreed(self, *args: tuple) -> None:
        self.carousel.props.interactive = True
        self.toolbar_view.props.reveal_top_bars = True
        self.toolbar_view.set_reveal_bottom_bars(True)
        self.stack_modal.props.visible_child_name = "agreed"

    @Gtk.Template.Callback()
    def on_complete_setup(self, *args: tuple) -> None:
        Settings.get().welcome: bool = False
        self.force_close()
