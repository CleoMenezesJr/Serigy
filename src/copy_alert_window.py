# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
import logging

import gi

from serigy.clipboard import ClipboardItem, ClipboardItemType, ClipboardQueue
from serigy.define import (
    RESOURCE_PATH,
    supported_file_formats,
    supported_image_formats,
    supported_text_formats,
)
from serigy.settings import Settings

gi.require_versions(
    {"Gtk": "4.0", "Adw": "1", "Gdk": "4.0", "GdkPixbuf": "2.0"}
)
from gi.repository import Adw, Gdk, Gio, GLib, Gtk


@Gtk.Template(resource_path=f"{RESOURCE_PATH}/gtk/copy-alert-window.ui")
class CopyAlertWindow(Adw.Window):
    __gtype_name__ = "CopyAlertWindow"

    def __init__(
        self,
        queue: ClipboardQueue,
        on_finished=None,
        visible_mode: bool = False,
        sentinel: str | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.application = kwargs["application"]
        self.on_finished = on_finished
        self.queue = queue
        self.visible_mode = visible_mode
        self._sentinel = sentinel
        # Transparent for auto-copies, visible for shortcut-triggered
        self.set_opacity(1.0 if visible_mode else 0.01)
        self.connect("show", lambda _: self.on_show())
        self._retry_count = 0
        self._capture_started = False
        self._closed = False
        self.connect("notify::is-active", self._on_focus_changed)

        self._retry_timeout = GLib.timeout_add(3000, self._retry_focus)
        self._close_timeout = GLib.timeout_add(10000, self._force_close)
        logging.debug(
            "CopyAlertWindow created (visible_mode=%s)", visible_mode
        )

    def _retry_focus(self):
        self._retry_timeout = None
        if not self._capture_started and not self._closed:
            logging.debug(
                "CopyAlertWindow: no focus after 3s, retrying present()"
            )
            self.present()
        return False

    def _force_close(self):
        self._close_timeout = None
        if not self._closed:
            logging.debug(
                "CopyAlertWindow: force-closed after 10s without capture"
            )
            self._close()
        return False

    def on_show(self):
        logging.debug("CopyAlertWindow: on_show, calling present()")
        self.present()

    def _on_focus_changed(self, window, pspec):
        logging.debug(
            "CopyAlertWindow: is-active changed → %s (capture_started=%s)",
            self.is_active(),
            self._capture_started,
        )
        if self.is_active() and not self._capture_started:
            self._capture_started = True
            self._capture_and_queue()

    def _capture_and_queue(self) -> bool:
        clipboard = Gdk.Display.get_default().get_clipboard()
        formats = clipboard.get_formats().to_string().split(" ")
        current_formats_set = set(formats)

        if (
            Settings.get().filter_sensitive
            and "x-kde-passwordManagerHint" in current_formats_set
        ):
            logging.debug(
                "Sensitive content filtered (x-kde-passwordManagerHint)"
            )
            self._close()
            return False

        is_image = bool(set(supported_image_formats) & current_formats_set)
        is_file = bool(set(supported_file_formats) & current_formats_set)
        is_text = bool(set(supported_text_formats) & current_formats_set)

        if is_image:
            clipboard.read_texture_async(None, self._on_texture_ready)
            return False
        elif is_file:
            clipboard.read_value_async(
                Gdk.FileList, GLib.PRIORITY_DEFAULT, None, self._on_files_ready
            )
            return False
        elif is_text:
            clipboard.read_text_async(None, self._on_text_ready)
            return False

        self._retry_count += 1
        if self._retry_count < 10:
            GLib.timeout_add(50, self._capture_and_queue)
            return False

        self._close()
        return False

    def _on_text_ready(self, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                if self._sentinel and text == self._sentinel:
                    self._close()
                    return
                for item in self._text_items(text):
                    self.queue.add(item)
        except Exception:
            pass
        self._close()

    def _text_items(self, text: str) -> list[ClipboardItem]:
        """Turn the copied text into items, watching for file uris.

        Once the app that copied a file quits, the clipboard keeps only the
        text flavour of that copy, which is the list of uris. Stored as text
        it becomes a slot that pastes a path where a file was expected.
        """
        if text.startswith("file://"):
            uris = text.split()
            if all(uri.startswith("file://") for uri in uris):
                items = (
                    self._reference_item(Gio.File.new_for_uri(uri))
                    for uri in uris
                )
                return [item for item in items if item]

        return [
            ClipboardItem(
                item_type=ClipboardItemType.TEXT,
                data=text,
                content_hash=hashlib.sha256(text.encode()).hexdigest(),
                mime="text/plain",
            )
        ]

    def _on_texture_ready(self, clipboard, result):
        try:
            texture = clipboard.read_texture_finish(result)
            if texture:
                pixbuf = Gdk.pixbuf_get_from_texture(texture)
                if pixbuf:
                    success, buffer = pixbuf.save_to_bufferv("png", [], [])
                    if success:
                        content_hash = hashlib.sha256(buffer).hexdigest()
                        filename = f"{content_hash}.png"
                        item = ClipboardItem(
                            item_type=ClipboardItemType.IMAGE,
                            data=pixbuf,
                            content_hash=content_hash,
                            filename=filename,
                            mime="image/png",
                        )
                        self.queue.add(item)
        except Exception:
            pass
        self._close()

    def _on_files_ready(self, clipboard, result):
        try:
            file_list = clipboard.read_value_finish(result)
        except GLib.Error as e:
            logging.warning("Could not read the copied files: %s", e.message)
            self._close()
            return

        for file in file_list or []:
            item = self._image_item(file) or self._reference_item(file)
            if item:
                self.queue.add(item)

        self._close()

    def _image_item(self, file: Gio.File) -> ClipboardItem | None:
        """Read the file as an image, when its bytes are within reach.

        An image slot can be shown and pasted into anything that takes a
        picture, which a uri cannot. Only apps under the same sandbox rules
        hand over readable files, so this often fails.
        """
        try:
            texture = Gdk.Texture.new_from_file(file)
            pixbuf = Gdk.pixbuf_get_from_texture(texture)
            content_type = file.query_info(
                "standard::content-type", 0, None
            ).get_content_type()
        except GLib.Error as e:
            logging.debug(
                "Keeping %s as a reference: %s", file.get_uri(), e.message
            )
            return None

        ext = content_type.rsplit("/", 1)[-1] if "/" in content_type else "png"
        try:
            success, buffer = pixbuf.save_to_bufferv(ext, [], [])
        except GLib.Error:
            ext = "png"
            success, buffer = pixbuf.save_to_bufferv(ext, [], [])

        if not success:
            return None

        content_hash = hashlib.sha256(buffer).hexdigest()
        name = file.get_basename() or ""
        stem = name.rsplit(".", 1)[0] if "." in name else name
        return ClipboardItem(
            item_type=ClipboardItemType.FILE,
            data=pixbuf,
            content_hash=content_hash,
            filename=f"{stem}_{content_hash}.{ext}",
            mime=f"image/{ext}",
        )

    def _reference_item(self, file: Gio.File) -> ClipboardItem | None:
        """Point at the file, which is all the clipboard itself held.

        The type comes from the name because reading the file is what we
        cannot count on doing.
        """
        uri = file.get_uri()
        if not uri:
            return None

        name = file.get_basename() or uri
        return ClipboardItem(
            item_type=ClipboardItemType.FILE,
            data=None,
            content_hash=hashlib.sha256(uri.encode()).hexdigest(),
            mime=Gio.content_type_guess(name, None)[0],
            uri=uri,
        )

    def _close(self):
        if self._closed:
            return
        self._closed = True
        if self._retry_timeout:
            GLib.source_remove(self._retry_timeout)
            self._retry_timeout = None
        if self._close_timeout:
            GLib.source_remove(self._close_timeout)
            self._close_timeout = None
        if self.on_finished:
            self.on_finished()
        self.destroy()
