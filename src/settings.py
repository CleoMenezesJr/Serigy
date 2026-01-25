# Copyright 2021 Rafael Mardojai CM, 2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Self

from gi.repository import Gio, GLib, GObject

from serigy.define import APP_ID


class Settings(Gio.Settings):
    _instance = None
    _presets_settings: dict = {}

    __gsignals__ = {
        "preset-changed": (GObject.SIGNAL_RUN_FIRST, None, (str,)),
    }

    @classmethod
    def get(cls: GObject) -> Self:
        """Return an active instance of Settings."""
        if cls._instance is None:
            cls._instance = Settings()
        return cls._instance

    def __init__(self):
        super().__init__(schema_id=APP_ID)

    # Slots

    @property
    def slots(self) -> GLib.Variant:
        return self.get_value("slots")

    @slots.setter
    def slots(self, slots: GLib.Variant) -> None:
        self.set_value("slots", slots)

    # Auto Arrange

    @property
    def auto_arrange(self) -> bool:
        return self.get_boolean("auto-arrange")

    @auto_arrange.setter
    def auto_arrange(self, do_arrange: bool) -> None:
        self.set_boolean("auto-arrange", do_arrange)

    # Number of Slots

    @property
    def number_slots(self) -> int:
        return self.get_int("number-slots")

    @property
    def number_slots_value(self) -> int:
        """Return real number of slots."""
        values = {0: 6, 1: 9, 2: 12}
        return values.get(self.number_slots, 9)

    # Incognito Mode

    @property
    def incognito_mode(self) -> bool:
        return self.get_boolean("incognito-mode")

    @incognito_mode.setter
    def incognito_mode(self, value: bool) -> None:
        self.set_boolean("incognito-mode", value)

    # Auto-Clear

    @property
    def auto_clear_enabled(self) -> bool:
        return self.get_boolean("auto-clear-enabled")

    @auto_clear_enabled.setter
    def auto_clear_enabled(self, value: bool) -> None:
        self.set_boolean("auto-clear-enabled", value)

    @property
    def auto_clear_minutes(self) -> int:
        return self.get_int("auto-clear-minutes")

    @auto_clear_minutes.setter
    def auto_clear_minutes(self, value: int) -> None:
        self.set_int("auto-clear-minutes", value)

    @property
    def auto_clear_minutes_value(self) -> int:
        """Return actual minutes from index."""
        values = [5, 10, 15, 30, 60]
        index = self.auto_clear_minutes
        return values[index] if 0 <= index < len(values) else 10

    # Welcome Dialog

    @property
    def show_welcome(self) -> bool:
        return self.get_boolean("show-welcome")

    @show_welcome.setter
    def show_welcome(self, value: bool) -> None:
        self.set_boolean("show-welcome", value)

