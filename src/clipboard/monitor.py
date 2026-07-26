# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
import logging
import uuid
from collections.abc import Callable

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib

from serigy.clipboard.detector import (
    IMAGE_PROBE_TICKS,
    Action,
    ClipboardState,
    decide,
    probe_failure_is_conclusive,
)


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
        self._probe_failures = 0
        self._image_tick = 0
        self._texture_fingerprint: str | None = None
        self._stale_trigger_fired = False

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
        self._reset_probe_state()
        self._stale_trigger_fired = False
        self._suppress_next = False
        self.sentinel_written = False
        logging.debug("Clipboard monitoring started")
        self.last_formats = self.clipboard.get_formats().to_string()
        self._capture_initial_hash()

    def stop(self):
        self.is_monitoring = False
        self._reset_probe_state()
        self._suppress_next = False
        logging.debug("Clipboard monitoring stopped")
        if self._signal_handler_id:
            self.clipboard.disconnect(self._signal_handler_id)
            self._signal_handler_id = None
        if self._poll_timer_id:
            GLib.source_remove(self._poll_timer_id)
            self._poll_timer_id = None

    def done_processing(self):
        self.last_formats = self.clipboard.get_formats().to_string()
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
                "Could not capture initial clipboard hash "
                "(expected if empty): %s",
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
        self._reset_probe_state()
        self._stale_trigger_fired = False
        if can_proceed:
            self._check_for_changes()

    def _on_poll(self) -> bool:
        if not self.is_monitoring:
            logging.debug("_on_poll: stopping, is_monitoring=False")
            return False
        if not self._initial_state_ready:
            logging.debug("_on_poll: skip, initial state not ready")
            return True
        if self._is_processing:
            logging.debug("_on_poll: skip, is_processing=True")
            return True
        self._check_for_changes()
        return True

    def _reset_probe_state(self):
        self._probe_failures = 0
        self._image_tick = 0
        self._texture_fingerprint = None

    def _observe(self) -> ClipboardState:
        is_local = self.clipboard.is_local()
        if is_local != self._last_is_local:
            logging.debug(
                "_check_for_changes: is_local changed to %s", is_local
            )
            self._last_is_local = is_local

        return ClipboardState(
            is_local=is_local,
            formats=self.clipboard.get_formats().to_string(),
            last_formats=self.last_formats,
            sentinel_written=self.sentinel_written,
            image_tick=self._image_tick,
        )

    def _check_for_changes(self):
        state = self._observe()
        action = decide(state)

        if action is Action.TRIGGER_CAPTURE:
            if state.formats != state.last_formats:
                logging.debug(
                    "Clipboard formats changed: %s", state.formats[:50]
                )
                self.last_formats = state.formats
                self._reset_probe_state()
                self._stale_trigger_fired = False
                logging.debug(
                    "_check_for_changes: TRIGGER alert window (format change)"
                )
                self._schedule_callback()
                self._read_text_hash(is_initial=True)
                return

            # Sentinel cancelled: another client took the selection.
            logging.debug(
                "_check_for_changes: sentinel cancelled, "
                "TRIGGER (someone copied)"
            )
            self.sentinel_written = False
            self.last_formats = state.formats
            self._reset_probe_state()
            self._stale_trigger_fired = False
            self._schedule_callback()
            return

        if action is Action.WRITE_SENTINEL:
            self._write_sentinel()
            return

        if action is Action.PROBE_LOCAL:
            self.clipboard.read_text_async(None, self._on_portal_probe_read)
            return

        if action is Action.PROBE_TEXT:
            self._read_text_hash(is_initial=False)
            return

        if action is Action.PROBE_TEXTURE:
            self._image_tick = 0
            self.clipboard.read_texture_async(None, self._on_texture_probe)
            return

        self._image_tick = (self._image_tick + 1) % IMAGE_PROBE_TICKS

    def _on_texture_probe(self, clipboard, result):
        try:
            texture = clipboard.read_texture_finish(result)
        except Exception as e:
            self._on_probe_failed(f"texture read failed: {e}")
            return

        if texture is None:
            self._on_probe_failed("texture read returned nothing")
            return

        self._probe_failures = 0
        self._stale_trigger_fired = False
        # Dimensions instead of a hash: hashing means re-encoding the image
        # every tick. A same-size replacement is missed here and caught by
        # the format change or the `changed` signal.
        fingerprint = f"{texture.get_width()}x{texture.get_height()}"
        if self._texture_fingerprint is None:
            self._texture_fingerprint = fingerprint
        elif fingerprint != self._texture_fingerprint:
            self._texture_fingerprint = fingerprint
            self._reset_probe_state()
            logging.debug(
                "_check_for_changes: TRIGGER alert window (texture changed)"
            )
            self._schedule_callback()

    def _on_probe_failed(self, why: str):
        self._probe_failures += 1
        conclusive = probe_failure_is_conclusive(
            self._probe_failures, self._stale_trigger_fired
        )
        if not self._stale_trigger_fired:
            logging.debug(
                "_check_for_changes: probe failed (%s), streak=%d",
                why,
                self._probe_failures,
            )
        if not conclusive:
            return

        self._stale_trigger_fired = True
        self._reset_probe_state()
        logging.debug(
            "_check_for_changes: TRIGGER alert window (formats went stale)"
        )
        self._schedule_callback()

    def _on_portal_probe_read(self, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                if text == self.sentinel:
                    self._suppress_next = False
                    return
                text_hash = hashlib.sha256(text.encode()).hexdigest()
                if text_hash != self.last_text_hash:
                    logging.debug(
                        "_check_for_changes: TRIGGER via portal probe "
                        "(hash changed, is_local=True)"
                    )
                    self.last_text_hash = text_hash
                    self._schedule_callback()
                else:
                    self._suppress_next = False
                    logging.debug(
                        "_check_for_changes: portal probe, same hash, "
                        "no trigger"
                    )
            else:
                self._suppress_next = False
                logging.debug("_check_for_changes: portal probe, empty read")
        except Exception as e:
            self._suppress_next = False
            logging.debug("_check_for_changes: portal probe failed: %s", e)

    def _write_sentinel(self):
        """Write a sentinel to become wl_data_source owner.

        On Wayland, when another app copies, the compositor sends
        wl_data_source.cancelled to the current owner. GDK converts
        this to the 'changed' signal, without requiring window focus.
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
                    "Sentinel written to clipboard for Wayland "
                    "passive detection"
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
                self._probe_failures = 0
                self._stale_trigger_fired = False
                if text == self.sentinel:
                    logging.debug("_on_text_read: ignoring sentinel text")
                    return
                text_hash = hashlib.sha256(text.encode()).hexdigest()
                if is_initial:
                    self.last_text_hash = text_hash
                elif text_hash != self.last_text_hash:
                    logging.debug(
                        "_check_for_changes: TRIGGER alert window "
                        "(text hash mismatch)"
                    )
                    self.last_text_hash = text_hash
                    self._schedule_callback()

            elif not is_initial:
                self._on_probe_failed("text read returned empty")
        except Exception as e:
            if is_initial:
                logging.debug("Could not read initial clipboard text: %s", e)
            else:
                self._on_probe_failed(f"text read failed: {e}")

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
                "Could not read final clipboard text "
                "(expected if no text format available): %s",
                e,
            )
            self.last_text_hash = None

        # The capture window just read the clipboard for real.
        self._reset_probe_state()
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
