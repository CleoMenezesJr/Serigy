# window.py
#
# Copyright 2024 Cleo Menezes Jr.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
from datetime import datetime
from threading import Thread
from time import sleep

import gi

gi.require_versions({"Gtk": "4.0", "Adw": "1"})

if gi:
    from gi.repository import Adw, Gdk, Gio, GLib, Gtk


@Gtk.Template(
    resource_path="/io/github/cleomenezesjr/Serigy/gtk/copy-alert-window.ui"
)
class CopyAlertWindow(Adw.Window):
    __gtype_name__ = "CopyAlertWindow"

    def __init__(self, main_window, **kwargs):
        super().__init__(**kwargs)

        self.main_window = main_window

        self.notification = Gio.Notification()
        self.notification.set_title("Empty clipboard or unsupported format")
        self.notification.set_body("Copy some text or image to be able to pin")

        self.connect("show", lambda _: Thread(target=self.setup).start())

    def setup(self) -> None:
        sleep(1)
        clipboard: Gdk.Clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard_formats: list = clipboard.get_formats().to_string()

        if "GdkTexture" in clipboard_formats:
            clipboard.read_texture_async(
                cancellable=None, callback=self.on_clipboard_texture
            )
        elif "GdkFileList" in clipboard_formats:
            clipboard.read_value_async(
                type=Gdk.FileList,
                io_priority=GLib.PRIORITY_DEFAULT,
                cancellable=None,
                callback=self.on_clipboard_files,
            )
        elif "gchararray" in clipboard_formats:
            clipboard.read_text_async(
                cancellable=None, callback=self.on_clipboard_text
            )
        else:
            self.close()
            self.get_application().send_notification(
                "empty-clipboard", self.notification
            )

    def on_clipboard_text(self, clipboard, result):
        try:
            text: str = clipboard.read_text_finish(result)
            if text:
                cb_list: GLib.Variant = self.main_window.settings.get_value(
                    "pinned-clipboard-history"
                ).unpack()
                cb_list.insert(0, [text, "", ""])
                cb_list: list = cb_list[:-1]

                for _ in range(3):
                    self.main_window.grid.remove_column(1)
                self.main_window.update_history(cb_list)
                self.main_window._set_grid()

            self.close()

        except GLib.Error as e:
            print("Erro ao ler da área de transferência:", e.message)
            self.on_load_clipboard(has_window)
        except Exception as e:
            print("Erro inesperado:", e)

    def on_clipboard_texture(self, clipboard: Gdk.Clipboard, result: Gio.Task):
        try:
            texture: Gdk.MemoryTexture = clipboard.read_texture_finish(result)
            if texture:
                pixbuf: GdkPixbuf.Pixbuf = Gdk.pixbuf_get_from_texture(texture)
                filename: str = f"{datetime.now()}.png"
                file_path: str = os.path.join(
                    GLib.get_user_cache_dir(), "tmp", filename
                )
                pixbuf.savev(file_path, "png", [], [])

                cb_list: GLib.Variant = self.main_window.settings.get_value(
                    "pinned-clipboard-history"
                ).unpack()
                cb_list.insert(0, ["", filename, ""])

                if cb_list[-1][1]:
                    os.remove(
                        os.path.join(
                            GLib.get_user_cache_dir(),
                            "tmp",
                            cb_list[-1][1],
                        )
                    )

                cb_list: list = cb_list[:-1]

                for _ in range(3):
                    self.main_window.grid.remove_column(1)
                self.main_window.update_history(cb_list)
                self.main_window._set_grid()

            self.close()

        except GLib.Error as e:
            print("Erro ao ler da área de transferência:", e.message)
            self.on_load_clipboard(has_window)
        except Exception as e:
            print("Erro inesperado:", e)

    def on_clipboard_files(self, clipboard: Gdk.FileList, result: Gio.Task):
        try:
            file_list: Gdk.FileList = clipboard.read_value_finish(result)
            if file_list:
                for file in file_list:
                    file: Gio.File
                    info = file.query_info("standard::name", 0, None)
                    content_type: str = file.query_info(
                        "standard::content-type", 0, None
                    ).get_content_type()
                    filename: str = f"{info.get_name()}"

                    try:
                        texture: Gdk.Texture = Gdk.Texture.new_from_file(file)
                    except (AttributeError, GLib.Error) as e:
                        self.get_application().send_notification(
                            "empty-clipboard", self.notification
                        )
                        continue

                    pixbuf: GdkPixbuf.Pixbuf = Gdk.pixbuf_get_from_texture(
                        texture
                    )
                    file_path: str = os.path.join(
                        GLib.get_user_cache_dir(), "tmp", filename
                    )
                    file_extension = content_type[
                        content_type.rfind("/") + 1 :
                    ]
                    pixbuf.savev(file_path, file_extension, [], [])

                    cb_list: GLib.Variant = (
                        self.main_window.settings.get_value(
                            "pinned-clipboard-history"
                        ).unpack()
                    )
                    cb_list.insert(0, ["", filename, ""])

                    if cb_list[-1][1]:
                        os.remove(
                            os.path.join(
                                GLib.get_user_cache_dir(),
                                "tmp",
                                cb_list[-1][1],
                            )
                        )

                    cb_list: list = cb_list[:-1]

                    for _ in range(3):
                        self.main_window.grid.remove_column(1)
                    self.main_window.update_history(cb_list)
                    self.main_window._set_grid()

            self.close()

        except GLib.Error as e:
            print("Erro ao ler da área de transferência:", e.message)
            self.on_load_clipboard(has_window)
        except Exception as e:
            print("Erro inesperado:", e)
