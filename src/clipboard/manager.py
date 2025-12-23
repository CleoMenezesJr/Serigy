# Copyright 2024 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
import os
from gettext import gettext as _
from typing import Callable, Optional

from serigy.define import (
    supported_file_formats,
    supported_image_formats,
    supported_text_formats,
)
from serigy.settings import Settings
from .queue import ClipboardItem, ClipboardItemType

import gi

gi.require_versions({"Gdk": "4.0"})
if gi:
    from gi.repository import Gdk, Gio, GLib


class ClipboardManager:
    def __init__(self, main_window_provider, application):
        self.main_window_provider = main_window_provider
        self.application = application
        self.notification = Gio.Notification()
        self.cancellable = None
        self.on_finish = None

    def send_notification(self, title: str, body: str, id: str) -> None:
        self.notification.set_title(title)
        self.notification.set_body(body)
        self.application.send_notification(id, self.notification)

    def _find_last_unpinned_slot(self, cb_list: list) -> Optional[int]:
        for i in range(len(cb_list) - 1, -1, -1):
            if cb_list[i][2] != "pinned":
                return i
        return None

    def _remove_old_file_if_exists(self, cb_list: list, idx: int) -> None:
        if cb_list[idx][1]:
            old_file_path = os.path.join(
                GLib.get_user_cache_dir(), "tmp", cb_list[idx][1]
            )
            if os.path.exists(old_file_path):
                os.remove(old_file_path)

    def process_clipboard(self, on_finish: Callable[[], None] = None) -> None:
        self.on_finish = on_finish
        if self.cancellable:
            self.cancellable.cancel()

        self.cancellable = Gio.Cancellable()

        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard_formats = clipboard.get_formats().to_string().split(" ")

        is_image = bool(set(supported_image_formats) & set(clipboard_formats))
        is_file = bool(set(supported_file_formats) & set(clipboard_formats))
        is_text = bool(set(supported_text_formats) & set(clipboard_formats))

        if is_image:
            clipboard.read_texture_async(
                cancellable=self.cancellable,
                callback=self.on_clipboard_texture,
            )
        elif is_file:
            clipboard.read_value_async(
                type=Gdk.FileList,
                io_priority=GLib.PRIORITY_DEFAULT,
                cancellable=self.cancellable,
                callback=self.on_clipboard_files,
            )
        elif is_text:
            clipboard.read_text_async(
                cancellable=self.cancellable,
                callback=self.on_clipboard_text,
            )
        else:
            self.send_notification(
                title=_("Copy Failed"),
                body=_("The content could not be copied to the clipboard."),
                id="empty-clipboard",
            )
            if self.on_finish:
                self.on_finish()

    def _update_slots(self, cb_list: list) -> None:
        window = self.main_window_provider()
        Settings.get().slots = GLib.Variant("aas", cb_list)

        if window:
            for _ in range(3):
                if hasattr(window, "grid"):
                    window.grid.remove_column(1)
            window.update_slots(cb_list)
            window._set_grid()

        if self.on_finish:
            self.on_finish()

    def process_item(self, item: ClipboardItem) -> None:
        cb_list = Settings.get().slots.unpack()

        if item.item_type == ClipboardItemType.TEXT:
            if item.data in cb_list[0][0]:
                return
        else:
            if item.filename and item.filename == cb_list[0][1]:
                return

        last_unpinned_idx = self._find_last_unpinned_slot(cb_list)
        if last_unpinned_idx is None:
            return

        self._remove_old_file_if_exists(cb_list, last_unpinned_idx)
        cb_list.pop(last_unpinned_idx)

        if item.item_type == ClipboardItemType.TEXT:
            cb_list.insert(0, [item.data, "", ""])
        else:
            if item.filename:
                file_path = os.path.join(
                    GLib.get_user_cache_dir(), "tmp", item.filename
                )
                if not os.path.exists(file_path) and item.data:
                    try:
                        ext = (
                            item.filename.rsplit(".", 1)[-1]
                            if "." in item.filename
                            else "png"
                        )
                        item.data.savev(file_path, ext, [], [])
                    except Exception:
                        return
            cb_list.insert(0, ["", item.filename, ""])

        self._update_slots_no_callback(cb_list)

    def _update_slots_no_callback(self, cb_list: list) -> None:
        window = self.main_window_provider()
        Settings.get().slots = GLib.Variant("aas", cb_list)

        if window:
            for _ in range(3):
                if hasattr(window, "grid"):
                    window.grid.remove_column(1)
            window.update_slots(cb_list)
            window._set_grid()

    def on_clipboard_text(
        self, clipboard: Gdk.Clipboard, result: Gio.Task
    ) -> None:
        try:
            text = clipboard.read_text_finish(result)
            if not text:
                if self.on_finish:
                    self.on_finish()
                return

            cb_list = Settings.get().slots.unpack()
            if text in cb_list[0][0]:
                if self.on_finish:
                    self.on_finish()
                return

            last_unpinned_idx = self._find_last_unpinned_slot(cb_list)
            if last_unpinned_idx is None:
                if self.on_finish:
                    self.on_finish()
                return

            cb_list.pop(last_unpinned_idx)
            cb_list.insert(0, [text, "", ""])
            self._update_slots(cb_list)

        except GLib.Error:
            if self.on_finish:
                self.on_finish()
        except Exception:
            if self.on_finish:
                self.on_finish()

    def on_clipboard_texture(
        self, clipboard: Gdk.Clipboard, result: Gio.Task
    ) -> None:
        try:
            texture = clipboard.read_texture_finish(result)
            if not texture:
                if self.on_finish:
                    self.on_finish()
                return

            pixbuf = Gdk.pixbuf_get_from_texture(texture)
            if not pixbuf:
                if self.on_finish:
                    self.on_finish()
                return

            success, buffer = pixbuf.save_to_bufferv("png", [], [])
            if not success:
                if self.on_finish:
                    self.on_finish()
                return

            image_hash = hashlib.sha256(buffer).hexdigest()
            filename = f"{image_hash}.png"
            file_path = os.path.join(
                GLib.get_user_cache_dir(), "tmp", filename
            )

            cb_list = Settings.get().slots.unpack()
            if filename == cb_list[0][1]:
                if self.on_finish:
                    self.on_finish()
                return

            if not os.path.exists(file_path):
                pixbuf.savev(file_path, "png", [], [])

            last_unpinned_idx = self._find_last_unpinned_slot(cb_list)
            if last_unpinned_idx is None:
                if self.on_finish:
                    self.on_finish()
                return

            self._remove_old_file_if_exists(cb_list, last_unpinned_idx)
            cb_list.pop(last_unpinned_idx)
            cb_list.insert(0, ["", filename, ""])
            self._update_slots(cb_list)

        except GLib.Error:
            pass
        except Exception:
            pass

    def on_clipboard_files(
        self, clipboard: Gdk.FileList, result: Gio.Task
    ) -> None:
        try:
            file_list = clipboard.read_value_finish(result)
            if not file_list:
                if self.on_finish:
                    self.on_finish()
                return

            for file in file_list:
                info = file.query_info("standard::name", 0, None)
                content_type = file.query_info(
                    "standard::content-type", 0, None
                ).get_content_type()
                original_filename = info.get_name()

                try:
                    texture = Gdk.Texture.new_from_file(file)
                except (AttributeError, GLib.Error):
                    self.send_notification(
                        title=_("Invalid Clipboard Format"),
                        body=_(
                            f"{original_filename} file has unsupported format. "
                        )
                        + _("Only text and image formats are supported."),
                        id="invalid-clipboard-format",
                    )
                    continue

                pixbuf = Gdk.pixbuf_get_from_texture(texture)

                last_slash_index = content_type.rfind("/") + 1
                file_extension = content_type[last_slash_index:] or "png"

                try:
                    success, buffer = pixbuf.save_to_bufferv(
                        file_extension, [], []
                    )
                except GLib.Error:
                    file_extension = "png"
                    success, buffer = pixbuf.save_to_bufferv(
                        file_extension, [], []
                    )

                if not success:
                    continue

                image_hash = hashlib.sha256(buffer).hexdigest()
                name_without_ext = os.path.splitext(original_filename)[0]
                filename = f"{name_without_ext}_{image_hash}.{file_extension}"
                file_path = os.path.join(
                    GLib.get_user_cache_dir(), "tmp", filename
                )

                cb_list = Settings.get().slots.unpack()
                if cb_list[0][1] and image_hash in cb_list[0][1]:
                    continue

                if not os.path.exists(file_path):
                    pixbuf.savev(file_path, file_extension, [], [])

                last_unpinned_idx = self._find_last_unpinned_slot(cb_list)
                if last_unpinned_idx is None:
                    continue

                self._remove_old_file_if_exists(cb_list, last_unpinned_idx)
                cb_list.pop(last_unpinned_idx)
                cb_list.insert(0, ["", filename, ""])
                self._update_slots(cb_list)
                return

            if self.on_finish:
                self.on_finish()

        except GLib.Error:
            if self.on_finish:
                self.on_finish()
        except Exception:
            if self.on_finish:
                self.on_finish()
