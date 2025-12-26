# Copyright 2024-2025 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

from gi.repository import GLib


class ClipboardItemType(Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"


@dataclass
class ClipboardItem:
    item_type: ClipboardItemType
    data: Any
    content_hash: str
    filename: Optional[str] = None


class ClipboardQueue:
    """Async queue for processing clipboard items sequentially."""

    def __init__(self, process_callback: Callable[[ClipboardItem], None]):
        self._queue: deque[ClipboardItem] = deque()
        self._process_callback = process_callback
        self._is_processing = False
        self._last_hash: Optional[str] = None

    def add(self, item: ClipboardItem) -> bool:
        if item.content_hash == self._last_hash:
            return False

        self._last_hash = item.content_hash
        self._queue.append(item)

        if not self._is_processing:
            self._schedule_next()

        return True

    def _schedule_next(self):
        if self._queue:
            self._is_processing = True
            GLib.idle_add(self._process_next)
        else:
            self._is_processing = False

    def _process_next(self) -> bool:
        if not self._queue:
            self._is_processing = False
            return False

        item = self._queue.popleft()

        try:
            self._process_callback(item)
        except Exception:
            pass

        if self._queue:
            GLib.idle_add(self._process_next)
        else:
            self._is_processing = False

        return False

    @property
    def pending_count(self) -> int:
        return len(self._queue)

    @property
    def is_processing(self) -> bool:
        return self._is_processing
