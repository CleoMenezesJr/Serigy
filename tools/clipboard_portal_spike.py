# Copyright 2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

"""Spike: clipboard monitoring via RemoteDesktop + Clipboard portals.

Answers three questions the current sentinel/focus-stealing monitor cannot:

  1. Does SelectionOwnerChanged fire for text AND images with no window
     focused (and no window at all)?
  2. Does persist_mode=2 restore the grant silently on the next run?
  3. Can we own the selection (SetSelection/SelectionWrite) without the
     suppress_next_change dance?

Run it, then copy things in other apps and watch stdout. Ctrl-C to stop.

    flatpak run --filesystem=<repo> --command=python3 \
        io.github.cleomenezesjr.Serigy <repo>/tools/clipboard_portal_spike.py

Run it twice: the first run shows GNOME's consent dialog, the second must
not (that is the persistence check).
"""

import argparse
import hashlib
import os
import select
import sys
import time
from secrets import token_hex

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
IFACE_REMOTE = "org.freedesktop.portal.RemoteDesktop"
IFACE_INPUT_CAPTURE = "org.freedesktop.portal.InputCapture"
IFACE_CLIPBOARD = "org.freedesktop.portal.Clipboard"
IFACE_REQUEST = "org.freedesktop.portal.Request"
IFACE_SESSION = "org.freedesktop.portal.Session"

TOKEN_DIR = os.path.join(GLib.get_user_config_dir(), "serigy-spike")

_start = time.monotonic()


def log(msg: str) -> None:
    print(f"[{time.monotonic() - _start:7.2f}s] {msg}", flush=True)


