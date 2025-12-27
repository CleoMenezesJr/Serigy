# Copyright 2024-2025 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

from gi.repository import Adw, Gio, Gtk

from serigy.define import RESOURCE_PATH
from serigy.settings import Settings


@Gtk.Template(resource_path=f"{RESOURCE_PATH}/gtk/preferences.ui")
class PreferencesDialog(Adw.PreferencesDialog):
    __gtype_name__ = "PreferencesDialog"

    auto_arrange: Adw.SwitchRow = Gtk.Template.Child()
    image_polling: Adw.SwitchRow = Gtk.Template.Child()
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
            "image-polling",
            self.image_polling,
            "active",
            Gio.SettingsBindFlags.DEFAULT,
        )

        Settings.get().bind(
            "number-slots",
            self.number_slots,
            "selected",
            Gio.SettingsBindFlags.DEFAULT,
        )
