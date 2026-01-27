# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import shutil
import time
import weakref

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from serigy.content_type import detect as detect_content_type
from serigy.define import RESOURCE_PATH
from serigy.settings import Settings


@Gtk.Template(resource_path=f"{RESOURCE_PATH}/gtk/overlay-button.ui")
class OverlayButton(Gtk.Overlay):
    __gtype_name__ = "OverlayButton"

    # Child widgets
    label: Gtk.Label = Gtk.Template.Child()
    main_button: Gtk.Button = Gtk.Template.Child()
    revealer_crossfade: Gtk.Revealer = Gtk.Template.Child()
    image: Gtk.Picture = Gtk.Template.Child()

    # Header widgets
    type_icon: Gtk.Image = Gtk.Template.Child()
    info_label: Gtk.Label = Gtk.Template.Child()
    options_button: Gtk.MenuButton = Gtk.Template.Child()
    delete_button: Gtk.Button = Gtk.Template.Child()
    pin_button: Gtk.ToggleButton = Gtk.Template.Child()

    def __init__(
        self,
        parent,
        id: str,
        label: str = None,
        filename: str = None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        # Initial state
        self.parent = weakref.proxy(parent)
        self.slot_id = int(id)
        self.text_content = label

        # Setup buttons
        self.delete_button.set_name(id)
        self.set_name(id)

        self.revealer_crossfade.set_reveal_child(True)
        self.toast = Adw.Toast(title=_("Copied to clipboard"), timeout=1)

        # Connect signals
        self._delete_handler = self.delete_button.connect(
            "clicked", self.remove
        )
        self._pin_handler = self.pin_button.connect(
            "toggled", self._on_pin_toggled
        )

        # Setup actions for the menu
        self._setup_actions()

        # Track pending removals for auto-arrange
        self._pending_removal = False

        # Check if pinned and timestamp
        slots = Settings.get().slots.unpack()
        slot_data = slots[self.slot_id]

        # Handle 4-element slot [text, file, favorites, timestamp]
        is_pinned = len(slot_data) > 2 and slot_data[2] == "pinned"
        timestamp = slot_data[3] if len(slot_data) > 3 else ""

        self.pin_button.set_active(is_pinned)

        # Determine type and update info
        if label:
            # Detect content type intelligently
            content_type = detect_content_type(label)
            self.type_icon.set_from_icon_name(content_type.icon)
            self.label.set_text(label)
            self._main_btn_handler = self.main_button.connect(
                "clicked", self.copy_text_to_clipboard, label
            )
            self._create_text_menu()
            self._update_info_label(
                _(content_type.type_id.capitalize()), timestamp
            )
        elif filename:
            self.image.set_visible(True)
            self.filename = filename
            self.type_icon.set_from_icon_name("image-x-generic-symbolic")

            try:
                file_path = os.path.join(
                    GLib.get_user_cache_dir(), "tmp", filename
                )
                self.file_path = file_path
                texture = Gdk.Texture.new_from_filename(file_path)
                self._main_btn_handler = self.main_button.connect(
                    "clicked", self._copy_image_sync, texture
                )
            except GLib.Error:
                pass
            else:
                GLib.idle_add(self.image.set_paintable, texture)

            self._create_image_menu()
            self._update_info_label(_("Image"), timestamp)
        else:
            self.revealer_crossfade.set_reveal_child(False)

        # Remove 'osd' class if present (cleanup from old style)
        self.delete_button.add_css_class("flat")

    def _get_relative_time(self, timestamp_str: str) -> str:
        if not timestamp_str:
            return ""

        try:
            ts = int(timestamp_str)
            diff = int(time.time()) - ts

            if diff < 60:
                return _("Just now")
            elif diff < 3600:
                return _("{} min ago").format(diff // 60)
            elif diff < 86400:
                return _("{} hr ago").format(diff // 3600)
            else:
                return _("{} days ago").format(diff // 86400)
        except ValueError:
            return ""

    def _update_info_label(self, type_str: str, timestamp_str: str):
        rel_time = self._get_relative_time(timestamp_str)
        if rel_time:
            self.info_label.set_label(f"{type_str} • {rel_time}")
        else:
            self.info_label.set_label(type_str)

    def _setup_actions(self):
        action_group = Gio.SimpleActionGroup()

        # Copy formatting actions (text only)
        for action_name in [
            "copy-uppercase",
            "copy-lowercase",
            "copy-titlecase",
        ]:
            action = Gio.SimpleAction.new(action_name, None)
            method_name = f"_on_{action_name.replace('-', '_')}"
            action.connect("activate", getattr(self, method_name))
            action_group.add_action(action)

        # Save action (image only)
        save_action = Gio.SimpleAction.new("save", None)
        save_action.connect("activate", self._on_save_image)
        action_group.add_action(save_action)

        self.action_group = action_group
        self.insert_action_group("slot", action_group)

    def _create_text_menu(self):
        menu = Gio.Menu()

        copy_submenu = Gio.Menu()
        copy_submenu.append(_("UPPERCASE"), "slot.copy-uppercase")
        copy_submenu.append(_("lowercase"), "slot.copy-lowercase")
        copy_submenu.append(_("Title Case"), "slot.copy-titlecase")

        menu.append_submenu(_("Copy as..."), copy_submenu)
        self.options_button.set_menu_model(menu)

    def _create_image_menu(self):
        menu = Gio.Menu()
        menu.append(_("Save..."), "slot.save")
        self.options_button.set_menu_model(menu)

    def _on_pin_toggled(self, button):
        slots = Settings.get().slots.unpack()
        is_active = button.get_active()
        slots[self.slot_id][2] = "pinned" if is_active else ""
        self.parent.update_slots(slots)

    def _on_save_image(self, action, param):
        if not hasattr(self, "file_path"):
            return
        dialog = Gtk.FileDialog()
        dialog.set_initial_name(self.filename)
        dialog.save(self.parent, None, self._on_save_finish)

    def _on_save_finish(self, dialog, result):
        try:
            file = dialog.save_finish(result)
            if file:
                shutil.copy2(self.file_path, file.get_path())
                self.parent.toast_overlay.add_toast(
                    Adw.Toast(title=_("Image saved"), timeout=1)
                )
        except GLib.Error:
            pass

    def _on_copy_uppercase(self, action, param):
        if self.text_content:
            self._copy_formatted(self.text_content.upper())

    def _on_copy_lowercase(self, action, param):
        if self.text_content:
            self._copy_formatted(self.text_content.lower())

    def _on_copy_titlecase(self, action, param):
        if self.text_content:
            self._copy_formatted(self.text_content.title())

    def _copy_to_clipboard(self, content, show_toast: bool = True) -> None:
        clipboard = Gdk.Display.get_default().get_clipboard()
        if isinstance(content, Gdk.Texture):
            gbytes = content.save_to_png_bytes()
            clipboard.set_content(
                Gdk.ContentProvider.new_for_bytes("image/png", gbytes)
            )

    def cleanup(self):
        if hasattr(self, "action_group") and self.action_group:
            self.action_group = None
        self.insert_action_group("slot", None)

        if hasattr(self, "_main_btn_handler") and self._main_btn_handler:
            try:
                self.main_button.disconnect(self._main_btn_handler)
            except Exception:
                pass

        if hasattr(self, "_delete_handler") and self._delete_handler:
            try:
                self.delete_button.disconnect(self._delete_handler)
            except Exception:
                pass

        if hasattr(self, "_pin_handler") and self._pin_handler:
            try:
                self.pin_button.disconnect(self._pin_handler)
            except Exception:
                pass

        self.parent = None

    def _copy_formatted(self, text: str):
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set_content(Gdk.ContentProvider.new_for_value(text))
        self.parent.toast_overlay.add_toast(
            Adw.Toast(title=_("Copied to clipboard"), timeout=1)
        )

    def copy_text_to_clipboard(self, widget: Gtk.Button, text: str) -> None:
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set_content(Gdk.ContentProvider.new_for_value(text))
        self.parent.toast_overlay.add_toast(
            Adw.Toast(title=_("Copied to clipboard"), timeout=1)
        )

    def _copy_image_sync(
        self, widget: Gtk.Button, texture: Gdk.Texture
    ) -> None:
        self.parent.stack.props.visible_child_name = "loading_page"
        self._copy_to_clipboard(texture)
        self.parent.stack.props.visible_child_name = "slots_page"

    def remove(self, widget: Gtk.Button) -> None:
        self.revealer_crossfade.set_reveal_child(False)
        _index: int = int(widget.get_name())
        _slots: list = Settings.get().slots.unpack()

        if _slots[_index][1]:
            file_path = os.path.join(
                GLib.get_user_cache_dir(), "tmp", _slots[_index][1]
            )
            if os.path.exists(file_path):
                os.remove(file_path)

        _slots[_index] = ["", "", ""]

        self.parent.update_slots(_slots)

        if Settings.get().auto_arrange:
            self._pending_removal = True
            self.revealer_crossfade.connect(
                "notify::child-revealed", self._on_reveal_done
            )

    def _on_reveal_done(self, revealer, pspec):
        if not revealer.get_child_revealed() and self._pending_removal:
            self._pending_removal = False
            revealer.disconnect_by_func(self._on_reveal_done)

            for child in self.parent.grid:
                if isinstance(child, OverlayButton) and child._pending_removal:
                    return

            self.parent.arrange_slots()
