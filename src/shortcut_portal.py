# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

# Reference:
# https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html

import logging
import secrets
import string
from collections.abc import Callable
from typing import Any

from gi.repository import Gio, GLib


class GlobalShortcutsPortal:
    PORTAL_NAME = "org.freedesktop.portal.Desktop"
    PORTAL_PATH = "/org/freedesktop/portal/desktop"
    INTERFACE = "org.freedesktop.portal.GlobalShortcuts"
    SESSION_INTERFACE = "org.freedesktop.portal.Session"

    def __init__(self):
        self.connection = None
        self.proxy = None
        self.session_handle = None
        self._activated_callbacks = []
        self._deactivated_callbacks = []

    def connect_sync(self):
        self.connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.proxy = Gio.DBusProxy.new_sync(
            self.connection,
            Gio.DBusProxyFlags.NONE,
            None,
            self.PORTAL_NAME,
            self.PORTAL_PATH,
            self.INTERFACE,
            None,
        )

        self.connection.signal_subscribe(
            self.PORTAL_NAME,
            self.INTERFACE,
            "Activated",
            self.PORTAL_PATH,
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_activated,
            None,
        )

        self.connection.signal_subscribe(
            self.PORTAL_NAME,
            self.INTERFACE,
            "Deactivated",
            self.PORTAL_PATH,
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_deactivated,
            None,
        )

    @staticmethod
    def _generate_token():
        return "".join(
            secrets.SystemRandom().choices(
                string.ascii_letters + string.digits + "_", k=16
            )
        )

    def create_session(self):
        options = {
            "session_handle_token": GLib.Variant("s", self._generate_token())
        }

        result = self.proxy.call_sync(
            "CreateSession",
            GLib.Variant("(a{sv})", (options,)),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

        request_path = result[0]

        self.session_handle = self._wait_for_request(request_path)
        return self.session_handle

    def close_session(self) -> None:
        """Hand back the session we are holding, if we hold one.

        Shortcuts can only be bound to a session once, so a session whose
        bind was refused is spent and the next attempt needs a fresh one.
        The portal keeps the spent one alive for as long as we stay on the
        bus, which for a service that runs for weeks means one dead session
        per refusal.
        """
        if not self.session_handle:
            return

        try:
            self.connection.call_sync(
                self.PORTAL_NAME,
                self.session_handle,
                self.SESSION_INTERFACE,
                "Close",
                None,
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
        except GLib.Error as e:
            # A session the portal has already dropped is the outcome we
            # were asking for, so there is nothing here worth failing over.
            logging.debug(
                "Could not close the shortcut session: %s", e.message
            )
        finally:
            self.session_handle = None

    def bind_shortcuts(
        self,
        shortcuts: list[tuple[int, dict[str, str | None]]],
        parent_window: str | None = "",
    ) -> list[str]:
        if not self.session_handle:
            raise RuntimeError(
                "Session not created. Please run create_session() first."
            )

        # Converts shortcuts to DBus format
        shortcuts_variant = []
        for shortcut_id, info in shortcuts:
            props = {}
            if "description" in info:
                props["description"] = GLib.Variant("s", info["description"])
            if "preferred_trigger" in info:
                props["preferred_trigger"] = GLib.Variant(
                    "s", info["preferred_trigger"]
                )

            shortcuts_variant.append((shortcut_id, props))

        options = {"handle_token": GLib.Variant("s", self._generate_token())}

        result = self.proxy.call_sync(
            "BindShortcuts",
            GLib.Variant(
                "(oa(sa{sv})sa{sv})",
                (
                    self.session_handle,
                    shortcuts_variant,
                    parent_window,
                    options,
                ),
            ),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

        request_path = result[0]
        return self._wait_for_request(request_path)

    def list_shortcuts(self):
        if not self.session_handle:
            raise RuntimeError("Session not created.")

        options = {"handle_token": GLib.Variant("s", self._generate_token())}

        result = self.proxy.call_sync(
            "ListShortcuts",
            GLib.Variant("(oa{sv})", (self.session_handle, options)),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

        request_path = result[0]
        return self._wait_for_request(request_path)

    # NOTE: Next versions of the portal will be possible to configure shortcuts
    def configure_shortcuts(
        self,
        parent_window: str = "",
        activation_token: GLib.Variant | None = None,
    ) -> None:
        if not self.session_handle:
            raise RuntimeError("Session not created.")

        options = {}
        if activation_token:
            options["activation_token"] = GLib.Variant("s", activation_token)

        self.proxy.call_sync(
            "ConfigureShortcuts",
            GLib.Variant(
                "(osa{sv})", (self.session_handle, parent_window, options)
            ),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

    def _wait_for_request(self, request_path: str) -> dict[str, Any]:
        loop = GLib.MainLoop()
        response_data = {}

        def on_response(
            connection, sender, path, interface, signal, params, user_data
        ):
            status, results = params
            response_data["status"] = status
            response_data["results"] = results
            loop.quit()

        self.connection.signal_subscribe(
            self.PORTAL_NAME,
            "org.freedesktop.portal.Request",
            "Response",
            request_path,
            None,
            Gio.DBusSignalFlags.NONE,
            on_response,
            None,
        )

        loop.run()

        if response_data["status"] != 0:
            raise RuntimeError("Portal request failed")

        # Extract the session_handle or shortcuts
        results = response_data["results"]
        if "session_handle" in results:
            return results["session_handle"]
        elif "shortcuts" in results:
            return results["shortcuts"]

        return results

    def on_activated(self, callback: Callable) -> None:
        self._activated_callbacks.append(callback)

    def on_deactivated(self, callback: Callable) -> None:
        self._deactivated_callbacks.append(callback)

    def _on_activated(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        path: str,
        interface: str,
        signal: str,
        params: GLib.Variant,
        user_data,
    ) -> None:
        session_handle, shortcut_id, timestamp, options = params

        # Nothing narrows the subscription to one session, so a press meant
        # for a session we have since let go still arrives here. Only the
        # session we hold has anything to say to the app.
        if session_handle != self.session_handle:
            return

        for callback in self._activated_callbacks:
            callback(shortcut_id, timestamp, dict(options))

    def _on_deactivated(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        path: str,
        interface: str,
        signal: str,
        params: GLib.Variant,
        user_data,
    ) -> None:
        session_handle, shortcut_id, timestamp, options = params

        if session_handle != self.session_handle:
            return

        for callback in self._deactivated_callbacks:
            callback(shortcut_id, timestamp, dict(options))
