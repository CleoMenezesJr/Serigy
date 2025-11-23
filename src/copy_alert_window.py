# Copyright 2024 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
import os

import gi
from serigy.define import (
    supported_file_formats,
    supported_image_formats,
    supported_text_formats,
)
from serigy.settings import Settings

gi.require_versions({"Gtk": "4.0", "Adw": "1", "GdkPixbuf": "2.0"})

if gi:
    from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk


@Gtk.Template(
    resource_path="/io/github/cleomenezesjr/Serigy/gtk/copy-alert-window.ui"
)
class CopyAlertWindow(Adw.Window):
    __gtype_name__ = "CopyAlertWindow"

    def __init__(self, main_window, **kwargs):
        super().__init__(**kwargs)

        self.main_window = main_window
        self.slots: GLib.Variant = Settings.get().slots
        self.application = kwargs["application"]
        self.notification = Gio.Notification()
        self.cancellable = None

        self.set_opacity(Settings.get().alert_window_opacity / 100)

        self.connect("show", lambda _: self.on_show())

    def on_show(self):
        GLib.timeout_add(100, self.get_clipboard_data)

    def get_clipboard_data(self) -> None:
        if self.cancellable:
            self.cancellable.cancel()

        self.cancellable = Gio.Cancellable()

        clipboard: Gdk.Clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard_formats: list = (
            clipboard.get_formats().to_string().split(" ")
        )

        if bool(set(supported_image_formats) & set(clipboard_formats)):
            clipboard.read_texture_async(
                cancellable=self.cancellable,
                callback=self.on_clipboard_texture,
            )
        elif bool(set(supported_file_formats) & set(clipboard_formats)):
            clipboard.read_value_async(
                type=Gdk.FileList,
                io_priority=GLib.PRIORITY_DEFAULT,
                cancellable=self.cancellable,
                callback=self.on_clipboard_files,
            )
        elif bool(set(supported_text_formats) & set(clipboard_formats)):
            clipboard.read_text_async(
                cancellable=self.cancellable, callback=self.on_clipboard_text
            )
        else:
            self.close()

            body = _("The content could not be copied to the clipboard.")
            self.send_notification(
                title=_("Copy Failed"),
                body=body,
                id="empty-clipboard",
            )

    def send_notification(self, title: str, body: str, id: str) -> None:
        self.notification.set_title(title)
        self.notification.set_body(body)
        self.application.send_notification(id, self.notification)
        return None

    def on_clipboard_text(
        self, clipboard: Gdk.Clipboard, result: Gio.Task
    ) -> None:
        try:
            text: str = clipboard.read_text_finish(result)
            if not text:
                return None

            cb_list: GLib.Variant = self.slots.unpack()
            if text in cb_list[0][0] and Settings.get().skip_duplicate_copy:
                return None

            cb_list.insert(0, [text, "", ""])
            cb_list: list = cb_list[:-1]

            for _ in range(3):
                self.main_window.grid.remove_column(1)
            self.main_window.update_slots(cb_list)
            self.main_window._set_grid()

        except GLib.Error as e:
            if "cancelled" not in str(e).lower():
                print(f"GLib Error: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")
        finally:
            self.close()

    def on_clipboard_texture(
        self, clipboard: Gdk.Clipboard, result: Gio.Task
    ) -> None:
        try:
            texture: Gdk.MemoryTexture = clipboard.read_texture_finish(result)
            if not texture:
                return None

            pixbuf: GdkPixbuf.Pixbuf = Gdk.pixbuf_get_from_texture(texture)

            success, buffer = pixbuf.save_to_bufferv("png", [], [])
            if not success:
                return None

            image_hash = hashlib.sha256(buffer).hexdigest()
            filename: str = f"{image_hash}.png"
            file_path: str = os.path.join(
                GLib.get_user_cache_dir(), "tmp", filename
            )

            cb_list: GLib.Variant = self.slots.unpack()
            if (
                filename == cb_list[0][1]
                and Settings.get().skip_duplicate_copy
            ):
                return None

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

            for _ in range(3):
                self.main_window.grid.remove_column(1)
            self.main_window.update_slots(cb_list)
            self.main_window._set_grid()

        except GLib.Error as e:
            if "cancelled" not in str(e).lower():
                print(f"GLib Error: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")
        finally:
            self.close()

    def on_clipboard_files(
        self, clipboard: Gdk.FileList, result: Gio.Task
    ) -> None | str:
        try:
            file_list: Gdk.FileList = clipboard.read_value_finish(result)
            if not file_list:
                return None

            for file in file_list:
                file: Gio.File
                info = file.query_info("standard::name", 0, None)
                content_type: str = file.query_info(
                    "standard::content-type", 0, None
                ).get_content_type()
                original_filename: str = info.get_name()

                try:
                    texture: Gdk.Texture = Gdk.Texture.new_from_file(file)
                except (AttributeError, GLib.Error) as e:
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

                cb_list: GLib.Variant = self.slots.unpack()
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

                for _ in range(3):
                    self.main_window.grid.remove_column(1)
                self.main_window.update_slots(cb_list)
                self.main_window._set_grid()

        except GLib.Error as e:
            if "cancelled" not in str(e).lower():
                print(f"GLib Error: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")
        finally:
            self.close()
