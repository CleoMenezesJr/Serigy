# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import weakref
from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, Gtk

from serigy.define import RESOURCE_PATH
from serigy.overlay_button import OverlayButton
from serigy.settings import Settings


@Gtk.Template(resource_path=f"{RESOURCE_PATH}/gtk/window.ui")
class SerigyWindow(Adw.ApplicationWindow):
    __gtype_name__ = "SerigyWindow"

    # Child widgets
    grid: Gtk.Grid = Gtk.Template.Child()
    stack: Gtk.Stack = Gtk.Template.Child()
    toast_overlay: Adw.ToastOverlay = Gtk.Template.Child()
    empty_button: Gtk.Button = Gtk.Template.Child()
    setup_button: Gtk.Button = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Initial state
        self._empty_btn_handler = self.empty_button.connect(
            "clicked", self.alert_dialog_empty_slots
        )

        # Use weakref in callback to avoid circular reference
        weak_self = weakref.ref(self)

        def on_number_slots_changed(settings, key):
            obj = weak_self()
            if obj is not None:
                obj.arrange_slots()

        def on_incognito_changed(settings, key):
            obj = weak_self()
            if obj is not None:
                obj._update_incognito_style()

        self._settings_handler_id = Settings.get().connect(
            "changed::number-slots", on_number_slots_changed
        )
        self._incognito_handler_id = Settings.get().connect(
            "changed::incognito-mode", on_incognito_changed
        )

        self.set_hide_on_close(False)
        self._update_incognito_style()

        self._set_grid()

    def _update_incognito_style(self):
        if Settings.get().incognito_mode:
            self.add_css_class("incognito")
        else:
            self.remove_css_class("incognito")

    def do_close_request(self):
        self._manual_cleanup()
        self.destroy()
        return True

    def _manual_cleanup(self):
        """Clean up signal handlers and children to prevent memory leaks."""
        # Disconnect Settings signal handler
        if hasattr(self, "_settings_handler_id") and self._settings_handler_id:
            Settings.get().disconnect(self._settings_handler_id)
            self._settings_handler_id = None

        # Disconnect internal signals
        if hasattr(self, "_empty_btn_handler") and self._empty_btn_handler:
            self.empty_button.disconnect(self._empty_btn_handler)
            self._empty_btn_handler = None

        # Cleanup grid children
        if hasattr(self, "grid"):
            while True:
                child = self.grid.get_first_child()
                if child is None:
                    break
                if isinstance(child, OverlayButton):
                    child.cleanup()
                self.grid.remove(child)

    def _set_grid(self, do_sort: bool = False) -> None:
        self.stack.props.visible_child_name = "loading_page"

        # Properly destroy all existing children to prevent memory leaks
        while True:
            child = self.grid.get_first_child()
            if child is None:
                break
            if isinstance(child, OverlayButton):
                child.cleanup()
            self.grid.remove(child)

        row_idx: int = 1
        total_columns: int = 1
        _slots = Settings.get().slots.unpack()

        if do_sort or Settings.get().auto_arrange:
            _slots: list = [sub for sub in _slots if any(sub)] + [
                sub for sub in _slots if not any(sub)
            ]
            self.update_slots(_slots)

        _number_slots: int = Settings.get().number_slots_value
        _slots_difference: int = len(_slots) - _number_slots

        if _slots_difference != 0:
            _slots: list = self._slots_adjustment(_slots, _slots_difference)
            self.update_slots(_slots)

        for idx, row in enumerate(_slots):
            button = OverlayButton(
                parent=self, id=str(idx), label=row[0], filename=row[1]
            )
            self.grid.attach(button, row_idx, total_columns, 1, 1)

            if row_idx == 3:
                row_idx = 1
                total_columns += 1

                continue

            row_idx += 1

        self.stack.props.visible_child_name = "slots_page"

        self.empty_button.props.sensitive = any(
            len(i) for sub in _slots for i in sub
        )

        return None

    def update_slots(self, new_slots: list) -> None:
        # Ensure all values are valid strings
        sanitized_slots = [
            [str(x) if x is not None else "" for x in states]
            for states in new_slots
        ]

        variant_array = GLib.Variant.new_array(
            GLib.VariantType("as"),
            [
                GLib.Variant.new_array(
                    GLib.VariantType("s"),
                    [GLib.Variant.new_string(x) for x in states],
                )
                for states in sanitized_slots
            ],
        )

        Settings.get().slots = variant_array

        self.empty_button.props.sensitive = any(
            len(i) for sub in new_slots for i in sub
        )

        return None

    def _slots_adjustment(self, slots: list, slots_difference: int) -> list:
        if len(slots) <= Settings.get().number_slots_value:
            for _ in range(Settings.get().number_slots_value - len(slots)):
                slots.append(["", "", ""])
        else:
            slots = slots[:-slots_difference]

        return slots

    def alert_dialog_empty_slots(self, *_args: tuple) -> None:
        alert_dialog = Adw.AlertDialog(
            heading=_("Empty slots?"),
            body=_("All information will be erased. Do you want to continue?"),
            close_response="cancel",
        )

        alert_dialog.add_response("cancel", _("Cancel"))
        alert_dialog.add_response("empty", _("Empty"))

        alert_dialog.set_response_appearance(
            "empty", Adw.ResponseAppearance.DESTRUCTIVE
        )

        win = self

        def empty_slots(alert_dialog: Adw.AlertDialog, task: Gio.Task) -> None:
            response = alert_dialog.choose_finish(task)
            if response == "cancel":
                return None

            _slots = Settings.get().slots.unpack()
            _number_slots = Settings.get().number_slots_value

            # Preserve pinned slots, empty the rest
            new_slots = []
            for slot in _slots:
                if slot[2] == "pinned":
                    new_slots.append(slot)
                else:
                    new_slots.append(["", "", ""])

            # Ensure correct number of slots
            while len(new_slots) < _number_slots:
                new_slots.append(["", "", ""])
            new_slots = new_slots[:_number_slots]

            win.update_slots(new_slots)

            for _i in range(3):
                win.grid.remove_column(1)
            win._set_grid()

        alert_dialog.choose(self, None, empty_slots)
        return None

    def arrange_slots(self, *args: tuple) -> None:
        for _i in range(3):
            self.grid.remove_column(1)
        self._set_grid(do_sort=True)
