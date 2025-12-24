# Copyright 2024 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
from typing import Callable, Optional

import gi

gi.require_version("Gdk", "4.0")
if gi:
    from gi.repository import Gdk, GLib


class ClipboardMonitor:
    def __init__(self, callback: Callable[[], None]):
        self.callback = callback
        self.clipboard = Gdk.Display.get_default().get_clipboard()
        self.last_formats = ""
        self.last_text_hash: Optional[str] = None
        self.is_monitoring = False
        self._signal_handler_id = None
        self._poll_timer_id = None
        self._initial_state_ready = False
        self._is_processing = False

    def done_processing(self):
        # Update formats first
        self.last_formats = self.clipboard.get_formats().to_string()
        # Read text hash - this will call _finish_processing when done
        self._read_text_hash_and_finish()

    def _read_text_hash_and_finish(self):
        self.clipboard.read_text_async(None, self._on_done_hash_ready)

    def _on_done_hash_ready(self, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                self.last_text_hash = hashlib.sha256(text.encode()).hexdigest()
        except Exception:
            pass

        self._is_processing = False
        # Check if anything changed while we were processing
        self._check_for_changes()

    def start(self):
        if self.is_monitoring:
            return
        self.is_monitoring = True
        self._initial_state_ready = False

        self.last_formats = self.clipboard.get_formats().to_string()
        self._capture_initial_hash()

    def _capture_initial_hash(self):
        self.clipboard.read_text_async(None, self._on_initial_hash_ready)

    def _on_initial_hash_ready(self, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                self.last_text_hash = hashlib.sha256(text.encode()).hexdigest()
        except Exception:
            pass

        self._initial_state_ready = True
        self._signal_handler_id = self.clipboard.connect(
            "changed", self._on_signal
        )
        self._poll_timer_id = GLib.timeout_add(1000, self._on_poll)

    def stop(self):
        self.is_monitoring = False
        if self._signal_handler_id:
            self.clipboard.disconnect(self._signal_handler_id)
            self._signal_handler_id = None
        if self._poll_timer_id:
            GLib.source_remove(self._poll_timer_id)
            self._poll_timer_id = None

    def _on_signal(self, clipboard):
        if (
            self.is_monitoring
            and self._initial_state_ready
            and not self._is_processing
        ):
            self._check_for_changes()

    def _on_poll(self) -> bool:
        if (
            not self.is_monitoring
            or not self._initial_state_ready
            or self._is_processing
        ):
            return self.is_monitoring
        self._check_for_changes()
        return True

    def _check_for_changes(self):
        if self.clipboard.is_local():
            return

        current_formats = self.clipboard.get_formats().to_string()
        if current_formats != self.last_formats:
            self.last_formats = current_formats
            self._schedule_callback()
            self._read_text_hash(is_initial=True)
            return

        # Only check text hash if clipboard contains text
        if "text/plain" in current_formats:
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
        if not self._is_processing:
            self._is_processing = True
            GLib.idle_add(self._fire_callback)

    def _fire_callback(self):
        self.callback()
        return False