class Spike:
    def __init__(
        self,
        device_types: int,
        test_write: bool,
        input_capture: bool = False,
    ):
        self.device_types = device_types
        self.test_write = test_write
        # InputCapture is the other portal session type the Clipboard
        # portal can attach to. It grants no access to screen contents,
        # so it may not raise the "screen is being shared" indicator.
        self.input_capture = input_capture
        self.token_path = os.path.join(
            TOKEN_DIR,
            "restore-token-input-capture"
            if input_capture
            else "restore-token-remote-desktop",
        )
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.sender = self.bus.get_unique_name()[1:].replace(".", "_")
        self.session_handle: str | None = None
        self.owned_payload = b"serigy-spike-owns-the-clipboard"
        self.loop = GLib.MainLoop()
        self._fallback_used = False

    # ---- plumbing ----------------------------------------------------

    def _request_path(self, token: str) -> str:
        return f"{PORTAL_PATH}/request/{self.sender}/{token}"

    def _call(self, iface: str, method: str, params: GLib.Variant):
        return self.bus.call_sync(
            PORTAL_BUS,
            PORTAL_PATH,
            iface,
            method,
            params,
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

    def _request(self, iface: str, method: str, build_params, on_response):
        """Issue a portal Request and route its Response to on_response.

        Subscribes before calling so the reply cannot race us.
        """
        token = f"serigy_spike_{token_hex(8)}"
        sub_id = None

        def handler(_conn, _sender, _path, _iface, _signal, params):
            self.bus.signal_unsubscribe(sub_id)
            response, results = params.unpack()
            on_response(response, results)

        sub_id = self.bus.signal_subscribe(
            PORTAL_BUS,
            IFACE_REQUEST,
            "Response",
            self._request_path(token),
            None,
            Gio.DBusSignalFlags.NONE,
            handler,
        )
        self._call(iface, method, build_params(token))

    def _read_fd(self, fd: int, timeout: float = 5.0) -> bytes:
        """Drain the portal's pipe.

        The fd comes back non-blocking and the source app has usually not
        written anything yet, so reading straight away raises EAGAIN. Wait
        on it instead. (Real code should do this with a GLib IO watch —
        this blocks the main loop.)
        """
        chunks = []
        try:
            while True:
                readable, _, _ = select.select([fd], [], [], timeout)
                if not readable:
                    log(f"        !! timed out after {timeout}s")
                    break
                try:
                    chunk = os.read(fd, 65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            os.close(fd)
        return b"".join(chunks)

    # ---- session setup ------------------------------------------------

    def run(self) -> int:
        kind = "InputCapture" if self.input_capture else "RemoteDesktop"
        log(f"unique name .{self.sender}, {kind}, types={self.device_types}")
        self.create_session()
        try:
            self.loop.run()
        except KeyboardInterrupt:
            pass
        return 0

    def create_session(self) -> None:
        def options(token):
            opts = {
                "handle_token": GLib.Variant("s", token),
                "session_handle_token": GLib.Variant(
                    "s", f"serigy_spike_{token_hex(8)}"
                ),
            }
            if self.input_capture:
                # capabilities: 1=keyboard, 2=pointer, 4=touchscreen
                opts["capabilities"] = GLib.Variant("u", self.device_types)
            return opts

        if self.input_capture:
            log("InputCapture.CreateSession…")
            self._request(
                IFACE_INPUT_CAPTURE,
                "CreateSession",
                lambda t: GLib.Variant("(sa{sv})", ("", options(t))),
                self._on_session,
            )
            return

        log("RemoteDesktop.CreateSession…")
        self._request(
            IFACE_REMOTE,
            "CreateSession",
            lambda t: GLib.Variant("(a{sv})", (options(t),)),
            self._on_session,
        )

    def _on_session(self, response: int, results: dict) -> None:
        if response != 0:
            log(f"FAIL CreateSession response={response} results={results}")
            self.loop.quit()
            return
        self.session_handle = results["session_handle"]
        log(f"session = {self.session_handle}")

        self.bus.signal_subscribe(
            PORTAL_BUS,
            IFACE_SESSION,
            "Closed",
            self.session_handle,
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_session_closed,
        )
        if self.input_capture:
            # No SelectDevices step: capabilities went in CreateSession and
            # persistence is negotiated at Start. RequestClipboard before
            # Start is rejected here with "Invalid state (0)", despite what
            # the spec says — so it is attempted after Start instead.
            self.start()
            return
        self.select_devices()

    def _on_session_closed(self, *_args) -> None:
        log("!! Session.Closed — the portal dropped our session")
        self.loop.quit()

    def select_devices(self) -> None:
        options = {
            "types": GLib.Variant("u", self.device_types),
            "persist_mode": GLib.Variant("u", 2),  # until explicitly revoked
        }
        restore_token = self._load_token()
        if restore_token:
            options["restore_token"] = GLib.Variant("s", restore_token)
            log("reusing stored restore_token (expecting NO dialog)")
        else:
            log("no restore_token stored (expecting the consent dialog)")

        def build(token):
            opts = dict(options)
            opts["handle_token"] = GLib.Variant("s", token)
            return GLib.Variant("(oa{sv})", (self.session_handle, opts))

        log("RemoteDesktop.SelectDevices…")
        self._request(IFACE_REMOTE, "SelectDevices", build, self._on_devices)

    def _on_devices(self, response: int, results: dict) -> None:
        if response != 0:
            log(f"FAIL SelectDevices response={response} results={results}")
            if self.device_types == 0 and not self._fallback_used:
                # GNOME may refuse a session that controls no input device.
                self._fallback_used = True
                self.device_types = 3  # keyboard | pointer
                log("retrying with device_types=3 (keyboard|pointer)")
                self.create_session()
                return
            self.loop.quit()
            return

        self.request_clipboard()
        self.start()

    def request_clipboard(self) -> None:
        log("RequestClipboard (must come before Start)…")
        self._call(
            IFACE_CLIPBOARD,
            "RequestClipboard",
            GLib.Variant("(oa{sv})", (self.session_handle, {})),
        )

    def start(self) -> None:
        iface = IFACE_INPUT_CAPTURE if self.input_capture else IFACE_REMOTE

        def build(token):
            opts = {"handle_token": GLib.Variant("s", token)}
            if self.input_capture:
                # RemoteDesktop negotiates persistence at SelectDevices;
                # InputCapture does it here.
                opts["persist_mode"] = GLib.Variant("u", 2)
                restore_token = self._load_token()
                if restore_token:
                    opts["restore_token"] = GLib.Variant("s", restore_token)
                    log("reusing stored restore_token (expecting NO dialog)")
            return GLib.Variant(
                "(osa{sv})",
                (
                    self.session_handle,
                    "",  # no parent window — we are headless on purpose
                    opts,
                ),
            )

        log(f"{iface.rsplit('.', 1)[-1]}.Start… (dialog on first run)")
        self._request(iface, "Start", build, self._on_started)

    def _on_started(self, response: int, results: dict) -> None:
        if response != 0:
            log(f"FAIL Start response={response} results={results}")
            self.loop.quit()
            return

        clipboard_enabled = results.get("clipboard_enabled", False)
        if self.input_capture and not clipboard_enabled:
            try:
                self.request_clipboard()
                clipboard_enabled = True
                log("RequestClipboard accepted AFTER Start")
            except GLib.Error as e:
                log(f"RequestClipboard after Start failed too: {e.message}")

        log(f"STARTED. clipboard_enabled={clipboard_enabled}")
        log(f"        devices={results.get('devices')}")

        token = results.get("restore_token")
        if token:
            self._store_token(token)
            log("        restore_token stored → rerun to test persistence")
        else:
            log("        !! no restore_token returned (persistence broken)")

        if not clipboard_enabled:
            log("!! clipboard access denied — nothing to monitor, quitting")
            self.loop.quit()
            return

        self.bus.signal_subscribe(
            PORTAL_BUS,
            IFACE_CLIPBOARD,
            "SelectionOwnerChanged",
            PORTAL_PATH,
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_owner_changed,
        )
        if self.test_write:
            self.bus.signal_subscribe(
                PORTAL_BUS,
                IFACE_CLIPBOARD,
                "SelectionTransfer",
                PORTAL_PATH,
                None,
                Gio.DBusSignalFlags.NONE,
                self._on_transfer,
            )
            GLib.timeout_add_seconds(10, self._claim_selection)
            log("will claim the selection in 10s (--test-write)")

        log("")
        log("=== monitoring. Copy text, then an image, in ANY app. ===")
        log("=== No Serigy window exists — that is the whole point. ===")

    # ---- the actual monitoring ----------------------------------------

    def _on_owner_changed(self, _c, _s, _p, _i, _sig, params) -> None:
        _session, options = params.unpack()
        mime_types = options.get("mime_types", [])
        is_owner = options.get("session_is_owner", False)
        log(f"SelectionOwnerChanged: owner_is_us={is_owner}")
        log(f"        mime_types={mime_types}")
        if is_owner:
            return

        mime = self._pick_mime(mime_types)
        if not mime:
            log("        no readable mime type offered")
            return
        self._read_selection(mime)

    def _pick_mime(self, mime_types: list[str]) -> str | None:
        """Image wins over text: an image copy often also offers text/html."""
        for mime in mime_types:
            if mime.startswith("image/"):
                return mime
        for preferred in (
            "text/plain;charset=utf-8",
            "text/plain",
            "UTF8_STRING",
        ):
            if preferred in mime_types:
                return preferred
        return mime_types[0] if mime_types else None

    def _read_selection(self, mime: str) -> None:
        log(f"        SelectionRead({mime})…")
        try:
            result, fd_list = self.bus.call_with_unix_fd_list_sync(
                PORTAL_BUS,
                PORTAL_PATH,
                IFACE_CLIPBOARD,
                "SelectionRead",
                GLib.Variant("(os)", (self.session_handle, mime)),
                GLib.VariantType("(h)"),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
                None,
            )
        except GLib.Error as e:
            log(f"        FAIL SelectionRead: {e.message}")
            return

        fd = fd_list.get(result.unpack()[0])
        data = self._read_fd(fd)
        digest = hashlib.sha256(data).hexdigest()[:12]
        preview = data[:60].decode("utf-8", "replace").replace("\n", "\\n")
        log(f"        GOT {len(data)} bytes, sha256={digest}")
        log(f"        preview={preview!r}")

    # ---- owning the selection (optional) -------------------------------

    def _claim_selection(self) -> bool:
        log("SetSelection: claiming text/plain ownership")
        self._call(
            IFACE_CLIPBOARD,
            "SetSelection",
            GLib.Variant(
                "(oa{sv})",
                (
                    self.session_handle,
                    {
                        "mime_types": GLib.Variant(
                            "as", ["text/plain;charset=utf-8", "text/plain"]
                        )
                    },
                ),
            ),
        )
        return False

    def _on_transfer(self, _c, _s, _p, _i, _sig, params) -> None:
        _session, mime, serial = params.unpack()
        log(f"SelectionTransfer: someone is pasting {mime} (serial={serial})")
        try:
            result, fd_list = self.bus.call_with_unix_fd_list_sync(
                PORTAL_BUS,
                PORTAL_PATH,
                IFACE_CLIPBOARD,
                "SelectionWrite",
                GLib.Variant("(ou)", (self.session_handle, serial)),
                GLib.VariantType("(h)"),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
                None,
            )
        except GLib.Error as e:
            log(f"        FAIL SelectionWrite: {e.message}")
            return

        fd = fd_list.get(result.unpack()[0])
        try:
            os.write(fd, self.owned_payload)
            success = True
        except OSError as e:
            log(f"        write failed: {e}")
            success = False
        finally:
            os.close(fd)

        self._call(
            IFACE_CLIPBOARD,
            "SelectionWriteDone",
            GLib.Variant("(oub)", (self.session_handle, serial, success)),
        )
        log(f"        served {len(self.owned_payload)} bytes, done={success}")

    # ---- restore token persistence -------------------------------------

    def _load_token(self) -> str | None:
        try:
            with open(self.token_path, encoding="utf-8") as f:
                return f.read().strip() or None
        except OSError:
            return None

    def _store_token(self, token: str) -> None:
        os.makedirs(TOKEN_DIR, exist_ok=True)
        with open(self.token_path, "w", encoding="utf-8") as f:
            f.write(token)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--types",
        type=int,
        default=0,
        help="RemoteDesktop device bitmask (0=none, 1=kbd, 2=pointer, "
        "3=both). Starts at 0 and falls back to 3 if GNOME refuses.",
    )
    parser.add_argument(
        "--test-write",
        action="store_true",
        help="also claim the selection and serve paste requests",
    )
    parser.add_argument(
        "--input-capture",
        action="store_true",
        help="attach the clipboard to an InputCapture session instead of "
        "RemoteDesktop (grants no screen access)",
    )
    parser.add_argument(
        "--forget",
        action="store_true",
        help="drop the stored restore_token and exit",
    )
    args = parser.parse_args()

    spike = Spike(args.types, args.test_write, args.input_capture)

    if args.forget:
        try:
            os.remove(spike.token_path)
            log(f"removed {spike.token_path}")
        except OSError as e:
            log(f"nothing to remove: {e}")
        return 0

    return spike.run()


if __name__ == "__main__":
    sys.exit(main())
