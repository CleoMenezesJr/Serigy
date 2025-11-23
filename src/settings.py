# Copyright 2021 Rafael Mardojai CM, 2025 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Self

from gi.repository import Gio, GLib, GObject


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
        super().__init__(schema_id="io.github.cleomenezesjr.Serigy")

    """ Slots """

    @property
    def slots(self) -> GLib.Variant:
        return self.get_value("slots")

    @slots.setter
    def slots(self, slots: GLib.Variant) -> None:
        self.set_value("slots", slots)

    """ Welcome Window """

    @property
    def welcome(self) -> bool:
        return self.get_boolean("show-welcome-window")

    @welcome.setter
    def welcome(self, do_show: bool) -> None:
        self.set_boolean("show-welcome-window", do_show)

    """ Auto Arrange  """

    @property
    def auto_arrange(self) -> bool:
        return self.get_boolean("auto-arrange")

    @auto_arrange.setter
    def auto_arrange(self, do_arrange: bool) -> None:
        self.set_boolean("auto-arrange", do_arrange)

    """ Number of Slots  """

    @property
    def number_slots(self) -> int:
        return self.get_int("number-slots")

    @property
    def number_slots_value(self) -> str:
        """Return real number of slots."""
        value = self.number_slots

        if value == 0:
            return 6
        if value == 1:
            return 9
        if value == 2:
            return 12

    """ Alert Window Opacity """

    @property
    def alert_window_opacity(self) -> GLib.Variant:
        return self.get_int("alert-window-opacity")

    @alert_window_opacity.setter
    def alert_window_opacity(self, opacity: GLib.Variant) -> None:
        self.set_int("alert-window-opacity", opacity)

    """ Skip Duplicate Copy  """

    @property
    def skip_duplicate_copy(self) -> bool:
        return self.get_boolean("skip-duplicate-copy")

    @skip_duplicate_copy.setter
    def skip_duplicate_copy(self, do_skip: bool) -> None:
        self.set_boolean("skip-duplicate-copy", do_skip)
