# Copyright 2024 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import shutil
from gettext import gettext as _

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

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
    pin_icon: Gtk.Image = Gtk.Template.Child()

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
        self.slot_id = int(id)
        self.text_content = label
        self.remove_button.set_name(id)
        self.set_name(id)
        self.revealer_crossfade.set_reveal_child(True)
        self.toast = Adw.Toast(title=_("Copied to clipboard"), timeout=1)

        # Setup actions
        self._setup_actions()

        # Setup right-click gesture
        self.gesture_click = Gtk.GestureClick(button=3)
        self.gesture_click.connect("pressed", self._on_right_click)
        self.main_button.add_controller(self.gesture_click)

        # Check if pinned
        slots = Settings.get().slots.unpack()
        if slots[self.slot_id][2] == "pinned":
            self.pin_icon.set_visible(True)

        if label:
            self.label.set_text(label)
            self.main_button.connect(
                "clicked", self.copy_text_to_clipboard, label
            )
            self.remove_button.add_css_class("flat")
            self._create_text_popover()
        elif filename:
            self.image.set_visible(True)
            self.remove_button.add_css_class("osd")
            self.filename = filename

            try:
                file_path = os.path.join(
                    GLib.get_user_cache_dir(), "tmp", filename
                )
                self.file_path = file_path
                texture = Gdk.Texture.new_from_filename(file_path)
                self.main_button.connect(
                    "clicked", self._copy_image_sync, texture
                )
            except GLib.Error:
                pass
            else:
                GLib.idle_add(self.image.set_paintable, texture)
            self._create_image_popover()
        else:
            self.revealer_crossfade.set_reveal_child(False)

    def _setup_actions(self):
        action_group = Gio.SimpleActionGroup()

        # Pin action
        pin_action = Gio.SimpleAction.new("pin", None)
        pin_action.connect("activate", self._on_pin)
        action_group.add_action(pin_action)

        # Copy formatting actions (text only)
        uppercase_action = Gio.SimpleAction.new("copy-uppercase", None)
        uppercase_action.connect("activate", self._on_copy_uppercase)
        action_group.add_action(uppercase_action)

        lowercase_action = Gio.SimpleAction.new("copy-lowercase", None)
        lowercase_action.connect("activate", self._on_copy_lowercase)
        action_group.add_action(lowercase_action)

        titlecase_action = Gio.SimpleAction.new("copy-titlecase", None)
        titlecase_action.connect("activate", self._on_copy_titlecase)
        action_group.add_action(titlecase_action)

        # Save action (image only)
        save_action = Gio.SimpleAction.new("save", None)
        save_action.connect("activate", self._on_save_image)
        action_group.add_action(save_action)

        self.insert_action_group("slot", action_group)

    def _create_text_popover(self):
        """Create popover menu for text slots."""
        menu = Gio.Menu()
        
        pin_section = Gio.Menu()
        pin_section.append(_("Pin"), "slot.pin")
        menu.append_section(None, pin_section)
        
        copy_submenu = Gio.Menu()
        copy_submenu.append(_("UPPERCASE"), "slot.copy-uppercase")
        copy_submenu.append(_("lowercase"), "slot.copy-lowercase")
        copy_submenu.append(_("Title Case"), "slot.copy-titlecase")
        
        copy_section = Gio.Menu()
        copy_section.append_submenu(_("Copy as…"), copy_submenu)
        menu.append_section(None, copy_section)
        
        self.popover_menu = Gtk.PopoverMenu.new_from_model(menu)
        self.popover_menu.set_parent(self.main_button)
        self.popover_menu.set_has_arrow(False)

    def _create_image_popover(self):
        """Create popover menu for image slots."""
        menu = Gio.Menu()
        
        pin_section = Gio.Menu()
        pin_section.append(_("Pin"), "slot.pin")
        menu.append_section(None, pin_section)
        
        save_section = Gio.Menu()
        save_section.append(_("Save…"), "slot.save")
        menu.append_section(None, save_section)
        
        self.popover_menu = Gtk.PopoverMenu.new_from_model(menu)
        self.popover_menu.set_parent(self.main_button)
        self.popover_menu.set_has_arrow(False)

    def _on_right_click(self, gesture, n_press, x, y):
        if not hasattr(self, 'popover_menu'):
            return
        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        self.popover_menu.set_pointing_to(rect)
        self.popover_menu.popup()

    def _on_pin(self, action, param):
        slots = Settings.get().slots.unpack()
        is_pinned = slots[self.slot_id][2] == "pinned"
        slots[self.slot_id][2] = "" if is_pinned else "pinned"
        self.parent.update_slots(slots)
        self.pin_icon.set_visible(not is_pinned)

    def _on_save_image(self, action, param):
        """Open file chooser to save image."""
        if not hasattr(self, 'file_path'):
            return
        
        dialog = Gtk.FileDialog()
        dialog.set_initial_name(self.filename)
        dialog.save(self.parent, None, self._on_save_finish)

    def _on_save_finish(self, dialog, result):
        try:
            file = dialog.save_finish(result)
            if file:
                # Copy file to selected location
                import shutil
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

    def _skip_clipboard_monitor(self) -> None:
        """Tell clipboard monitor to ignore the next change."""
        app = self.parent.get_application()
        if app and hasattr(app, 'clipboard_monitor'):
            app.clipboard_monitor.skip_next_change()

    def _copy_to_clipboard(self, content, show_toast: bool = True) -> None:
        """Copy content to clipboard and optionally show toast."""
        self._skip_clipboard_monitor()
        clipboard = Gdk.Display.get_default().get_clipboard()
        
        if isinstance(content, Gdk.Texture):
            gbytes = content.save_to_png_bytes()
            clipboard.set_content(
                Gdk.ContentProvider.new_for_bytes("image/png", gbytes)
            )
        else:
            clipboard.set_content(Gdk.ContentProvider.new_for_value(content))
        
        if show_toast:
            self.parent.toast_overlay.add_toast(self.toast)

    def _copy_formatted(self, text: str):
        self._skip_clipboard_monitor()
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set_content(Gdk.ContentProvider.new_for_value(text))
        self.parent.toast_overlay.add_toast(
            Adw.Toast(title=_("Copied to clipboard"), timeout=1)
        )

    def copy_text_to_clipboard(self, widget: Gtk.Button, text: str) -> None:
        self._copy_to_clipboard(text)

    def _copy_image_sync(self, widget: Gtk.Button, texture: Gdk.Texture) -> None:
        self.parent.stack.props.visible_child_name = "loading_page"
        self._copy_to_clipboard(texture)
        self.parent.stack.props.visible_child_name = "slots_page"

    @Gtk.Template.Callback()
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
            self.parent.arrange_slots()

        return None
