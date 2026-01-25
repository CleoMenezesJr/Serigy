# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import threading
import time

from gi.repository import Adw

from serigy.shortcut_portal import GlobalShortcutsPortal

portal = GlobalShortcutsPortal()
portal.connect_sync()

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


def debounce(wait: float):
    def decorator(fn):
        last_call = [0]
        lock = threading.Lock()

        def debounced(*args, **kwargs):
            with lock:
                last_call[0] = time.time()

                def call_it():
                    time_since_last_call = time.time() - last_call[0]
                    if time_since_last_call >= wait:
                        fn(*args, **kwargs)

                threading.Timer(wait, call_it).start()

        return debounced

    return decorator


def setup(app: Adw.Application) -> bool:
    """Setup global shortcuts.

    Returns True on success, False if user cancelled.
    """
    try:
        portal.create_session()
    except RuntimeError:
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
