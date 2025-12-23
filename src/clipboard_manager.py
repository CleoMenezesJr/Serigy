# Copyright 2024 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
import os
from gettext import gettext as _

from typing import Callable

import gi
from serigy.define import (
    supported_file_formats,
    supported_image_formats,
    supported_text_formats,
)
from serigy.settings import Settings

gi.require_versions({"Gdk": "4.0", "GdkPixbuf": "2.0"})

gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")

if gi:
    from gi.repository import Gdk, GdkPixbuf, Gio, GLib


class ClipboardManager:
    def __init__(self, main_window_provider, application):
        self.main_window_provider = main_window_provider
        self.application = application
        self.notification = Gio.Notification()
        self.cancellable = None

    def send_notification(self, title: str, body: str, id: str) -> None:
        self.notification.set_title(title)
        self.notification.set_body(body)
        self.application.send_notification(id, self.notification)

    def process_clipboard(self, on_finish: Callable[[], None] = None) -> None:
        self.on_finish = on_finish
        if self.cancellable:
            self.cancellable.cancel()

        self.cancellable = Gio.Cancellable()

        clipboard: Gdk.Clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard_formats: list = (
            clipboard.get_formats().to_string().split(" ")
        )

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
                cancellable=self.cancellable, callback=self.on_clipboard_text
            )
        else:
            body = _("The content could not be copied to the clipboard.")
            self.send_notification(
                title=_("Copy Failed"),
                body=body,
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

    def on_clipboard_text(
        self, clipboard: Gdk.Clipboard, result: Gio.Task
    ) -> None:
        try:
            text: str = clipboard.read_text_finish(result)
            if not text:
                if self.on_finish:
                    self.on_finish()
                return

            cb_list: GLib.Variant = Settings.get().slots.unpack()
            if text in cb_list[0][0] and Settings.get().skip_duplicate_copy:
                if self.on_finish:
                    self.on_finish()
                return

            cb_list.insert(0, [text, "", ""])
            cb_list: list = cb_list[:-1]

            self._update_slots(cb_list)

        except GLib.Error as e:
            if "cancelled" not in str(e).lower():
                print(f"GLib Error: {e}")
            if self.on_finish:
                self.on_finish()
        except Exception as e:
            print(f"Unexpected error: {e}")
            if self.on_finish:
                self.on_finish()

    def on_clipboard_texture(
        self, clipboard: Gdk.Clipboard, result: Gio.Task
    ) -> None:
        try:
            texture: Gdk.MemoryTexture = clipboard.read_texture_finish(result)
            if not texture:
                if self.on_finish:
                     self.on_finish()
                return

            pixbuf: GdkPixbuf.Pixbuf = Gdk.pixbuf_get_from_texture(texture)
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
            filename: str = f"{image_hash}.png"
            file_path: str = os.path.join(
                GLib.get_user_cache_dir(), "tmp", filename
            )

            cb_list: GLib.Variant = Settings.get().slots.unpack()
            if (
                filename == cb_list[0][1]
                and Settings.get().skip_duplicate_copy
            ):
                if self.on_finish:
                     self.on_finish()
                return

            if not os.path.exists(file_path):
                pixbuf.savev(file_path, "png", [], [])

            cb_list.insert(0, ["", filename, ""])

            if cb_list[-1][1]:
                old_file_path = os.path.join(
                    GLib.get_user_cache_dir(),
                    "tmp",
                    cb_list[-1][1],
                )
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)

            cb_list: list = cb_list[:-1]

            self._update_slots(cb_list)

        except GLib.Error as e:
            if "cancelled" not in str(e).lower():
                print(f"GLib Error: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

    def on_clipboard_files(
        self, clipboard: Gdk.FileList, result: Gio.Task
    ) -> None | str:
        try:
            file_list: Gdk.FileList = clipboard.read_value_finish(result)
            if not file_list:
                if self.on_finish:
                    self.on_finish()
                return

            for file in file_list:
                file: Gio.File
                info = file.query_info("standard::name", 0, None)
                content_type: str = file.query_info(
                    "standard::content-type", 0, None
                ).get_content_type()
                original_filename: str = info.get_name()

                try:
                    texture: Gdk.Texture = Gdk.Texture.new_from_file(file)
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

                pixbuf: GdkPixbuf.Pixbuf = Gdk.pixbuf_get_from_texture(texture)

                last_slash_index = content_type.rfind("/") + 1
                file_extension = content_type[last_slash_index:]
                # Fix for some content types or defaulting
                if not file_extension:
                    file_extension = "png"

                # Check if save supported
                # Simplified check logic here as pixbuf.save_to_bufferv throws if format not supported
                try:
                    success, buffer = pixbuf.save_to_bufferv(
                        file_extension, [], []
                    )
                except GLib.Error:
                    # Fallback to png if original format not supported for saving
                    file_extension = "png"
                    success, buffer = pixbuf.save_to_bufferv(
                        file_extension, [], []
                    )

                if not success:
                    continue

                image_hash = hashlib.sha256(buffer).hexdigest()

                name_without_ext = os.path.splitext(original_filename)[0]
                filename: str = (
                    f"{name_without_ext}_{image_hash}.{file_extension}"
                )
                file_path: str = os.path.join(
                    GLib.get_user_cache_dir(), "tmp", filename
                )

                cb_list: GLib.Variant = Settings.get().slots.unpack()
                if (
                    cb_list[0][1]
                    and image_hash in cb_list[0][1]
                    and Settings.get().skip_duplicate_copy
                ):
                    continue

                if not os.path.exists(file_path):
                    pixbuf.savev(file_path, file_extension, [], [])

                cb_list.insert(0, ["", filename, ""])

                if cb_list[-1][1]:
                    old_file_path = os.path.join(
                        GLib.get_user_cache_dir(),
                        "tmp",
                        cb_list[-1][1],
                    )
                    if os.path.exists(old_file_path):
                        os.remove(old_file_path)

                cb_list: list = cb_list[:-1]

                self._update_slots(cb_list)
                return

            # If loop finished without returning (no valid files found), close.
            if self.on_finish:
                self.on_finish()

        except GLib.Error as e:
            if "cancelled" not in str(e).lower():
                print(f"GLib Error: {e}")
            if self.on_finish:
                self.on_finish()
        except Exception as e:
            print(f"Unexpected error: {e}")
            if self.on_finish:
                self.on_finish()
