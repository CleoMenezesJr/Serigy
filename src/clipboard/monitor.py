# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
import logging
from collections.abc import Callable

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib


class ClipboardMonitor:
    """Monitors clipboard for text changes."""

    def __init__(self, callback: Callable[[], None]):
        self.callback = callback
        self.clipboard = Gdk.Display.get_default().get_clipboard()
        self.last_formats = ""
        self.last_text_hash: str | None = None
        self.is_monitoring = False
        self._signal_handler_id = None
        self._poll_timer_id = None
        self._initial_state_ready = False
        self._is_processing = False

    def start(self):
        if self.is_monitoring:
            return
        self.is_monitoring = True
        self._initial_state_ready = False
        logging.debug("Clipboard monitoring started")
        self.last_formats = self.clipboard.get_formats().to_string()
        self._capture_initial_hash()

    def stop(self):
        self.is_monitoring = False
        logging.debug("Clipboard monitoring stopped")
        if self._signal_handler_id:
            self.clipboard.disconnect(self._signal_handler_id)
            self._signal_handler_id = None
        if self._poll_timer_id:
            GLib.source_remove(self._poll_timer_id)
            self._poll_timer_id = None

    def done_processing(self):
        current_formats = self.clipboard.get_formats().to_string()
        formats_changed = current_formats != self.last_formats
        self.last_formats = current_formats

        if formats_changed:
            logging.debug("Formats changed during processing, resetting hash")
            self.last_text_hash = None
            self._is_processing = False
            self._check_for_changes()
            return

        self._read_text_hash_and_finish()

    def _capture_initial_hash(self):
        self.clipboard.read_text_async(None, self._on_initial_hash_ready)

    def _on_initial_hash_ready(self, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                self.last_text_hash = hashlib.sha256(text.encode()).hexdigest()
        except Exception as e:
            logging.debug("Could not capture initial clipboard hash (expected if empty): %s", e)

        self._initial_state_ready = True
        self._signal_handler_id = self.clipboard.connect(
            "changed", self._on_signal
        )
        self._poll_timer_id = GLib.timeout_add(1000, self._on_poll)

    def _on_signal(self, clipboard):
        can_proceed = (
            self.is_monitoring
            and self._initial_state_ready
            and not self._is_processing
        )
        if can_proceed:
            self._check_for_changes()

    def _on_poll(self) -> bool:
        skip_poll = (
            not self.is_monitoring
            or not self._initial_state_ready
            or self._is_processing
        )
        if skip_poll:
            return self.is_monitoring
        self._check_for_changes()
        return True

    def _check_for_changes(self):
        if self.clipboard.is_local():
            return

        current_formats = self.clipboard.get_formats().to_string()

        if current_formats != self.last_formats:
            logging.debug(
                "Clipboard formats changed: %s", current_formats[:50]
            )
            self.last_formats = current_formats
            self._schedule_callback()
            self._read_text_hash(is_initial=True)
            return

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
                    logging.debug("Text content changed (hash mismatch)")
                    self.last_text_hash = text_hash
                    self._schedule_callback()
        except Exception as e:
            logging.debug("Could not read clipboard text (expected if no text format available): %s", e)

    def _read_text_hash_and_finish(self):
        self.clipboard.read_text_async(None, self._on_done_hash_ready)

    def _on_done_hash_ready(self, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                self.last_text_hash = hashlib.sha256(text.encode()).hexdigest()
            else:
                self.last_text_hash = None
        except Exception as e:
            logging.debug("Could not read final clipboard text (expected if no text format available): %s", e)
            self.last_text_hash = None

        self._is_processing = False
        self._check_for_changes()

    def _schedule_callback(self):
        if not self._is_processing:
            self._is_processing = True
            GLib.idle_add(self._fire_callback)

    def _fire_callback(self):
        self.callback()
        return False
