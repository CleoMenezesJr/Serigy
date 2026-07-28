# Copyright 2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

"""Put a stored slot back on the clipboard.

The compositor grants the selection to a focused window only, so this is
`CopyAlertWindow` in reverse: a window nobody sees takes focus just long
enough for the write to be accepted. Text never comes through here — the
shell writes that one itself.
"""

import logging

import gi

gi.require_versions({"Gtk": "4.0", "Adw": "1", "Gdk": "4.0"})

from gi.repository import Adw, Gdk, GLib, Gtk

from serigy.clipboard.content import provider_for

# The compositor is under no obligation to hand focus over, and the reason
# it withholds it — the user still typing somewhere else — passes. So ask
# again on a beat, and only call it a failure once every attempt is spent.
# Three attempts, three seconds apart, is the ten seconds the capture window
# already waits before it gives up.
RETRY_INTERVAL_MS = 3000
MAX_ATTEMPTS = 3

# Long enough for GDK to hand the selection request to the compositor
# before the window that justified it goes away.
SETTLE_MS = 100


class ClipboardWriter(Adw.Window):
    __gtype_name__ = "ClipboardWriter"

    def __init__(
        self, slot, monitor, on_finished=None, on_failed=None, **kwargs
    ):
        super().__init__(**kwargs)

        self._slot = slot
        self._monitor = monitor
        self._on_finished = on_finished
        self._on_failed = on_failed
        self._written = False
        self._closed = False
        self._attempts = 1

        # Same shape as the capture window, which is known to earn focus;
        # invisible because there is nothing here to read.
        self.set_content(Gtk.Box())
        self.set_size_request(283, 60)
        self.set_resizable(False)
        self.set_modal(True)
        self.set_opacity(0.01)

        self.connect("show", lambda *_: self.present())
        self.connect("notify::is-active", self._on_focus_changed)

        self._retry_timeout = GLib.timeout_add(
            RETRY_INTERVAL_MS, self._retry_focus
        )
        logging.debug("ClipboardWriter created, attempt 1 at focus")

    def _retry_focus(self):
        """Ask for focus again, and own the deadline while doing it."""
        if self._written or self._closed:
            self._retry_timeout = None
            return False

        if self._attempts >= MAX_ATTEMPTS:
            self._retry_timeout = None
            logging.debug(
                "ClipboardWriter: no focus after %d attempts, giving up",
                self._attempts,
            )
            self._close(failed=True)
            return False

        self._attempts += 1
        logging.debug("ClipboardWriter: attempt %d at focus", self._attempts)
        self.present()
        return True

    def _on_focus_changed(self, window, pspec):
        if not self.is_active() or self._written:
            return
        self._written = True

        provider = provider_for(self._slot)
        if provider is None:
            logging.warning("Nothing left to write for this slot")
            self._close(failed=True)
            return

        # Our own write, so the monitor must not take it back in as a copy.
        self._monitor.suppress_next_change()
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set_content(provider)
        logging.debug("ClipboardWriter: content written")

        GLib.timeout_add(SETTLE_MS, self._close)

    def _close(self, failed: bool = False):
        if self._closed:
            return False
        self._closed = True

        if self._retry_timeout:
            GLib.source_remove(self._retry_timeout)
            self._retry_timeout = None

        if failed and self._on_failed:
            self._on_failed()
        if self._on_finished:
            self._on_finished()

        self.destroy()
        return False
