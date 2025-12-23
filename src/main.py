# main.py
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

import sys
from gettext import gettext as _
from typing import Any, Callable, Optional

import gi

from .clipboard_monitor import ClipboardMonitor
from .copy_alert_window import CopyAlertWindow
from .logging.setup import log_system_info, setup_logging
from .preferences import PreferencesDialog
from .settings import Settings
from .setup_shortcut_portal import setup as setup_shortcut_portal

gi.require_versions({"Gtk": "4.0", "Adw": "1", "Xdp": "1.0"})

if gi:
    from gi.repository import Adw, Gio, GLib, Gtk, Xdp

    from .window import SerigyWindow


class SerigyApplication(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="io.github.cleomenezesjr.Serigy",
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE
            | Gio.ApplicationFlags.CAN_OVERRIDE_APP_ID,
        )
        self.create_action("about", self.on_about_action)
        self.create_action(
            "preferences", self.on_preferences_action, ["<primary>p"]
        )
        self.create_action(
            "shortcuts",
            lambda *_: GLib.idle_add(self.on_shortcuts_action),
            ["<primary>slash"],
        )

        self.portal = Xdp.Portal()
        self.portal.set_background_status("Waiting user input", None)

        self.hold()  # Prevent application from quitting if no windows are open
        self.connect("activate", self.on_activate)

        self.add_main_option(
            "copy",
            ord("c"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            _("Call copy function"),
            None,
        )

        self.is_copy = False

        setup_shortcut_portal(self)

        self.clipboard_monitor = ClipboardMonitor(self.on_clipboard_changed)
        self.clipboard_monitor.start()

    def on_clipboard_changed(self):
        self.is_copy = True
        self.do_activate()

    def on_activate(self, *kwargs):
        win = self.props.active_window
        parent = Xdp.parent_new_gtk(win) if win else None

        if not parent:
            notification = Gio.Notification()
            notification.set_title(_("Background Mode Failed"))
            notification.set_body(
                _(
                    "Serigy could not request background permission because no active window was found."
                )
            )
            self.send_notification("background-request-failed", notification)
            return

        self.portal.request_background(
            parent,
            "Waiting for user input to pin clipboard.",
            ["serigy", "--gapplication-service"],
            Xdp.BackgroundFlags.AUTOSTART,
            None,
        )

    def do_activate(self) -> None:
        try:
            setup_logging()
        except ValueError:
            pass

        log_system_info()

        win = self.props.active_window
        if not win:
            win = SerigyWindow(application=self)

        if self.is_copy:
            self.copy_alert_window = CopyAlertWindow(
                application=self, main_window=win
            )
            self.copy_alert_window.show()
            self.is_copy = False
            return None

        self.create_action("arrange_slots", win.arrange_slots, ["<primary>o"])
        self.create_action("quit", lambda *_: win.close(), ["<primary>q"])

        win.present()

    def on_about_action(self, *args: tuple) -> None:
        about = Adw.AboutDialog(
            application_name="Serigy",
            application_icon="io.github.cleomenezesjr.Serigy",
            developer_name="Cleo Menezes Jr.",
            version="1.1",
            developers=["Cleo Menezes Jr. https://github.com/CleoMenezesJr"],
            copyright="© 2024 Cleo Menezes Jr.",
            comments=_("Pin your clipboard"),
            issue_url="https://github.com/CleoMenezesJr/escambo/issues/new",
            support_url="https://matrix.to/#/%23serigy:matrix.org",
            artists=["Jakub Steiner https://jimmac.eu/"],
        )
        # Translators: Replace "translator-credits" with your name/username,
        # and optionally an email or URL.
        about.set_translator_credits(_("translator-credits"))
        about.add_link(_("Donate"), "https://ko-fi.com/cleomenezesjr ")
        about.add_other_app(
            "io.github.cleomenezesjr.aurea",
            _("Aurea"),
            _("Flatpak metainfo banner previewer"),
        )
        about.present(self.props.active_window)

    def on_preferences_action(
        self, action: Gio.SimpleAction, param: Optional[Any]
    ) -> None:
        prefs = PreferencesDialog(self.props.active_window)
        prefs.present(self.props.active_window)

    def on_shortcuts_action(self, *args: tuple) -> None:
        builder = Gtk.Builder()
        builder.add_from_resource(
            "/io/github/cleomenezesjr/Serigy/gtk/shortcuts-dialog.ui"
        )
        dialog = builder.get_object("shortcuts_dialog")
        dialog.present(self.props.active_window)

    def create_action(
        self,
        name: str,
        callback: Callable[[], None],
        shortcuts: Optional[list] = None,
    ) -> Optional[int]:
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)

    def do_command_line(self, command_line: Gio.ApplicationCommandLine):
        commands = command_line.get_options_dict()
        commands = commands.end().unpack()

        if "copy" in commands:
            self.is_copy = True

        self.do_activate()
        return 0


def main(version: str) -> int:
    app = SerigyApplication()
    return app.run(sys.argv)
