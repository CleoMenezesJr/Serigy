# Copyright 2024-2025 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib

import gi
from serigy.clipboard import ClipboardItem, ClipboardItemType, ClipboardQueue
from serigy.define import (
    supported_file_formats,
    supported_image_formats,
    supported_text_formats,
)

gi.require_versions({"Gtk": "4.0", "Adw": "1", "Gdk": "4.0"})
if gi:
    from gi.repository import Adw, Gdk, GLib, Gtk


@Gtk.Template(
    resource_path="/io/github/cleomenezesjr/Serigy/gtk/copy-alert-window.ui"
)
class CopyAlertWindow(Adw.Window):
    __gtype_name__ = "CopyAlertWindow"

    def __init__(
        self,
        queue: ClipboardQueue,
        on_finished=None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.application = kwargs["application"]
        self.on_finished = on_finished
        self.queue = queue
        self.set_opacity(0.01)
        self.connect("show", lambda _: self.on_show())
        self._retry_count = 0
        self._capture_started = False
        self._closed = False
        self.connect("notify::is-active", self._on_focus_changed)

        # Safety timeouts: retry focus at 3s, give up at 10s
        self._retry_timeout = GLib.timeout_add(3000, self._retry_focus)
        self._close_timeout = GLib.timeout_add(10000, self._force_close)

    def _retry_focus(self):
        """Try to get focus again if capture hasn't started."""
        if not self._capture_started and not self._closed:
            self.present()
        return False  # Don't repeat

    def _force_close(self):
        """Force close if still stuck after 5 seconds."""
        if not self._closed:
            self._close()
        return False  # Don't repeat

    def on_show(self):
        self.present()

    def _on_focus_changed(self, window, pspec):
        if self.is_active() and not self._capture_started:
            self._capture_started = True
            self._capture_and_queue()

    def _capture_and_queue(self) -> bool:
        clipboard = Gdk.Display.get_default().get_clipboard()
        formats = clipboard.get_formats().to_string().split(" ")
        current_formats_set = set(formats)

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

        # Retry generic empty formats
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
                content_hash = hashlib.sha256(text.encode()).hexdigest()
                item = ClipboardItem(
                    item_type=ClipboardItemType.TEXT,
                    data=text,
                    content_hash=content_hash,
                )
                self.queue.add(item)
        except Exception:
            pass
        self._close()

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
                        )
                        self.queue.add(item)
        except Exception:
            pass
        self._close()

    def _on_files_ready(self, clipboard, result):
        try:
            file_list = clipboard.read_value_finish(result)
            if file_list:
                for file in file_list:
                    try:
                        info = file.query_info("standard::name", 0, None)
                        content_type = file.query_info(
                            "standard::content-type", 0, None
                        ).get_content_type()
                        original_filename = info.get_name()

                        texture = Gdk.Texture.new_from_file(file)
                        pixbuf = Gdk.pixbuf_get_from_texture(texture)

                        ext = (
                            content_type.rsplit("/", 1)[-1]
                            if "/" in content_type
                            else "png"
                        )
                        try:
                            success, buffer = pixbuf.save_to_bufferv(
                                ext, [], []
                            )
                        except GLib.Error:
                            ext = "png"
                            success, buffer = pixbuf.save_to_bufferv(
                                ext, [], []
                            )

                        if success:
                            content_hash = hashlib.sha256(buffer).hexdigest()
                            name_no_ext = (
                                original_filename.rsplit(".", 1)[0]
                                if "." in original_filename
                                else original_filename
                            )
                            filename = f"{name_no_ext}_{content_hash}.{ext}"
                            item = ClipboardItem(
                                item_type=ClipboardItemType.FILE,
                                data=pixbuf,
                                content_hash=content_hash,
                                filename=filename,
                            )
                            self.queue.add(item)
                    except Exception:
                        continue
        except Exception:
            pass
        self._close()

    def _close(self):
        if self._closed:
            return
        self._closed = True
        # Cancel pending timeouts
        if self._retry_timeout:
            GLib.source_remove(self._retry_timeout)
            self._retry_timeout = None
        if self._close_timeout:
            GLib.source_remove(self._close_timeout)
            self._close_timeout = None
        if self.on_finished:
            self.on_finished()
        self.destroy()
