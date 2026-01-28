# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from gi.repository import Adw, GLib

from serigy.shortcut_portal import GlobalShortcutsPortal

# Portal instance will be initialized in setup()
portal = None

# Define shortcuts
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


def debounce(wait: int):  # wait in milliseconds
    """Decorator to rate-limit function calls using GLib.timeout_add.

    Delays execution until the wait time has passed without new calls.
    Prevents invalid Source ID errors by managing cleanup safely.
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

            # Convert seconds to milliseconds if float provided, or expect ms
            delay_ms = int(wait * 1000) if isinstance(wait, float) else wait
            debounced._source_id = GLib.timeout_add(delay_ms, call_it)

        return debounced

    return decorator


def setup(app: Adw.Application) -> bool:
    """Setup global shortcuts.

    Returns True on success, False if user cancelled.
    """
    global portal
    try:
        if portal is None:
            portal = GlobalShortcutsPortal()
            portal.connect_sync()
        portal.create_session()
    except RuntimeError as e:
        logging.error("Failed to create shortcut session: %s", e)
        return False

    # Define callbacks
    @debounce(0.5)
    def _on_shortcut_activated(
        shortcut_id: str, timestamp: int, options: dict
    ) -> None:
        if shortcut_id == "pin_clipboard":
            # Trigger visible copy alert window
            app.on_shortcut_copy()
        elif shortcut_id == "open_serigy":
            # Open main window
            app.do_activate()

    def _on_shortcut_deactivated(
        shortcut_id: str, timestamp: int, options: dict
    ) -> None:
        pass

    portal.on_activated(_on_shortcut_activated)
    portal.on_deactivated(_on_shortcut_deactivated)

    try:
        portal.bind_shortcuts(shortcuts)
    except RuntimeError:
        return False

    return True
