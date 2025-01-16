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

from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango

from .overlay_button import OverlayButton


@Gtk.Template(
    resource_path="/page/codeberg/cleomenezesjr/Serigy/gtk/window.ui"
)
class SerigyWindow(Adw.ApplicationWindow):
    __gtype_name__ = "SerigyWindow"

    # Child widgets
    grid: Gtk.Grid = Gtk.Template.Child()
    stack: Gtk.Stack = Gtk.Template.Child()
    toast_overlay: Adw.ToastOverlay = Gtk.Template.Child()
    empty_button: Gtk.Button = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Initial state
        self.settings: Gio.Settings = Gio.Settings.new(
            "page.codeberg.cleomenezesjr.Serigy"
        )
        self.empty_button.connect("clicked", self.empty_slots_alert_dialog)

        self._set_grid()

    def _set_grid(self) -> None:
        self.stack.props.visible_child_name = "loading_page"

        row_idx: int = 1
        total_columns: int = 1
        history: GLib.Variant = self.settings.get_value(
            "pinned-clipboard-history"
        )

        for idx, row in enumerate(history):
            GLib.idle_add(
                self.grid.attach,
                OverlayButton(
                    parent=self, id=str(idx), label=row[0], filename=row[1]
                ),  # child
                row_idx,  # column
                total_columns,  # row
                1,  # width
                1,  # height
            )

            if row_idx == 3:
                row_idx = 1
                total_columns += 1

                continue

            row_idx += 1

        self.stack.props.visible_child_name = "history_page"

        self.empty_button.props.sensitive = any(
            [len(i) for sub in history for i in sub]
        )

        return None

    def update_history(self, new_history: list) -> None:
        variant_array = GLib.Variant.new_array(
            GLib.VariantType("as"),
            [
                GLib.Variant.new_array(
                    GLib.VariantType("s"),
                    [GLib.Variant.new_string(x) for x in states],
                )
                for states in new_history
            ],
        )
        self.settings.set_value("pinned-clipboard-history", variant_array)

        self.empty_button.props.sensitive = any(
            [len(i) for sub in new_history for i in sub]
        )

        return None

    def empty_slots_alert_dialog(self, *_args) -> None:
        alert_dialog = Adw.AlertDialog(
            heading="Empty slots?",
            body="All information will be erased. Do you want to continue?",
            close_response="cancel",
        )

        alert_dialog.add_response("cancel", "Cancel")
        alert_dialog.add_response("empty", "Empty")

        alert_dialog.set_response_appearance(
            "empty", Adw.ResponseAppearance.DESTRUCTIVE
        )

        win = self

        def empty_slots(alert_dialog: Adw.AlertDialog, task: Gio.Task) -> None:
            response = alert_dialog.choose_finish(task)
            if response == "cancel":
                return None

            win.update_history([["", "", ""] for _ in range(6)])
            for _ in range(3):
                win.grid.remove_column(1)
            win._set_grid()

        alert_dialog.choose(self, None, empty_slots)
        return None
