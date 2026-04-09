# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
import logging
import uuid
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
        self._last_is_local: bool | None = None
        self.sentinel = f"\u200b{uuid.uuid4()}\u200b"
        self.sentinel_written = False
        self._suppress_next = False

    def suppress_next_change(self):
        """Suppress the next clipboard change detection.

        Call this immediately before writing to the clipboard from within
        the app (e.g. slot copy), so the monitor does not re-capture
        content that the user explicitly chose to copy.
        """
        self._suppress_next = True
        logging.debug(
            "suppress_next_change: next clipboard change will be ignored"
        )

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
            logging.debug("Formats changed during processing, re-reading hash")
            self._read_text_hash_and_finish()
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
            logging.debug(
                "Could not capture initial clipboard hash (expected if empty): %s",
                e,
            )

        self._initial_state_ready = True
        logging.debug(
            "Clipboard monitor ready: is_local=%s, formats=%r",
            self.clipboard.is_local(),
            self.last_formats,
        )
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
        logging.debug(
            "_on_signal: changed signal received, can_proceed=%s", can_proceed
        )
        if can_proceed:
            self._check_for_changes()

    def _on_poll(self) -> bool:
        if not self.is_monitoring:
            logging.debug("_on_poll: stopping — is_monitoring=False")
            return False
        if not self._initial_state_ready:
            logging.debug("_on_poll: skip — initial state not ready")
            return True
        if self._is_processing:
            logging.debug("_on_poll: skip — is_processing=True")
            return True
        self._check_for_changes()
        return True

    def _check_for_changes(self):
        is_local = self.clipboard.is_local()
        if is_local != self._last_is_local:
            logging.debug(
                "_check_for_changes: is_local changed to %s", is_local
            )
            self._last_is_local = is_local
        if is_local:
            # Our process owns the clipboard (sentinel). Probe via portal to
            # detect if the content changed while we held ownership.
            self.clipboard.read_text_async(None, self._on_portal_probe_read)
            return

        current_formats = self.clipboard.get_formats().to_string()

        if current_formats != self.last_formats:
            logging.debug(
                "Clipboard formats changed: %s", current_formats[:50]
            )
            self.last_formats = current_formats
            logging.debug(
                "_check_for_changes: TRIGGER alert window (format change)"
            )
            self._schedule_callback()
            self._read_text_hash(is_initial=True)
            return

        if "text/plain" in current_formats:
            self._read_text_hash(is_initial=False)
        else:
            logging.debug(
                "_check_for_changes: formats unchanged (%r) — probing portal read",
                current_formats[:50],
            )
            # Empty clipboard + focus: write sentinel to detect when
            # another app copies (wl_data_source.cancelled).
            if current_formats == "":
                if not self.sentinel_written:
                    self._write_sentinel()
                else:
                    # Sentinel cancelled: another app copied. Trigger capture.
                    logging.debug(
                        "_check_for_changes: sentinel cancelled → TRIGGER"
                    )
                    self.sentinel_written = False
                    self._schedule_callback()
                return
            self.clipboard.read_text_async(None, self._on_portal_probe_read)

    def _on_portal_probe_read(self, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                if text == self.sentinel:
                    return
                text_hash = hashlib.sha256(text.encode()).hexdigest()
                if text_hash != self.last_text_hash:
                    logging.debug(
                        "_check_for_changes: TRIGGER via portal probe (hash changed, is_local=True)"
                    )
                    self.last_text_hash = text_hash
                    self._schedule_callback()
                else:
                    logging.debug(
                        "_check_for_changes: portal probe — same hash, no trigger"
                    )
            else:
                self._suppress_next = False
                logging.debug("_check_for_changes: portal probe — empty read")
        except Exception as e:
            self._suppress_next = False
            logging.debug("_check_for_changes: portal probe failed: %s", e)

    def _write_sentinel(self):
        """Write a sentinel to become wl_data_source owner.

        On Wayland, when another app copies, the compositor sends
        wl_data_source.cancelled to the current owner. GDK converts
        this to the 'changed' signal — without requiring window focus.
        Must be called while we have keyboard focus (compositor enforces this).
        """
        if self.sentinel_written:
            return
        try:
            provider = Gdk.ContentProvider.new_for_bytes(
                "text/plain;charset=utf-8",
                GLib.Bytes.new(self.sentinel.encode("utf-8")),
            )
            success = self.clipboard.set_content(provider)
            if success:
                self.sentinel_written = True
                logging.debug(
                    "Sentinel written to clipboard for Wayland passive detection"
                )
            else:
                logging.debug(
                    "Failed to write sentinel: set_content returned False"
                )
        except Exception as e:
            logging.debug("Failed to write sentinel: %s", e)

    def _read_text_hash(self, is_initial: bool):
        self.clipboard.read_text_async(None, self._on_text_read, is_initial)

    def _on_text_read(self, clipboard, result, is_initial):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                if text == self.sentinel:
                    logging.debug("_on_text_read: ignoring sentinel text")
                    return
                text_hash = hashlib.sha256(text.encode()).hexdigest()
                if is_initial:
                    self.last_text_hash = text_hash
                elif text_hash != self.last_text_hash:
                    logging.debug(
                        "_check_for_changes: TRIGGER alert window (text hash mismatch)"
                    )
                    self.last_text_hash = text_hash
                    self._schedule_callback()

            else:
                logging.debug(
                    "_check_for_changes: NO TRIGGER — text read returned empty"
                )
        except Exception as e:
            logging.debug(
                "Could not read clipboard text (expected if no text format available): %s",
                e,
            )

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
            logging.debug(
                "Could not read final clipboard text (expected if no text format available): %s",
                e,
            )
            self.last_text_hash = None

        self._is_processing = False
        self._check_for_changes()

    def _schedule_callback(self):
        if self._suppress_next:
            self._suppress_next = False
            logging.debug("_schedule_callback: suppressed (internal write)")
            return
        if not self._is_processing:
            self._is_processing = True
            GLib.idle_add(self._fire_callback)

    def _fire_callback(self):
        self.callback()
        return False
