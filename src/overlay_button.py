# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os
import shutil
import time
import weakref
from gettext import gettext as _
from typing import TYPE_CHECKING, Any

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from serigy.content_type import detect as detect_content_type
from serigy.define import RESOURCE_PATH
from serigy.settings import Settings

if TYPE_CHECKING:
    from serigy.window import SerigyWindow


@Gtk.Template(resource_path=f"{RESOURCE_PATH}/gtk/overlay-button.ui")
class OverlayButton(Gtk.Overlay):
    __gtype_name__ = "OverlayButton"

    # Child widgets
    label: Gtk.Label = Gtk.Template.Child()
    main_button: Gtk.Button = Gtk.Template.Child()
    revealer_crossfade: Gtk.Revealer = Gtk.Template.Child()
    image: Gtk.Picture = Gtk.Template.Child()

    # Header widgets
    header_scrim: Gtk.Box = Gtk.Template.Child()
    type_icon: Gtk.Image = Gtk.Template.Child()
    info_label: Gtk.Label = Gtk.Template.Child()
    options_button: Gtk.MenuButton = Gtk.Template.Child()
    delete_button: Gtk.Button = Gtk.Template.Child()
    pin_button: Gtk.ToggleButton = Gtk.Template.Child()

    def __init__(
        self,
        parent: "SerigyWindow",
        id: str,
        label: str | None = None,
        filename: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        # Store parent as weakref for safe lifecycle management
        self._parent_ref: weakref.ref["SerigyWindow"] = weakref.ref(parent)
        self.slot_id: int = int(id)
        self.text_content: str | None = label

        # Setup buttons
        self.delete_button.set_name(id)
        self.set_name(id)

        self.revealer_crossfade.set_reveal_child(True)

        # Connect signals
        self._delete_handler: int | None = self.delete_button.connect(
            "clicked", self.remove
        )
        self._pin_handler: int | None = self.pin_button.connect(
            "toggled", self._on_pin_toggled
        )

        # Setup actions for the menu
        self._setup_actions()

        # Track pending removals for auto-arrange
        self._pending_removal: bool = False

        # Prepare filename and file_path for image slots
        self.filename: str | None = None
        self.file_path: str | None = None
        self._main_btn_handler: int | None = None

        # Check if pinned and timestamp
        slots = Settings.get().slots.unpack()
        slot_data = slots[self.slot_id]

        # Handle 4-element slot [text, file, favorites, timestamp]
        is_pinned = len(slot_data) > 2 and slot_data[2] == "pinned"
        timestamp = slot_data[3] if len(slot_data) > 3 else ""

        self.pin_button.set_active(is_pinned)
        self._update_pin_tooltip(is_pinned)

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
            self._update_info_label(content_type.name, timestamp)
        elif filename:
            self.image.set_visible(True)
            self.header_scrim.set_visible(True)
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

    @property
    def parent(self) -> "SerigyWindow | None":
        """Safe access to parent window via weak reference."""
        return self._parent_ref()

    def _get_relative_time(self, timestamp_str: str) -> str:
        """Convert timestamp to human-readable relative time string."""
        if not timestamp_str:
            return ""

        try:
            ts: int = int(timestamp_str)
            diff: int = int(time.time()) - ts

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

    def _update_info_label(self, type_str: str, timestamp_str: str) -> None:
        """Update slot info label with type and relative time."""
        rel_time: str = self._get_relative_time(timestamp_str)
        if rel_time:
            self.info_label.set_label(f"{type_str} • {rel_time}")
        else:
            self.info_label.set_label(type_str)

    def _setup_actions(self) -> None:
        """Setup slot context menu actions."""
        action_group: Gio.SimpleActionGroup = Gio.SimpleActionGroup()

        # Copy formatting actions (text only)
        for action_name in [
            "copy-uppercase",
            "copy-lowercase",
            "copy-titlecase",
        ]:
            action: Gio.SimpleAction = Gio.SimpleAction.new(action_name, None)
            method_name: str = f"_on_{action_name.replace('-', '_')}"
            action.connect("activate", getattr(self, method_name))
            action_group.add_action(action)

        # Save action (image only)
        save_action: Gio.SimpleAction = Gio.SimpleAction.new("save", None)
        save_action.connect("activate", self._on_save_image)
        action_group.add_action(save_action)

        self.action_group = action_group
        self.insert_action_group("slot", action_group)

    def _create_text_menu(self) -> None:
        """Create context menu for text slots."""
        menu: Gio.Menu = Gio.Menu()

        copy_submenu: Gio.Menu = Gio.Menu()
        copy_submenu.append(_("UPPERCASE"), "slot.copy-uppercase")
        copy_submenu.append(_("lowercase"), "slot.copy-lowercase")
        copy_submenu.append(_("Title Case"), "slot.copy-titlecase")

        menu.append_submenu(_("Copy as..."), copy_submenu)
        self.options_button.set_menu_model(menu)

    def _create_image_menu(self) -> None:
        """Create context menu for image slots."""
        menu: Gio.Menu = Gio.Menu()
        menu.append(_("Save..."), "slot.save")
        self.options_button.set_menu_model(menu)

    def _update_pin_tooltip(self, is_pinned: bool) -> None:
        """Update pin button tooltip based on current state."""
        tooltip = _("Unpin") if is_pinned else _("Pin")
        self.pin_button.set_tooltip_text(tooltip)

    def _on_pin_toggled(self, button: Gtk.ToggleButton) -> None:
        """Handle pin button toggle state change."""
        slots: list[list[str]] = Settings.get().slots.unpack()
        is_active: bool = button.get_active()
        slots[self.slot_id][2] = "pinned" if is_active else ""
        parent = self.parent
        if parent is not None:
            parent.update_slots(slots)
        self._update_pin_tooltip(is_active)

    def _on_save_image(self, action: Gio.SimpleAction, param: GLib.Variant | None) -> None:
        """Handle save image action from context menu."""
        if not hasattr(self, "file_path") or not self.file_path:
            return
        parent = self.parent
        if parent is None:
            return
        dialog: Gtk.FileDialog = Gtk.FileDialog()
        dialog.set_initial_name(self.filename)
        dialog.save(parent, None, self._on_save_finish)

    def _on_save_finish(self, dialog: Gtk.FileDialog, result: Gio.Task) -> None:
        """Handle file save dialog result."""
        try:
            file = dialog.save_finish(result)
            if file:
                shutil.copy2(self.file_path, file.get_path())
                parent = self.parent
                if parent is not None:
                    parent.toast_overlay.add_toast(
                        Adw.Toast(title=_("Image saved"), timeout=1)
                    )
        except GLib.Error:
            pass

    def _on_copy_uppercase(self, action: Gio.SimpleAction, param: GLib.Variant | None) -> None:
        """Copy text in uppercase."""
        if self.text_content:
            self._copy_formatted(self.text_content.upper())

    def _on_copy_lowercase(self, action: Gio.SimpleAction, param: GLib.Variant | None) -> None:
        """Copy text in lowercase."""
        if self.text_content:
            self._copy_formatted(self.text_content.lower())

    def _on_copy_titlecase(self, action: Gio.SimpleAction, param: GLib.Variant | None) -> None:
        """Copy text in title case."""
        if self.text_content:
            self._copy_formatted(self.text_content.title())

    def _copy_to_clipboard(self, content: Gdk.Texture, show_toast: bool = True) -> None:
        """Copy texture content to system clipboard."""
        clipboard: Gdk.Clipboard = Gdk.Display.get_default().get_clipboard()
        if isinstance(content, Gdk.Texture):
            gbytes: GLib.Bytes = content.save_to_png_bytes()
            clipboard.set_content(
                Gdk.ContentProvider.new_for_bytes("image/png", gbytes)
            )

    def cleanup(self) -> None:
        """Clean up signal handlers and state before widget destruction."""
        if hasattr(self, "action_group") and self.action_group:
            self.action_group = None
        self.insert_action_group("slot", None)

        if hasattr(self, "_main_btn_handler") and self._main_btn_handler:
            try:
                self.main_button.disconnect(self._main_btn_handler)
            except Exception as e:
                logging.warning("Failed to disconnect main_button: %s", e)

        if hasattr(self, "_delete_handler") and self._delete_handler:
            try:
                self.delete_button.disconnect(self._delete_handler)
            except Exception as e:
                logging.warning("Failed to disconnect delete_button: %s", e)

        if hasattr(self, "_pin_handler") and self._pin_handler:
            try:
                self.pin_button.disconnect(self._pin_handler)
            except Exception as e:
                logging.warning("Failed to disconnect pin_button: %s", e)

        self._parent_ref = None

    def _copy_formatted(self, text: str) -> None:
        """Copy text to clipboard with user feedback."""
        clipboard: Gdk.Clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set_content(Gdk.ContentProvider.new_for_value(text))
        parent = self.parent
        if parent is not None:
            parent.toast_overlay.add_toast(
                Adw.Toast(title=_("Copied to clipboard"), timeout=1)
            )

    def copy_text_to_clipboard(self, widget: Gtk.Button, text: str) -> None:
        """Copy slot text to clipboard."""
        self._copy_formatted(text)

    def _copy_image_sync(self, widget: Gtk.Button, texture: Gdk.Texture) -> None:
        """Copy image to clipboard with UI feedback."""
        parent = self.parent
        if parent is not None:
            parent.stack.props.visible_child_name = "loading_page"
        self._copy_to_clipboard(texture)
        if parent is not None:
            parent.stack.props.visible_child_name = "slots_page"
            parent.toast_overlay.add_toast(
                Adw.Toast(title=_("Copied to clipboard"), timeout=1)
            )

    def remove(self, widget: Gtk.Button) -> None:
        """Remove this slot (mark as empty and trigger auto-arrange if enabled)."""
        self.revealer_crossfade.set_reveal_child(False)
        _index: int = int(widget.get_name())
        _slots: list[list[str]] = Settings.get().slots.unpack()

        if _slots[_index][1]:
            file_path: str = os.path.join(
                GLib.get_user_cache_dir(), "tmp", _slots[_index][1]
            )
            if os.path.exists(file_path):
                os.remove(file_path)

        _slots[_index] = ["", "", "", ""]

        parent = self.parent
        if parent is not None:
            parent.update_slots(_slots)

        if Settings.get().auto_arrange:
            self._pending_removal = True
            parent_ref = self.parent
            if parent_ref is not None:
                parent_ref.mark_pending_removal()
            self.revealer_crossfade.connect(
                "notify::child-revealed", self._on_reveal_done
            )

    def _on_reveal_done(self, revealer: Gtk.Revealer, pspec: GObject.ParamSpec) -> None:
        """Trigger arrange after slot removal reveal animation."""
        if not revealer.get_child_revealed() and self._pending_removal:
            self._pending_removal = False
            revealer.disconnect_by_func(self._on_reveal_done)
            parent = self.parent
            if parent is not None:
                parent.resolve_pending_removal()
