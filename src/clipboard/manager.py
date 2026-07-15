# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os
import time
import weakref

import gi

from serigy.clipboard.queue import ClipboardItem, ClipboardItemType
from serigy.settings import Settings
from serigy.slot_data import SlotData

gi.require_versions({"Gdk": "4.0"})

if gi:
    from gi.repository import GLib


class ClipboardManager:
    def __init__(self, application):
        self.application = weakref.proxy(application)

    def _find_last_unpinned_slot(self, cb_list: list[SlotData]) -> int | None:
        """Find the index of the last unpinned slot."""
        for i in reversed(range(len(cb_list))):
            if not cb_list[i].is_pinned:
                return i
        return None

    def _remove_old_file_if_exists(
        self, cb_list: list[SlotData], idx: int
    ) -> None:
        if cb_list[idx].filename:
            old_file_path = os.path.join(
                GLib.get_user_cache_dir(), "tmp", cb_list[idx].filename
            )
            if os.path.exists(old_file_path):
                os.remove(old_file_path)

    def process_item(self, item: ClipboardItem) -> None:
        cb_list = Settings.get().slots

        if item.item_type == ClipboardItemType.TEXT:
            if item.data == cb_list[0].text:
                return
        else:
            if item.filename and item.filename == cb_list[0].filename:
                return

        last_unpinned_idx = self._find_last_unpinned_slot(cb_list)
        if last_unpinned_idx is None:
            return

        self._remove_old_file_if_exists(cb_list, last_unpinned_idx)
        cb_list.pop(last_unpinned_idx)

        if item.item_type == ClipboardItemType.TEXT:
            cb_list.insert(
                0, SlotData(text=item.data, timestamp=str(int(time.time())))
            )
        else:
            if item.filename:
                cache_dir = os.path.join(GLib.get_user_cache_dir(), "tmp")
                os.makedirs(cache_dir, exist_ok=True)
                file_path = os.path.join(cache_dir, item.filename)
                if not os.path.exists(file_path) and item.data:
                    try:
                        ext = (
                            item.filename.rsplit(".", 1)[-1]
                            if "." in item.filename
                            else "png"
                        )
                        item.data.savev(file_path, ext, [], [])
                    except Exception as e:
                        logging.error(
                            "Failed to save clipboard image to cache: %s", e
                        )
                        return
            cb_list.insert(
                0,
                SlotData(
                    filename=item.filename, timestamp=str(int(time.time()))
                ),
            )

        self._update_slots_no_callback(cb_list)

    def _update_slots_no_callback(self, cb_list: list[SlotData]) -> None:
        window = self.application.get_active_window()
        Settings.get().slots = cb_list

        if window:
            window.update_slots(cb_list)
            window.refresh_grid()
