# Copyright 2024-2025 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import signal
import sys
from gettext import gettext as _
from typing import Any, Callable, Optional

import gi

from serigy.clipboard import ClipboardManager, ClipboardMonitor, ClipboardQueue
from serigy.copy_alert_window import CopyAlertWindow
from serigy.define import APP_ID, RESOURCE_PATH
from serigy.logging.setup import log_system_info, setup_logging
from serigy.preferences import PreferencesDialog
from serigy.settings import Settings
from serigy.setup_shortcut_portal import setup as setup_shortcut_portal

gi.require_versions({"Gtk": "4.0", "Adw": "1", "Xdp": "1.0"})

if gi:
    from gi.repository import Adw, Gio, GLib, Gtk, Xdp

    from serigy.window import SerigyWindow


class SerigyApplication(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
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
        self.create_action("quit", self._on_quit, ["<primary>q"])
        self.create_action(
            "toggle_incognito",
            self.on_toggle_incognito,
            ["<primary><alt><shift>i"],
        )

        self.portal = Xdp.Portal()
        self.portal.set_background_status(_("Monitoring clipboard"), None)

        self.hold()  # Prevent application from quitting if no windows are open
        self.connect("shutdown", self._on_terminate)

        # Handle SIGTERM from Background Apps
        GLib.unix_signal_add(
            GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._on_terminate
        )

        self.add_main_option(
            "copy",
            ord("c"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            _("Call copy function"),
            None,
        )

        self.is_copy = False
        self._app_ready = False
        self._shortcut_configured = setup_shortcut_portal(self)

        self.clipboard_manager = ClipboardManager(self)
        self.clipboard_queue = ClipboardQueue(
            self.clipboard_manager.process_item
        )

        self.clipboard_monitor = ClipboardMonitor(
            callback=self.on_clipboard_changed,
            polling_callback=self.on_image_poll,
        )

        Settings.get().incognito_mode = False  # Reset on startup
        Settings.get().connect(
            "changed::incognito-mode", self._on_incognito_changed
        )
        self._update_monitor_state()

    def on_clipboard_changed(self):
        if not self._app_ready:
            return
        self.is_copy = True
        self.do_activate()

    def on_image_poll(self, last_hash):
        """Called by image polling to check for new content."""
        if not self._app_ready:
            return
        if hasattr(self, "copy_alert_window") and self.copy_alert_window:
            return  # Already processing

        self.copy_alert_window = CopyAlertWindow(
            application=self,
            queue=self.clipboard_queue,
            on_finished=self.on_copy_finished,
            last_hash=last_hash,
            is_polling=True,
        )
        self.copy_alert_window.show()

    def on_copy_finished(self):
        self.copy_alert_window = None
        self.clipboard_monitor.done_processing()

    def on_toggle_incognito(self, *args):
        Settings.get().incognito_mode = not Settings.get().incognito_mode

    def _on_incognito_changed(self, settings, key):
        self._update_monitor_state()

    def _update_monitor_state(self):
        if Settings.get().incognito_mode:
            self.clipboard_monitor.stop()
        else:
            self.clipboard_monitor.start()

    def _on_quit(self, *args):
        win = self.props.active_window
        if win:
            win.close()
        else:
            self.quit()

    def _on_terminate(self, *args):
        self.clipboard_monitor.stop()
        self.release()
        return False

    def _on_retry_shortcut_setup(self, button):
        self._shortcut_configured = setup_shortcut_portal(self)
        win = self.get_active_window()
        if self._shortcut_configured and win:
            win.stack.props.visible_child_name = "slots_page"
            self._app_ready = True

    def do_activate(self) -> None:
        try:
            setup_logging()
        except ValueError:
            pass

        log_system_info()

        # Handle copy mode first, before touching main window
        if self.is_copy:
            if hasattr(self, "copy_alert_window") and self.copy_alert_window:
                self.is_copy = False
                return None

            self.copy_alert_window = CopyAlertWindow(
                application=self,
                queue=self.clipboard_queue,
                on_finished=self.on_copy_finished,
            )
            self.copy_alert_window.show()
            self.is_copy = False
            return None

        # Check for active window to prevent duplicates
        win = self.get_active_window()
        if not win:
            win = SerigyWindow(application=self)
            win.setup_button.connect("clicked", self._on_retry_shortcut_setup)
            self.create_action(
                "arrange_slots", win.arrange_slots, ["<primary>o"]
            )

        self._app_ready = True

        # Show setup required page if shortcut not configured
        if not self._shortcut_configured:
            win.stack.props.visible_child_name = "setup_required_page"
            win.present()
            return

        win.present()

        # Request background/autostart permission only once
        if not hasattr(self, "_background_requested"):
            self._background_requested = True
            try:
                self.portal.request_background(
                    None,  # parent - using None due to XdpGtk issues
                    "Monitoring clipboard in the background.",
                    [APP_ID, "--gapplication-service"],
                    Xdp.BackgroundFlags.AUTOSTART,
                    None,
                )
            except Exception:
                pass

    def on_about_action(self, *args: tuple) -> None:
        about = Adw.AboutDialog(
            application_name="Serigy",
            application_icon=APP_ID,
            developer_name="Cleo Menezes Jr.",
            version="1.1",
            developers=["Cleo Menezes Jr. https://github.com/CleoMenezesJr"],
            copyright="© 2024-2025 Cleo Menezes Jr.",
            comments=_("Manage your clipboard minimally"),
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
        builder.add_from_resource(f"{RESOURCE_PATH}/gtk/shortcuts-dialog.ui")
        dialog = builder.get_object("shortcuts_dialog")

        try:
            from serigy.setup_shortcut_portal import portal

            shortcuts = portal.list_shortcuts()
            for shortcut_id, props in shortcuts:
                if shortcut_id == "open_serigy" and "trigger" in props:
                    global_item = builder.get_object("global_shortcut")
                    if global_item:
                        global_item.set_accelerator(props["trigger"])
                    break
        except Exception:
            pass

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
