# Copyright 2024 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib

import gi
from serigy.clipboard_queue import ClipboardItem, ClipboardItemType, ClipboardQueue
from serigy.define import (
    supported_file_formats,
    supported_image_formats,
    supported_text_formats,
)

gi.require_versions({"Gtk": "4.0", "Adw": "1", "Gdk": "4.0", "GdkPixbuf": "2.0"})
from gi.repository import Adw, Gdk, GLib, Gtk


@Gtk.Template(
    resource_path="/io/github/cleomenezesjr/Serigy/gtk/copy-alert-window.ui"
)
class CopyAlertWindow(Adw.Window):
    __gtype_name__ = "CopyAlertWindow"

    def __init__(self, main_window, queue: ClipboardQueue, on_finished=None, **kwargs):
        super().__init__(**kwargs)

        self.main_window = main_window
        self.application = kwargs["application"]
        self.on_finished = on_finished
        self.queue = queue
        self.set_opacity(0.5)
        self.connect("show", lambda _: self.on_show())

    def on_show(self):
        self.present()
        GLib.timeout_add(500, self._capture_and_queue)

    def _capture_and_queue(self) -> bool:
        clipboard = Gdk.Display.get_default().get_clipboard()
        formats = clipboard.get_formats().to_string().split(" ")

        is_image = bool(set(supported_image_formats) & set(formats))
        is_file = bool(set(supported_file_formats) & set(formats))
        is_text = bool(set(supported_text_formats) & set(formats))

        if is_image:
            clipboard.read_texture_async(None, self._on_texture_ready)
        elif is_file:
            clipboard.read_value_async(
                Gdk.FileList, GLib.PRIORITY_DEFAULT, None, self._on_files_ready
            )
        elif is_text:
            clipboard.read_text_async(None, self._on_text_ready)
        else:
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

                        ext = content_type.rsplit("/", 1)[-1] if "/" in content_type else "png"
                        try:
                            success, buffer = pixbuf.save_to_bufferv(ext, [], [])
                        except GLib.Error:
                            ext = "png"
                            success, buffer = pixbuf.save_to_bufferv(ext, [], [])

                        if success:
                            content_hash = hashlib.sha256(buffer).hexdigest()
                            name_no_ext = original_filename.rsplit(".", 1)[0] if "." in original_filename else original_filename
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
        if self.on_finished:
            self.on_finished()
        self.close()
