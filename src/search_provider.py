# Copyright 2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

"""org.gnome.Shell.SearchProvider2 over the stored slots.

Activating a text result costs nothing: the shell writes the clipboard
itself, from the `clipboardText` it was already handed to draw the row. An
image or a file cannot travel in that field, so those are written by us,
which needs focus and can therefore fail.
"""

import logging
from gettext import gettext as _

from gi.repository import Gio, GLib

from serigy import search_query
from serigy.content_type import detect as detect_content_type
from serigy.image_store import image_path
from serigy.settings import Settings
from serigy.slot_display import relative_time, summary

INTERFACE_XML = """
<node>
  <interface name="org.gnome.Shell.SearchProvider2">
    <method name="GetInitialResultSet">
      <arg type="as" name="terms" direction="in"/>
      <arg type="as" name="results" direction="out"/>
    </method>
    <method name="GetSubsearchResultSet">
      <arg type="as" name="previous_results" direction="in"/>
      <arg type="as" name="terms" direction="in"/>
      <arg type="as" name="results" direction="out"/>
    </method>
    <method name="GetResultMetas">
      <arg type="as" name="identifiers" direction="in"/>
      <arg type="aa{sv}" name="metas" direction="out"/>
    </method>
    <method name="ActivateResult">
      <arg type="s" name="identifier" direction="in"/>
      <arg type="as" name="terms" direction="in"/>
      <arg type="u" name="timestamp" direction="in"/>
    </method>
    <method name="LaunchSearch">
      <arg type="as" name="terms" direction="in"/>
      <arg type="u" name="timestamp" direction="in"/>
    </method>
  </interface>
</node>
"""


