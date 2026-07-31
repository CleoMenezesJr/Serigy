# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from gi.repository import Adw, GLib

from serigy.shortcut_portal import GlobalShortcutsPortal

# Portal instance will be initialized in setup()
portal = None

shortcuts = [
    (
        "pin_clipboard",
        {
            "description": "Save Clipboard",
            "preferred_trigger": "<Control><Super>c",
        },
    ),
    (
        "open_serigy",
        {
            "description": "Open Serigy",
            "preferred_trigger": "<Control><Super>v",
        },
    ),
]


def debounce(wait_secs: float):
    """Decorator to rate-limit function calls using GLib.timeout_add.

    Delays execution until the wait time has passed without new calls.
    Prevents invalid Source ID errors by managing cleanup safely.

    Args:
        wait_secs: Delay in seconds (e.g. 0.5 for 500ms).
    """

    def decorator(fn):
        def debounced(*args, **kwargs):
            # Store source_id on the function object itself to persist state
            if hasattr(debounced, "_source_id") and debounced._source_id:
                GLib.source_remove(debounced._source_id)
                debounced._source_id = None

            def call_it():
                fn(*args, **kwargs)
                debounced._source_id = None
                return False  # Stop the timer (GLib.SOURCE_REMOVE)

            delay_ms = int(wait_secs * 1000)
            debounced._source_id = GLib.timeout_add(delay_ms, call_it)

        return debounced

    return decorator


def setup(app: Adw.Application) -> bool:
    """Setup global shortcuts.

    Returns True on success, False if user cancelled.
    """
    global portal

    @debounce(0.5)
    def _on_shortcut_activated(
        shortcut_id: str, timestamp: int, options: dict
    ) -> None:
        if shortcut_id == "pin_clipboard":
            app.on_shortcut_copy()
        elif shortcut_id == "open_serigy":
            app.do_activate()

    def _on_shortcut_deactivated(
        shortcut_id: str, timestamp: int, options: dict
    ) -> None:
        pass

    try:
        if portal is None:
            portal = GlobalShortcutsPortal()
            portal.connect_sync()
            # The callbacks belong to the portal, not to the attempt. Setup
            # is retried whenever binding is refused, and registering there
            # would leave one extra handler per attempt, so a single press
            # would reach the app as many times as it took to get here.
            portal.on_activated(_on_shortcut_activated)
            portal.on_deactivated(_on_shortcut_deactivated)
            portal.on_session_lost(app.on_shortcuts_lost)
        # Getting here a second time means the last bind was refused, and
        # the portal only lets an application attempt to bind a session
        # once, so what we are holding can never be used again.
        portal.close_session()
        portal.create_session()
    except RuntimeError as e:
        logging.error("Failed to create shortcut session: %s", e)
        return False

    try:
        portal.bind_shortcuts(shortcuts)
    except RuntimeError:
        return False

    return True
