# Copyright 2025 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

from gi.repository import Adw, Gio, Gtk

from .settings import Settings


@Gtk.Template(
    resource_path="/io/github/cleomenezesjr/Serigy/gtk/preferences.ui"
)
class PreferencesDialog(Adw.PreferencesDialog):
    __gtype_name__ = "PreferencesDialog"

    auto_arrange: Adw.SwitchRow = Gtk.Template.Child()
    number_slots: Adw.ComboRow = Gtk.Template.Child()

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)

        Settings.get().bind(
            "auto-arrange",
            self.auto_arrange,
            "active",
            Gio.SettingsBindFlags.DEFAULT,
        )

        Settings.get().bind(
            "number-slots",
            self.number_slots,
            "selected",
            Gio.SettingsBindFlags.DEFAULT,
        )
