# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

from gi.repository import Adw, Gio, Gtk

from serigy.define import RESOURCE_PATH
from serigy.settings import Settings


@Gtk.Template(resource_path=f"{RESOURCE_PATH}/gtk/preferences.ui")
class PreferencesDialog(Adw.PreferencesDialog):
    __gtype_name__ = "PreferencesDialog"

    incognito_mode: Adw.SwitchRow = Gtk.Template.Child()
    auto_arrange: Adw.SwitchRow = Gtk.Template.Child()
    auto_clear_enabled: Adw.ExpanderRow = Gtk.Template.Child()
    auto_clear_minutes: Adw.ComboRow = Gtk.Template.Child()
    number_slots: Adw.ComboRow = Gtk.Template.Child()

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)

        Settings.get().bind(
            "incognito-mode",
            self.incognito_mode,
            "active",
            Gio.SettingsBindFlags.DEFAULT,
        )

        Settings.get().bind(
            "auto-arrange",
            self.auto_arrange,
            "active",
            Gio.SettingsBindFlags.DEFAULT,
        )

        Settings.get().bind(
            "auto-clear-enabled",
            self.auto_clear_enabled,
            "enable-expansion",
            Gio.SettingsBindFlags.DEFAULT,
        )

        Settings.get().bind(
            "auto-clear-minutes",
            self.auto_clear_minutes,
            "selected",
            Gio.SettingsBindFlags.DEFAULT,
        )

        Settings.get().bind(
            "number-slots",
            self.number_slots,
            "selected",
            Gio.SettingsBindFlags.DEFAULT,
        )
