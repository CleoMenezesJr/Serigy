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

    def _find_matching_slot(
        self, cb_list: list[SlotData], item: ClipboardItem
    ) -> int | None:
        """Find the slot already holding this content, anywhere in the list.

        Only slot 0 used to be checked, so copying A, then B, then A again
        stored A a second time and the list filled up with the same content.
        """
        if item.item_type == ClipboardItemType.TEXT:
            key, field = item.data, "text"
        elif item.uri:
            key, field = item.uri, "uri"
        else:
            key, field = item.filename, "filename"

        if not key:
            return None

        return next(
            (i for i, s in enumerate(cb_list) if getattr(s, field) == key),
            None,
        )

    def process_item(self, item: ClipboardItem) -> None:
        cb_list = Settings.get().slots

        match_idx = self._find_matching_slot(cb_list, item)
        if match_idx is not None:
            self._promote_slot(cb_list, match_idx)
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

    def _promote_slot(self, cb_list: list[SlotData], index: int) -> None:
        """Move a slot we already hold back to the front.

        The copy is real, so the slot travels to the top and takes a fresh
        timestamp, which also keeps the auto cleaner from expiring something
        the user just copied. What it does not do is become a second slot.
        """
        slot = cb_list.pop(index)
        slot.timestamp = str(int(time.time()))
        cb_list.insert(0, slot)
        self._update_slots_no_callback(cb_list)

    def _update_slots_no_callback(self, cb_list: list[SlotData]) -> None:
        window = self.application.get_active_window()
        Settings.get().slots = cb_list

        if window:
            # Only the grid is left to do. Asking the window to update the
            # slots as well wrote the same list to GSettings a second time
            # and swept the image directory twice for every copy, and the
            # rebuild below reads the slots back and settles the toolbar
            # on its own.
            window.refresh_grid()
