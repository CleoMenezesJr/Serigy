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

import gi

from .copy_alert_window import CopyAlertWindow
from .setup_dialog import SetupDialog

gi.require_versions({"Gtk": "4.0", "Adw": "1"})

if gi:
    from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk

    from .window import SerigyWindow


class SerigyApplication(Adw.Application):
    """The main application singleton class."""

    def __init__(self):
        super().__init__(
            application_id="page.codeberg.cleomenezesjr.Serigy",
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE
            | Gio.ApplicationFlags.CAN_OVERRIDE_APP_ID,
        )
        self.create_action("quit", lambda *_: self.quit(), ["<primary>q"])
        self.create_action("about", self.on_about_action)
        self.create_action("preferences", self.on_preferences_action)

        self.add_main_option(
            "copy",
            ord("c"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            "Call copy function",
            None,
        )

        self.is_copy = False

    def do_activate(self):
        """Called when the application is activated.

        We raise the application's main window, creating it if
        necessary.
        """

        win = self.props.active_window
        if not win:
            win = SerigyWindow(application=self)

        if self.is_copy:
            self.copy_alert_window = CopyAlertWindow(
                application=self, main_window=win
            )
            self.copy_alert_window.show()
            self.is_copy = False
            return

        win.present()

        _settings: Gio.Settings = Gio.Settings.new(
            "page.codeberg.cleomenezesjr.Serigy"
        )
        show_welcome_window = _settings.get_boolean("show-welcome-window")
        if show_welcome_window:
            dialog: Adw.Dialog = SetupDialog()
            dialog.present(parent=win)

    def on_about_action(self, *args):
        """Callback for the app.about action."""
        about = Adw.AboutDialog(
            application_name="serigy",
            application_icon="page.codeberg.cleomenezesjr.Serigy",
            developer_name="Cleo Menezes Jr.",
            version="0.1.0",
            developers=["Cleo Menezes Jr."],
            copyright="© 2024 Cleo Menezes Jr.",
            comments=_("A clipboard pinner for GNOME."),
            issue_url="https://github.com/CleoMenezesJr/escambo/issues/new",
            support_url="https://ko-fi.com/cleomenezesjr",
        )
        # Translators: Replace "translator-credits" with your name/username,
        # and optionally an email or URL.
        about.set_translator_credits(_("translator-credits"))
        about.present(self.props.active_window)

    def on_preferences_action(self, widget, _):
        """Callback for the app.preferences action."""
        print("app.preferences action activated")

    def create_action(self, name, callback, shortcuts=None):
        """Add an application action.

        Args:
            name: the name of the action
            callback: the function to be called when the action is
              activated
            shortcuts: an optional list of accelerators
        """
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)

    def do_command_line(self, command):
        """
        This function is called when the application is launched from the
        command line. It parses the command line arguments and calls the
        corresponding functions.
        See: __register_arguments()
        """
        commands = command.get_options_dict()

        if commands.contains("copy"):
            self.is_copy = True

        self.do_activate()
        return 0


def main(version):
    """The application's entry point."""
    app = SerigyApplication()
    return app.run(sys.argv)
