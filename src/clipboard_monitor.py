# Copyright 2024 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
from typing import Callable, Optional

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib


class ClipboardMonitor:
    """
    Monitors clipboard changes using signal + polling hybrid approach.
    Detects changes via format comparison and text content hashing.
    """

    def __init__(self, callback: Callable[[], None]):
        self.callback = callback
        self.clipboard = Gdk.Display.get_default().get_clipboard()
        self.last_formats = ""
        self.last_text_hash: Optional[str] = None
        self.is_monitoring = False
        self._first_run = True
        self._skip_next = False
        self._debounce_timer_id = None
        self._signal_handler_id = None
        self._poll_timer_id = None

    def skip_next_change(self):
        self._skip_next = True

    def done_processing(self):
        self.last_formats = self.clipboard.get_formats().to_string()
        self._read_text_hash(is_initial=True)

    def start(self):
        if self.is_monitoring:
            return
        self.is_monitoring = True

        self.last_formats = self.clipboard.get_formats().to_string()
        self._read_text_hash(is_initial=True)

        self._signal_handler_id = self.clipboard.connect("changed", self._on_signal)
        self._poll_timer_id = GLib.timeout_add(1000, self._on_poll)

    def stop(self):
        self.is_monitoring = False
        if self._signal_handler_id:
            self.clipboard.disconnect(self._signal_handler_id)
            self._signal_handler_id = None
        if self._poll_timer_id:
            GLib.source_remove(self._poll_timer_id)
            self._poll_timer_id = None
        if self._debounce_timer_id:
            GLib.source_remove(self._debounce_timer_id)
            self._debounce_timer_id = None

    def _on_signal(self, clipboard):
        if self.is_monitoring:
            self._check_for_changes()

    def _on_poll(self) -> bool:
        if not self.is_monitoring:
            return False
        self._check_for_changes()
        return True

    def _check_for_changes(self):
        if self._first_run:
            self._first_run = False
            return

        if self._skip_next:
            self._skip_next = False
            self.last_formats = self.clipboard.get_formats().to_string()
            self._read_text_hash(is_initial=True)
            return

        if self.clipboard.is_local():
            return

        current_formats = self.clipboard.get_formats().to_string()
        if current_formats != self.last_formats:
            self.last_formats = current_formats
            self._schedule_callback()
            return

        self._read_text_hash(is_initial=False)

    def _read_text_hash(self, is_initial: bool):
        self.clipboard.read_text_async(None, self._on_text_read, is_initial)

    def _on_text_read(self, clipboard, result, is_initial):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                text_hash = hashlib.sha256(text.encode()).hexdigest()
                if is_initial:
                    self.last_text_hash = text_hash
                elif text_hash != self.last_text_hash:
                    self.last_text_hash = text_hash
                    self._schedule_callback()
        except Exception:
            pass

    def _schedule_callback(self):
        if self._debounce_timer_id is not None:
            GLib.source_remove(self._debounce_timer_id)
        self._debounce_timer_id = GLib.timeout_add(300, self._on_debounce)

    def _on_debounce(self):
        self._debounce_timer_id = None
        self.callback()
        return False
