# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import weakref
from gettext import gettext as _
from typing import Any

from gi.repository import Adw, Gio, GObject, Gtk

from serigy.define import RESOURCE_PATH
from serigy.image_store import remove_image
from serigy.overlay_button import OverlayButton
from serigy.settings import Settings
from serigy.slot_data import SlotData


class SlotItem(GObject.Object):
    """Represents a single clipboard slot item for GridView binding."""

    label = GObject.Property(type=str, default="", nick="Slot text content")
    filename = GObject.Property(
        type=str, default="", nick="Cached image filename"
    )
    uri = GObject.Property(type=str, default="", nick="Copied file URI")

    def __init__(
        self, label: str = "", filename: str = "", uri: str = ""
    ) -> None:
        super().__init__()
        self.props.label = label
        self.props.filename = filename
        self.props.uri = uri


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
        Settings.get().bind(
            "window-width",
            self,
            "default-width",
            Gio.SettingsBindFlags.DEFAULT,
        )
        Settings.get().bind(
            "window-height",
            self,
            "default-height",
            Gio.SettingsBindFlags.DEFAULT,
        )
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

    def _on_slot_bind(
        self, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem
    ) -> None:
        """Bind slot data to OverlayButton widget."""
        slot: SlotItem = list_item.get_item()

        button = OverlayButton(
            parent=self,
            list_item=list_item,
            label=slot.props.label,
            filename=slot.props.filename,
            uri=slot.props.uri,
        )
        button.set_halign(Gtk.Align.FILL)
        list_item.set_child(button)

        is_empty = (
            not slot.props.label
            and not slot.props.filename
            and not slot.props.uri
        )
        list_item.set_activatable(not is_empty)
        list_item.set_selectable(not is_empty)
        list_item.set_focusable(not is_empty)

    def _on_slot_unbind(
        self, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem
    ) -> None:
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

        _slots: list[SlotData] = Settings.get().slots

        if do_sort or Settings.get().auto_arrange:
            _slots = [s for s in _slots if not s.is_empty] + [
                s for s in _slots if s.is_empty
            ]
            self.update_slots(_slots)

        _number_slots: int = Settings.get().number_slots_value
        _slots_difference: int = len(_slots) - _number_slots

        if _slots_difference != 0:
            _slots = self._slots_adjustment(_slots, _slots_difference)
            self.update_slots(_slots)

        self._pending_removals = 0

        for row in _slots:
            self._slot_store.append(
                SlotItem(label=row.text, filename=row.filename, uri=row.uri)
            )

        self.stack.props.visible_child_name = "slots_page"

        self.empty_button.props.sensitive = any(not s.is_empty for s in _slots)

        return None

    def update_slots(self, new_slots: list[SlotData]) -> None:
        """Update slots in GSettings and refresh UI."""
        Settings.get().slots = new_slots

        self.empty_button.props.sensitive = any(
            not s.is_empty for s in new_slots
        )

        return None

    def _slots_adjustment(
        self, slots: list[SlotData], slots_difference: int
    ) -> list[SlotData]:
        """Adjust slot count to match settings value.

        When shrinking, drop empty slots first, then unpinned-occupied
        slots. Pinned slots are never dropped.
        """
        target = Settings.get().number_slots_value
        if len(slots) <= target:
            for _ in range(target - len(slots)):
                slots.append(SlotData())
        else:
            to_remove = len(slots) - target
            remaining = []
            dropped_images = []
            removed = 0
            for slot in slots:
                if removed < to_remove and not slot.is_pinned:
                    dropped_images.append(slot.filename)
                    removed += 1
                else:
                    remaining.append(slot)
            slots = remaining
            surviving = [slot.filename for slot in slots]
            for filename in dropped_images:
                remove_image(filename, surviving)
            while len(slots) < target:
                slots.append(SlotData())

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

            _slots = Settings.get().slots
            _number_slots = Settings.get().number_slots_value

            # Preserve pinned slots, empty the rest
            new_slots = []
            emptied_images = []
            for slot in _slots:
                if slot.is_pinned:
                    new_slots.append(slot)
                else:
                    emptied_images.append(slot.filename)
                    new_slots.append(SlotData())

            pinned_images = [slot.filename for slot in new_slots]
            for filename in emptied_images:
                remove_image(filename, pinned_images)

            # Ensure correct number of slots
            while len(new_slots) < _number_slots:
                new_slots.append(SlotData())
            new_slots = new_slots[:_number_slots]

            win.update_slots(new_slots)
            win.refresh_grid()

        alert_dialog.choose(self, None, empty_slots)
        return None

    def arrange_slots(self, *args: Any) -> None:
        """Move the occupied slots to the front and the empty ones back."""
        self._set_grid(do_sort=True)
