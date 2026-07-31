# Copyright 2024-2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import signal
import sys
from collections.abc import Callable
from gettext import gettext as _
from typing import Any

import gi

from serigy.auto_cleaner import AutoCleaner
from serigy.clipboard import (
    ClipboardManager,
    ClipboardMonitor,
    ClipboardQueue,
    ClipboardWriter,
)
from serigy.copy_alert_window import CopyAlertWindow
from serigy.define import APP_ID, RESOURCE_PATH, VERSION
from serigy.image_store import migrate as migrate_images
from serigy.logging.setup import log_system_info, setup_logging
from serigy.preferences import PreferencesDialog
from serigy.search_provider import SearchProvider
from serigy.settings import Settings
from serigy.setup_shortcut_portal import setup as setup_shortcut_portal
from serigy.slot_data import SlotData
from serigy.welcome_dialog import WelcomeDialog

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
        self.create_action("open-window", self._on_open_window_action)
        self.create_action(
            "preferences", self.on_preferences_action, ["<primary>p"]
        )
        self.create_action(
            "shortcuts",
            lambda *_: GLib.idle_add(self.on_shortcuts_action),
            ["<primary>slash"],
        )
        self.create_action(
            "activate-monitoring", self._on_activate_monitoring_action
        )
        self.create_action("quit", self._on_quit, ["<primary>q"])
        self.create_action(
            "toggle_incognito",
            self.on_toggle_incognito,
            ["<primary><alt><shift>i"],
        )

        self.portal = Xdp.Portal()

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
        self._shortcut_configured = False  # Initial state
        self._shortcut_setup_pending = False

        self.clipboard_manager = ClipboardManager(self)
        self.clipboard_queue = ClipboardQueue(
            self.clipboard_manager.process_item
        )

        self.clipboard_monitor = ClipboardMonitor(
            callback=self.on_clipboard_changed,
        )

        self._activation_pending = False
        self._activation_checked = False
        self._background_status = ""

        self._auto_cleaner = None
        self._welcome_dialog = None
        self._search_provider = None
        self._clipboard_writer = None

    def on_clipboard_changed(self):
        logging.debug(
            "on_clipboard_changed: app_ready=%s, existing_alert=%s",
            self._app_ready,
            hasattr(self, "copy_alert_window")
            and bool(self.copy_alert_window),
        )
        if not self._app_ready:
            self.clipboard_monitor.done_processing()
            return
        self.is_copy = True
        self.do_activate()

    def on_shortcut_copy(self):
        """Called when user triggers shortcut to pin current clipboard.

        Incognito refuses this too. Stopping the monitor only takes away the
        copies we notice by ourselves, and a capture asked for by hand is
        still a capture we would be storing.
        """
        if Settings.get().incognito_mode:
            logging.debug("on_shortcut_copy: refused, incognito is on")
            return

        if hasattr(self, "copy_alert_window") and self.copy_alert_window:
            return

        self.copy_alert_window = CopyAlertWindow(
            application=self,
            queue=self.clipboard_queue,
            on_finished=self.on_copy_finished,
            visible_mode=True,
        )
        self.copy_alert_window.show()

    def on_copy_finished(self):
        self.copy_alert_window = None
        self.clipboard_monitor.done_processing()
        # That window held focus and claimed the clipboard, so do not make
        # the user sit through another tick to hear monitoring is back.
        self._check_clipboard_activation()

    def write_slot_to_clipboard(self, slot, on_failed=None) -> None:
        """Put `slot` back on the clipboard, focus permitting.

        Refused while a capture is in flight: that window is claiming the
        clipboard for itself, and the two writes would undo each other.
        """
        if hasattr(self, "copy_alert_window") and self.copy_alert_window:
            logging.debug("Clipboard write refused: a capture is in flight")
            if on_failed:
                on_failed()
            return

        if self._clipboard_writer is not None:
            logging.debug("Clipboard write refused: one is already running")
            if on_failed:
                on_failed()
            return

        def on_finished():
            self._clipboard_writer = None

        self._clipboard_writer = ClipboardWriter(
            application=self,
            slot=slot,
            monitor=self.clipboard_monitor,
            on_finished=on_finished,
            on_failed=on_failed,
        )
        self._clipboard_writer.show()

    def on_toggle_incognito(self, *args):
        is_incognito = not Settings.get().incognito_mode
        Settings.get().incognito_mode = is_incognito

        win = self.get_active_window()
        if win:
            msg = (
                _("Incognito mode enabled")
                if is_incognito
                else _("Incognito mode disabled")
            )
            win.toast_overlay.add_toast(Adw.Toast(title=msg))

    def _on_monitor_setting_changed(self, settings, key):
        self._update_monitor_state()

    def _update_monitor_state(self):
        settings = Settings.get()
        if settings.monitor_clipboard and not settings.incognito_mode:
            self.clipboard_monitor.start()
        else:
            self.clipboard_monitor.stop()

        if not settings.monitor_clipboard or settings.incognito_mode:
            # Nothing is listening, so there is nothing to activate and no
            # reason to keep asking the user to fix it. Same condition the
            # activation check uses, so the notice goes the moment the switch
            # moves instead of on the next tick.
            self._clear_activation_pending()

        self._update_background_status()

    def _update_background_status(self):
        """Say in Background Apps what we are really doing.

        Nothing is claimed before the first activation check, because until it
        runs we do not know whether the compositor is handing us any copy.
        """
        if not self._activation_checked:
            return

        settings = Settings.get()
        # Incognito outranks the rest: storing nothing is the stronger claim,
        # and it is the one the user wants to see confirmed.
        if settings.incognito_mode:
            status = _("Incognito mode enabled")
        elif not settings.monitor_clipboard:
            status = _("Waiting for shortcut")
        elif self._activation_pending:
            status = _("Activation pending")
        else:
            status = _("Monitoring clipboard")

        if status == self._background_status:
            return
        self._background_status = status
        logging.debug("Background status: %s", status)
        self.portal.set_background_status(status, None)

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

    def _configure_shortcuts(self):
        self._shortcut_setup_pending = False
        self._shortcut_configured = setup_shortcut_portal(self)

        win = self.get_active_window()
        if win:
            win.stack.props.visible_child_name = (
                "slots_page"
                if self._shortcut_configured
                else "setup_required_page"
            )

        return GLib.SOURCE_REMOVE

    def _request_shortcuts(self):
        """Ask the portal for the shortcuts, from an idle.

        Binding runs a nested main loop that only ends once the user answers
        the portal dialog, so asking on the caller's stack holds up whatever
        it was doing, a window it was about to show included.
        """
        # One attempt at a time: startup and the first window open both ask,
        # and two of them reaching the portal together would each close the
        # session the other had just created.
        if self._shortcut_configured or self._shortcut_setup_pending:
            return

        self._shortcut_setup_pending = True
        GLib.idle_add(self._configure_shortcuts)

    def _on_retry_shortcut_setup(self, button):
        self._request_shortcuts()

    def do_startup(self):
        Adw.Application.do_startup(self)

        try:
            setup_logging()
        except ValueError:
            pass

        log_system_info()

        # Everything from here on belongs to the process that stays: startup
        # runs in the primary instance only, while __init__ runs in every
        # process, including the short-lived client that forwards a command
        # line and leaves. Holding the application from __init__ kept that
        # client in the main loop forever, and the monitor it started there
        # went for the same clipboard the real app was watching.
        self.hold()
        self.connect("shutdown", self._on_terminate)
        GLib.unix_signal_add(
            GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._on_terminate
        )

        # Incognito lasts for one run, so launching clears it. Reading it
        # back is what decides whether the monitor starts, so it comes first.
        Settings.get().incognito_mode = False

        Settings.get().connect(
            "changed::incognito-mode", self._on_monitor_setting_changed
        )
        Settings.get().connect(
            "changed::monitor-clipboard", self._on_monitor_setting_changed
        )
        self._update_monitor_state()

        self._auto_cleaner = AutoCleaner(self.get_active_window)

        self._migrate_images()

        self._request_shortcuts()

        # Request background/autostart permission immediately on startup
        if not hasattr(self, "_background_requested"):
            self._background_requested = True
            try:
                # Workaround for Python applications
                # to avoid issues with parent window
                parent = None
                self.portal.request_background(
                    parent,
                    _("Monitoring clipboard in the background."),
                    ["serigy", "--gapplication-service"],
                    Xdp.BackgroundFlags.AUTOSTART,
                    None,
                    self._on_request_background_finish,
                    None,
                )
            except Exception as e:
                logging.error("Background request init failed: %s", e)

        # Wayland only delivers clipboard events to focused windows. Whenever
        # we are left without one, prompt the user via notification.
        GLib.timeout_add_seconds(3, self._check_clipboard_activation)

        self._app_ready = True

    def do_dbus_register(self, connection, object_path):
        if not Adw.Application.do_dbus_register(self, connection, object_path):
            return False

        try:
            self._search_provider = SearchProvider(self)
            self._search_provider.register(
                connection, f"{object_path}/SearchProvider"
            )
        except Exception as e:
            # Losing the search is worth a log line; losing the app is not.
            logging.error("Could not register the search provider: %s", e)
            self._search_provider = None
        return True

    def do_dbus_unregister(self, connection, object_path):
        if self._search_provider is not None:
            self._search_provider.unregister(connection)
            self._search_provider = None
        Adw.Application.do_dbus_unregister(self, connection, object_path)

    def do_activate(self) -> None:
        if self.is_copy:
            if Settings.get().incognito_mode:
                # --copy arrives here without passing the monitor, so this is
                # the only thing standing between it and a stored slot.
                logging.debug("do_activate: copy refused, incognito is on")
                self.is_copy = False
                return None

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

        win = None
        windows = self.get_windows()
        if windows:
            win = windows[0]

        if not win:
            win = SerigyWindow(application=self)
            win.setup_button.connect("clicked", self._on_retry_shortcut_setup)

        self.create_action("arrange_slots", win.arrange_slots, ["<primary>o"])

        win.stack.props.visible_child_name = (
            "slots_page"
            if self._shortcut_configured
            else "setup_required_page"
        )

        # The window goes up before the ask, or the first thing a new user
        # sees is a permission dialog for an application still not on screen.
        win.present()
        self._request_shortcuts()

        if self._activation_pending:
            self._on_activate_monitoring_action()
            win.toast_overlay.add_toast(
                Adw.Toast(title=_("Clipboard monitoring activated"))
            )

        if Settings.get().show_welcome:
            if self._welcome_dialog:
                self._welcome_dialog.present(win)
            else:
                self._welcome_dialog = WelcomeDialog()
                self._welcome_dialog.connect(
                    "closed", lambda *_: setattr(self, "_welcome_dialog", None)
                )
                self._welcome_dialog.present(win)

    def _migrate_images(self):
        slots = Settings.get().slots
        missing = migrate_images(slot.filename for slot in slots)
        if not missing:
            return

        # A cache purge took these before the move; the slots would keep
        # pointing at files that can no longer be drawn.
        logging.info("Clearing %d slots with missing images", len(missing))
        for i, slot in enumerate(slots):
            if slot.filename in missing:
                slots[i] = SlotData()
        Settings.get().slots = slots

    def _clear_activation_pending(self):
        """Take back the pending state and the notice that announced it."""
        if not self._activation_pending:
            return
        logging.debug("Clipboard activation recovered, withdrawing notice")
        self._activation_pending = False
        self.withdraw_notification("clipboard-activation")

    def _check_clipboard_activation(self):
        """Ask, over and over, whether the next copy can still reach us.

        Losing the clipboard is not only a startup matter: focus can go to
        another window before the compositor hands us the selection, and from
        then on nothing arrives with no way back other than asking again.
        Getting it back is not only the user's doing either, since every
        capture window claims the clipboard on focus, so health is read afresh
        each tick instead of the pending flag latching until someone clicks.
        """
        settings = Settings.get()
        if not settings.monitor_clipboard or settings.incognito_mode:
            # Nothing is meant to be listening, so there is nothing to
            # activate, and what we are doing is known without asking the
            # compositor anything.
            self._clear_activation_pending()
            self._activation_checked = True
            self._update_background_status()
            return True

        if hasattr(self, "copy_alert_window") and self.copy_alert_window:
            # Mid capture, when the clipboard is nobody's for an instant.
            return True

        monitor = self.clipboard_monitor
        self._activation_checked = True
        has_content = bool(monitor.clipboard.get_formats().to_string())
        if monitor.owns_clipboard or has_content:
            # Our sentinel is there to be cancelled, or someone else's content
            # is there to be read, and a read going stale wakes the capture
            # window on its own.
            self._clear_activation_pending()
            self._update_background_status()
            return True

        if self._activation_pending:
            # Already asked; asking again every three seconds is nagging.
            return True

        logging.debug(
            "Clipboard activation check: sentinel not held, "
            "sending activation notification"
        )
        self._activation_pending = True
        self._update_background_status()
        notification = Gio.Notification.new(_("Clipboard Monitoring Inactive"))
        notification.set_body(
            _("Activate to start capturing clipboard history.")
        )
        notification.set_priority(Gio.NotificationPriority.URGENT)
        notification.set_default_action("app.activate-monitoring")
        notification.add_button(_("Activate"), "app.activate-monitoring")
        self.send_notification("clipboard-activation", notification)
        return True

    def _on_activate_monitoring_action(self, *args):
        logging.debug("activate-monitoring action invoked")
        self._clear_activation_pending()
        if hasattr(self, "copy_alert_window") and self.copy_alert_window:
            return

        def on_activation_finished():
            self._update_background_status()
            self.on_copy_finished()

        self.copy_alert_window = CopyAlertWindow(
            application=self,
            queue=self.clipboard_queue,
            on_finished=on_activation_finished,
            sentinel=self.clipboard_monitor.sentinel,
        )
        self.copy_alert_window.show()

    def _on_open_window_action(self, *args):
        self.do_activate()

    def _on_request_background_finish(self, source, result, data):
        try:
            success = source.request_background_finish(result)
            logging.debug("Background request success: %s", success)
        except Exception as e:
            logging.error("Background request failed in callback: %s", e)

    def on_about_action(self, *args: tuple) -> None:
        about = Adw.AboutDialog(
            application_name="Serigy",
            application_icon=APP_ID,
            developer_name="Cleo Menezes Jr.",
            version=VERSION,
            developers=["Cleo Menezes Jr. https://github.com/CleoMenezesJr"],
            copyright="© 2024-2026 Cleo Menezes Jr.",
            comments=_("Manage your clipboard minimally"),
            issue_url="https://github.com/CleoMenezesJr/Serigy/issues/new",
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
        self, action: Gio.SimpleAction, param: Any | None
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
        except Exception as e:
            # The dialog is still worth showing with the accelerator missing.
            logging.warning("Could not read the global shortcut: %s", e)

        dialog.present(self.props.active_window)

    def create_action(
        self,
        name: str,
        callback: Callable[[], None],
        shortcuts: list | None = None,
    ) -> int | None:
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

        # The client that forwarded this command line waits for the reply,
        # and the reply is only sent when this object is finalized. Under
        # Python that waits on the garbage collector, which on an idle
        # service can take minutes, so the client lingered as a live process
        # long after its errand was done. Say it here instead.
        command_line.set_exit_status(0)
        command_line.done()
        return 0


def main(version: str) -> int:
    app = SerigyApplication()
    return app.run(sys.argv)