class SearchProvider:
    def __init__(self, application):
        self._application = application
        self._registration_id: int | None = None
        self._node = Gio.DBusNodeInfo.new_for_xml(INTERFACE_XML)

    def register(self, connection: Gio.DBusConnection, object_path: str):
        self._registration_id = connection.register_object(
            object_path,
            self._node.interfaces[0],
            self._on_method_call,
            None,
            None,
        )
        logging.debug("Search provider registered at %s", object_path)

    def unregister(self, connection: Gio.DBusConnection):
        if self._registration_id is None:
            return
        connection.unregister_object(self._registration_id)
        self._registration_id = None

    def _on_method_call(
        self,
        connection,
        sender,
        object_path,
        interface_name,
        method_name,
        parameters,
        invocation,
    ):
        try:
            if method_name == "GetInitialResultSet":
                (terms,) = parameters.unpack()
                invocation.return_value(
                    GLib.Variant("(as)", (self._search(terms),))
                )
            elif method_name == "GetSubsearchResultSet":
                _previous, terms = parameters.unpack()
                invocation.return_value(
                    GLib.Variant("(as)", (self._search(terms),))
                )
            elif method_name == "GetResultMetas":
                (identifiers,) = parameters.unpack()
                invocation.return_value(
                    GLib.Variant("(aa{sv})", (self._metas(identifiers),))
                )
            elif method_name == "ActivateResult":
                identifier, _terms, _timestamp = parameters.unpack()
                self._activate(identifier)
                invocation.return_value(None)
            elif method_name == "LaunchSearch":
                self._application.do_activate()
                invocation.return_value(None)
            else:
                invocation.return_error_literal(
                    Gio.dbus_error_quark(),
                    Gio.DBusError.UNKNOWN_METHOD,
                    method_name,
                )
        except Exception:
            # A raise here would leave the shell waiting on a reply that
            # never comes, and the overview would stall on every keystroke.
            logging.exception("Search provider failed on %s", method_name)
            invocation.return_error_literal(
                Gio.dbus_error_quark(),
                Gio.DBusError.FAILED,
                f"{method_name} failed",
            )

    def _search(self, terms: list[str]) -> list[str]:
        """Answer the overview.

        A subsearch is recomputed rather than narrowed from the previous
        answer: a copy landing mid-typing belongs in the list, and the
        matching is cheap enough that keeping state would buy nothing.
        """
        if Settings.get().incognito_mode:
            return []
        return search_query.result_ids(Settings.get().slots, terms)

    def _metas(self, identifiers: list[str]) -> list[dict]:
        slots = Settings.get().slots
        metas = []
        for identifier in identifiers:
            slot = search_query.find(slots, identifier)
            if slot is None:
                # The shell throws if it gets back fewer metas than it
                # asked for, and takes the whole section down with it. A
                # copy rotating out mid-search is ordinary, so answer for
                # it rather than let one stale row cost all of them.
                metas.append(
                    {
                        "id": GLib.Variant("s", identifier),
                        "name": GLib.Variant("s", _("No longer available")),
                    }
                )
                continue
            metas.append(self._meta(slot, identifier))
        return metas

    def _meta(self, slot, identifier: str) -> dict:
        meta = {"id": GLib.Variant("s", identifier)}

        if slot.text:
            content_type = detect_content_type(slot.text, slot.mime)
            meta["name"] = GLib.Variant(
                "s", summary(slot.text) or content_type.name
            )
            meta["description"] = GLib.Variant(
                "s", self._description(content_type.name, slot.timestamp)
            )
            # No icon for text: the overview would draw a generic-document
            # glyph that looks like a file, which is misleading for a copy
            # the shell is about to put on the clipboard.
            meta["clipboardText"] = GLib.Variant("s", slot.text)
        elif slot.filename:
            meta["name"] = GLib.Variant("s", _("Image"))
            meta["description"] = GLib.Variant(
                "s", self._description(_("Image"), slot.timestamp)
            )
            icon = Gio.FileIcon.new(
                Gio.File.new_for_path(str(image_path(slot.filename)))
            )
            self._set_icon(meta, icon, "image-x-generic-symbolic")
        else:
            meta["name"] = GLib.Variant(
                "s", search_query.basename(slot.uri) or slot.uri
            )
            meta["description"] = GLib.Variant(
                "s", self._description(_("File"), slot.timestamp)
            )
            icon = Gio.content_type_get_symbolic_icon(
                slot.mime or "application/octet-stream"
            )
            self._set_icon(meta, icon, "folder-symbolic")

        return meta

    def _set_icon(self, meta: dict, icon, fallback: str) -> None:
        """Prefer the real icon, keep a name in reserve.

        `serialize` answers None for an icon it cannot express, and a meta
        without any icon key draws a blank square.
        """
        serialized = icon.serialize() if icon is not None else None
        if serialized is not None:
            meta["icon"] = serialized
        else:
            meta["gicon"] = GLib.Variant("s", fallback)

    def _description(self, type_name: str, timestamp: str) -> str:
        """The sentence the card shows under its header."""
        rel_time = relative_time(timestamp)
        return f"{type_name} • {rel_time}" if rel_time else type_name

    def _activate(self, identifier: str) -> None:
        settings = Settings.get()
        if settings.incognito_mode:
            # It can have been switched on between the listing and the
            # Enter, and incognito refuses every capture in both directions.
            logging.debug("Search activation refused, incognito is on")
            return

        slot = search_query.find(settings.slots, identifier)

        if slot is not None and slot.text:
            # The shell has written it already. Left alone, the monitor
            # would see that write and store the same text as a new copy.
            self._application.clipboard_monitor.suppress_next_change()
            return

        if slot is None:
            if identifier.startswith("t:"):
                # The text reached the clipboard anyway: it travelled inside
                # the meta the shell already held.
                logging.debug("Activated text slot is gone, nothing to do")
                return
            logging.debug("Activated slot %s is gone", identifier)
            self._notify_failure()
            return

        self._application.write_slot_to_clipboard(
            slot, on_failed=self._notify_failure
        )

    def _notify_failure(self) -> None:
        """Tell the user only when the copy truly could not be made.

        A focus refusal reaches here only after every attempt is spent. The
        other callers are content that is gone, or a capture already holding
        the clipboard — cases no retry would fix.
        """
        notification = Gio.Notification.new(_("Could not copy"))
        notification.set_body(_("Open Serigy and click the slot to copy it."))
        notification.set_default_action("app.open-window")
        self._application.send_notification("search-copy-failed", notification)
