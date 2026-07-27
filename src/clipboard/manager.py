# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import time
import weakref

from serigy.clipboard.queue import ClipboardItem, ClipboardItemType
from serigy.image_store import store_image
from serigy.settings import Settings
from serigy.slot_data import SlotData


class ClipboardManager:
    def __init__(self, application):
        self.application = weakref.proxy(application)

    def _find_last_unpinned_slot(self, cb_list: list[SlotData]) -> int | None:
        """Find the index of the last unpinned slot."""
        for i in reversed(range(len(cb_list))):
            if not cb_list[i].is_pinned:
                return i
        return None

    def process_item(self, item: ClipboardItem) -> None:
        cb_list = Settings.get().slots

        if item.item_type == ClipboardItemType.TEXT:
            if item.data == cb_list[0].text:
                return
        elif item.uri:
            if item.uri == cb_list[0].uri:
                return
        elif item.filename and item.filename == cb_list[0].filename:
            return

        last_unpinned_idx = self._find_last_unpinned_slot(cb_list)
        if last_unpinned_idx is None:
            return

        cb_list.pop(last_unpinned_idx)

        if item.item_type == ClipboardItemType.TEXT:
            cb_list.insert(
                0,
                SlotData(
                    text=item.data,
                    timestamp=str(int(time.time())),
                    mime=item.mime,
                ),
            )
        else:
            if item.filename and item.data:
                if not store_image(item.data, item.filename):
                    return
            cb_list.insert(
                0,
                SlotData(
                    filename=item.filename or "",
                    uri=item.uri,
                    timestamp=str(int(time.time())),
                    mime=item.mime,
                ),
            )

        self._update_slots_no_callback(cb_list)

    def _update_slots_no_callback(self, cb_list: list[SlotData]) -> None:
        window = self.application.get_active_window()
        Settings.get().slots = cb_list

        if window:
            window.update_slots(cb_list)
            window.refresh_grid()
