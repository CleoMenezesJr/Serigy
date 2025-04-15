# Copyright 2024 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import os
from datetime import datetime as dt
from threading import Thread

from gi.repository import Adw, Gdk, GdkPixbuf, GLib, GObject, Gtk

from .settings import Settings


@Gtk.Template(
    resource_path="/io/github/cleomenezesjr/Serigy/gtk/overlay-button.ui"
)
class OverlayButton(Gtk.Overlay):
    __gtype_name__ = "OverlayButton"

    # Child widgets
    label: Gtk.Label = Gtk.Template.Child()
    main_button: Gtk.Button = Gtk.Template.Child()
    remove_button: Gtk.Button = Gtk.Template.Child()
    revealer_crossfade: Gtk.Revealer = Gtk.Template.Child()
    image: Gtk.Picture = Gtk.Template.Child()

    def __init__(
        self,
        parent,
        id: str,
        label: str = None,
        filename: str = None,
        **kwargs
    ):
        super().__init__(**kwargs)

        # Initial state
        self.parent = parent
        self.remove_button.set_name(id)
        self.set_name(id)
        self.revealer_crossfade.set_reveal_child(True)
        self.toast = Adw.Toast(title=_("Copied to clipboard"), timeout=1)

        if label:
            self.label.set_text(label)
            self.main_button.connect(
                "clicked", self.copy_text_to_clipboard, label
            )
            self.remove_button.add_css_class("flat")
        elif filename:
            self.image.set_visible(True)
            self.remove_button.add_css_class("osd")

            try:
                file_path = os.path.join(
                    GLib.get_user_cache_dir(), "tmp", filename
                )
                texture = Gdk.Texture.new_from_filename(file_path)
                self.main_button.connect(
                    "clicked",
                    lambda widget: Thread(
                        target=self.copy_image_to_clipboard, args=[texture]
                    ).start(),
                )
            except GLib.Error:
                pass
                # logging.exception("Could not load exception")
            else:
                GLib.idle_add(self.image.set_paintable, texture)
        else:
            self.revealer_crossfade.set_reveal_child(False)

    def copy_text_to_clipboard(self, widget: Gtk.Button, text: str) -> None:
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set_content(Gdk.ContentProvider.new_for_value(text))
        self.parent.toast_overlay.add_toast(self.toast)

        return None

    def copy_image_to_clipboard(self, content: Gdk.Texture) -> None:
        self.parent.stack.props.visible_child_name = "loading_page"
        clipboard = Gdk.Display.get_default().get_clipboard()
        gbytes = content.save_to_png_bytes()
        clipboard.set_content(
            Gdk.ContentProvider.new_for_bytes("image/png", gbytes)
        )
        self.parent.toast_overlay.add_toast(self.toast)
        self.parent.stack.props.visible_child_name = "slots_page"

        return None

    @Gtk.Template.Callback()
    def remove(self, widget: Gtk.Button) -> None:
        self.revealer_crossfade.set_reveal_child(False)
        _index: int = int(widget.get_name())
        _slots: list = Settings.get().slots.unpack()

        if _slots[_index][1]:
            os.remove(
                os.path.join(
                    GLib.get_user_cache_dir(), "tmp", _slots[_index][1]
                )
            )

        _slots[_index] = ["", "", ""]

        self.parent.update_slots(_slots)

        return None
