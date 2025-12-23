import hashlib

from typing import Callable, Optional

import gi

from .define import (
    supported_file_formats,
    supported_image_formats,
    supported_text_formats,
)

gi.require_version("Gdk", "4.0")
if gi:
    from gi.repository import Gdk, GLib


class ClipboardMonitor:
    def __init__(self, callback: Callable[[], None]):
        self.callback = callback
        self.clipboard = Gdk.Display.get_default().get_clipboard()
        self.last_content_hash: Optional[str] = None
        self.last_formats: list = []
        self.is_monitoring = False
        self._first_run = True

    def start(self):
        if self.is_monitoring:
            return
        self.is_monitoring = True

        # Initial capture
        self.last_formats = self.clipboard.get_formats().to_string()
        self._check_content_async(is_initial=True)

        GLib.timeout_add(1000, self._check_clipboard)

    def stop(self):
        self.is_monitoring = False

    def _check_clipboard(self):
        if not self.is_monitoring:
            return False

        # 1. Format Check (Fast)
        current_formats = self.clipboard.get_formats().to_string()
        formats_list = current_formats.split(" ")

        if current_formats != self.last_formats:
            self.last_formats = current_formats
            self.callback()
            self._check_content_async(is_initial=True)  # Update hash silently
            return True

        # 2. Content Check (Slow) - If formats imply supported content
        self._check_content_async(is_initial=False)
        return True

    def _check_content_async(self, is_initial: bool):
        formats = self.clipboard.get_formats().to_string().split(" ")

        # Priority: Image > File > Text (Matches CopyAlertWindow logic)
        if bool(set(supported_image_formats) & set(formats)):
            self.clipboard.read_texture_async(
                None, self._on_read_texture, is_initial
            )
        elif bool(set(supported_file_formats) & set(formats)):
            self.clipboard.read_value_async(
                Gdk.FileList, 0, None, self._on_read_files, is_initial
            )
        elif bool(set(supported_text_formats) & set(formats)):
            self.clipboard.read_text_async(
                None, self._on_read_text, is_initial
            )

    def _on_read_texture(self, clipboard, result, is_initial):
        try:
            texture = clipboard.read_texture_finish(result)
            if not texture:
                return

            # Hash the pixels to detect changes
            # Note: This is resource intensive but necessary for images
            pixbuf = Gdk.pixbuf_get_from_texture(texture)
            success, buffer = pixbuf.save_to_bufferv("png", [], [])
            if not success:
                return

            content_hash = hashlib.sha256(buffer).hexdigest()
            self._handle_content_change(content_hash, is_initial)
        except Exception:
            pass

    def _on_read_files(self, clipboard, result, is_initial):
        try:
            file_list = clipboard.read_value_finish(result)
            if not file_list:
                return

            # Hash the list of paths
            uris = sorted([f.get_uri() for f in file_list])
            content_hash = hashlib.sha256("".join(uris).encode()).hexdigest()
            self._handle_content_change(content_hash, is_initial)
        except Exception:
            pass

    def _on_read_text(self, clipboard, result, is_initial):
        try:
            text = clipboard.read_text_finish(result)
            if not text:
                return

            # Use text itself as hash/identifier
            self._handle_content_change(text, is_initial)
        except Exception:
            pass

    def _handle_content_change(self, new_hash, is_initial):
        if is_initial or self._first_run:
            self.last_content_hash = new_hash
            self._first_run = False
            return

        if new_hash != self.last_content_hash:
            self.last_content_hash = new_hash
            self.callback()
