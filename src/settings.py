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
