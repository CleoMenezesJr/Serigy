# Copyright 2021 Rafael Mardojai CM, 2025 Cleo Menezes Jr.
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

    """ Slots """

    @property
    def slots(self) -> GLib.Variant:
        return self.get_value("slots")

    @slots.setter
    def slots(self, slots: GLib.Variant) -> None:
        self.set_value("slots", slots)

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

    """ Image Polling """

    @property
    def image_polling(self) -> bool:
        return self.get_boolean("image-polling")

    @image_polling.setter
    def image_polling(self, value: bool) -> None:
        self.set_boolean("image-polling", value)

    """ Incognito Mode """

    @property
    def incognito_mode(self) -> bool:
        return self.get_boolean("incognito-mode")

    @incognito_mode.setter
    def incognito_mode(self, value: bool) -> None:
        self.set_boolean("incognito-mode", value)
