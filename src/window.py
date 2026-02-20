# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import weakref
from gettext import gettext as _
from typing import Any

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from serigy.define import RESOURCE_PATH
from serigy.overlay_button import OverlayButton
from serigy.settings import Settings


class SlotItem(GObject.Object):
    """Represents a single clipboard slot item for GridView binding."""

    index = GObject.Property(type=int, default=0, nick="Slot index")
    label = GObject.Property(type=str, default="", nick="Slot text content")
    filename = GObject.Property(type=str, default="", nick="Cached image filename")

    def __init__(self, index: int = 0, label: str = "", filename: str = "") -> None:
        super().__init__()
        self.props.index = index
        self.props.label = label
        self.props.filename = filename


@Gtk.Template(resource_path=f"{RESOURCE_PATH}/gtk/window.ui")
class SerigyWindow(Adw.ApplicationWindow):
    __gtype_name__ = "SerigyWindow"

    # Child widgets
    grid_view: Gtk.GridView = Gtk.Template.Child()
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

        self.set_hide_on_close(True)
        self._update_incognito_style()

        self._pending_removals = 0
        self._slot_store = Gio.ListStore.new(SlotItem)
        self._selection_model = Gtk.NoSelection.new(model=self._slot_store)
        self._factory = Gtk.SignalListItemFactory()
        self._factory.connect("bind", self._on_slot_bind)
        self._factory.connect("unbind", self._on_slot_unbind)

        self.grid_view.set_model(self._selection_model)
        self.grid_view.set_factory(self._factory)
        self.grid_view.remove_css_class("view")
        self.grid_view.set_max_columns(3)
        self.grid_view.set_min_columns(1)

        self._set_grid()

    def _update_incognito_style(self):
        if Settings.get().incognito_mode:
            self.add_css_class("incognito")
        else:
            self.remove_css_class("incognito")

    def _cleanup_grid(self):
        """Clear model items so GridView unbind handles cleanup."""
        self._slot_store.remove_all()

    def _on_slot_bind(self, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        """Bind slot data to OverlayButton widget."""
        slot: SlotItem = list_item.get_item()

        button = OverlayButton(
            parent=self,
            id=str(slot.props.index),
            label=slot.props.label,
            filename=slot.props.filename,
        )
        button.set_margin_top(3)
        button.set_margin_bottom(3)
        button.set_margin_start(3)
        button.set_margin_end(3)
        button.set_halign(Gtk.Align.FILL)
        list_item.set_child(button)

    def _on_slot_unbind(self, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        """Unbind and cleanup OverlayButton widget."""
        child = list_item.get_child()
        if isinstance(child, OverlayButton):
            child.cleanup()
            list_item.set_child(None)

    def mark_pending_removal(self) -> None:
        self._pending_removals += 1

    def resolve_pending_removal(self) -> None:
        if self._pending_removals > 0:
            self._pending_removals -= 1

        if self._pending_removals == 0:
            self.arrange_slots()

    def refresh_grid(self) -> None:
        """Refresh the grid layout by re-initializing it."""
        self._set_grid()

    def _set_grid(self, do_sort: bool = False) -> None:
        """Initialize or refresh the slot grid view."""
        self._cleanup_grid()
        self.stack.props.visible_child_name = "loading_page"

        _slots: list[list[str]] = Settings.get().slots.unpack()

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

        self._pending_removals = 0

        for idx, row in enumerate(_slots):
            self._slot_store.append(
                SlotItem(index=idx, label=row[0], filename=row[1])
            )

        self.stack.props.visible_child_name = "slots_page"

        self.empty_button.props.sensitive = any(
            len(i) for sub in _slots for i in sub
        )

        return None

    def update_slots(self, new_slots: list[list[str]]) -> None:
        """Update slots in GSettings and refresh UI."""
        # Ensure all values are valid strings
        sanitized_slots: list[list[str]] = [
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

    def _slots_adjustment(self, slots: list[list[str]], slots_difference: int) -> list[list[str]]:
        """Adjust slot count to match settings value."""
        if len(slots) <= Settings.get().number_slots_value:
            for _ in range(Settings.get().number_slots_value - len(slots)):
                slots.append(["", "", "", ""])
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
                    new_slots.append(["", "", "", ""])

            # Ensure correct number of slots
            while len(new_slots) < _number_slots:
                new_slots.append(["", "", "", ""])
            new_slots = new_slots[:_number_slots]

            win.update_slots(new_slots)
            win.refresh_grid()

        alert_dialog.choose(self, None, empty_slots)
        return None

    def arrange_slots(self, *args: Any) -> None:
        """Re-arrange slots by moving occupied ones to front and empty to back."""
        self._set_grid(do_sort=True)
