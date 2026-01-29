# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import time

from gi.repository import GLib

from serigy.settings import Settings


class AutoCleaner:
    """Handles automatic clearing of expired clipboard items."""

    def __init__(self, get_window_callback):
        self._timer_id = None
        self._get_window = get_window_callback
        Settings.get().connect(
            "changed::auto-clear-enabled", self._on_settings_changed
        )
        Settings.get().connect(
            "changed::auto-clear-minutes", self._on_settings_changed
        )
        self._start_timer()

    def _on_settings_changed(self, settings, key):
        self._start_timer()

    def _start_timer(self):
        self._stop_timer()
        if not Settings.get().auto_clear_enabled:
            return
        self._timer_id = GLib.timeout_add_seconds(60, self._on_tick)

    def _stop_timer(self):
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def _on_tick(self):
        if not Settings.get().auto_clear_enabled:
            self._timer_id = None
            return False

        slots = Settings.get().slots.unpack()
        now = int(time.time())
        expiry_seconds = Settings.get().auto_clear_minutes_value * 60
        changed = False

        for i, slot in enumerate(slots):
            if len(slot) > 2 and slot[2] == "pinned":
                continue
            if not slot[0] and not slot[1]:
                continue
            if len(slot) > 3 and slot[3]:
                try:
                    timestamp = int(slot[3])
                    if now - timestamp > expiry_seconds:
                        slots[i] = ["", "", "", ""]
                        changed = True
                except ValueError:
                    pass

        if changed:
            Settings.get().slots = GLib.Variant("aas", slots)
            window = self._get_window()
            if window:
                window.update_slots(slots)
                window.refresh_grid()

        return True
