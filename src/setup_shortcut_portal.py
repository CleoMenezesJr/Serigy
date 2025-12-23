# Copyright 2025 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import threading
import time

from gi.repository import Adw

from .shortcut_portal import GlobalShortcutsPortal

portal = GlobalShortcutsPortal()
portal.connect_sync()

# Define shortcuts
shortcuts = [
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


def setup(app: Adw.Application) -> str:
    session = portal.create_session()

    # Define callbacks
    @debounce(0.5)
    def _on_shortcut_activated(
        shortcut_id: str, timestamp: int, options: dict
    ) -> None:
        print(f"Shortcut activated: {shortcut_id} (timestamp: {timestamp})")

        if shortcut_id == "open_serigy":
            app.do_activate()

        if "activation_token" in options:
            print(f"Activation token: {options['activation_token']}")

    def _on_shortcut_deactivated(
        shortcut_id: str, timestamp: int, options: dict
    ) -> None:
        print(f"Shortcut deactivated: {shortcut_id} (timestamp: {timestamp})")

    portal.on_activated(_on_shortcut_activated)
    portal.on_deactivated(_on_shortcut_deactivated)

    bound_shortcuts = portal.bind_shortcuts(shortcuts)
    print(f"Bound shortcuts: {len(bound_shortcuts)}")

    for shortcut_id, info in bound_shortcuts:
        desc = info.get("description", "N/A")
        trigger = info.get("trigger_description", "N/A")
        print(f"  - {shortcut_id}: {desc} [{trigger}]")

    return session
