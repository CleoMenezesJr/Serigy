# Copyright 2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

"""How a stored slot is offered to whoever pastes next.

One slot can be handed over from two places — the card the user clicks and
the shell search result — and the choice of flavours is subtle enough that
stating it twice would mean stating it differently.
"""

import logging

from gi.repository import Gdk, Gio, GLib, GObject

from serigy.image_store import image_path


def text_provider(text: str) -> Gdk.ContentProvider:
    return Gdk.ContentProvider.new_for_value(text)


def texture_provider(texture: Gdk.Texture) -> Gdk.ContentProvider:
    return Gdk.ContentProvider.new_for_bytes(
        "image/png", texture.save_to_png_bytes()
    )


def file_provider(file: Gio.File) -> Gdk.ContentProvider:
    """Decide how to hand `file` over.

    A file we can open goes out as a Gdk.FileList, so GTK routes it
    through the file transfer portal and whoever pastes gets access to it
    as well. A file we cannot open would leave that transfer empty, and
    receivers prefer it over everything else, so there we offer the uri,
    as text too so it still lands somewhere in a text field.
    """
    try:
        file.read(None).close(None)
    except GLib.Error as e:
        logging.debug("Offering %s as a uri: %s", file.get_uri(), e.message)
    else:
        return Gdk.ContentProvider.new_for_value(
            Gdk.FileList.new_from_list([file])
        )

    uri = file.get_uri()
    return Gdk.ContentProvider.new_union(
        [
            Gdk.ContentProvider.new_for_bytes(
                "x-special/gnome-copied-files",
                GLib.Bytes.new(f"copy\n{uri}".encode()),
            ),
            Gdk.ContentProvider.new_for_bytes(
                "text/uri-list", GLib.Bytes.new(f"{uri}\r\n".encode())
            ),
            Gdk.ContentProvider.new_for_value(GObject.Value(str, uri)),
        ]
    )


def provider_for(slot) -> Gdk.ContentProvider | None:
    """Everything a slot needs to become a clipboard offer, or None.

    None means the slot cannot be pasted at all: an empty one, or an image
    whose file no longer reads.
    """
    if slot.text:
        return text_provider(slot.text)

    if slot.filename:
        path = str(image_path(slot.filename))
        try:
            texture = Gdk.Texture.new_from_filename(path)
        except GLib.Error as e:
            logging.warning("Could not load %s: %s", path, e.message)
            return None
        return texture_provider(texture)

    if slot.uri:
        return file_provider(Gio.File.new_for_uri(slot.uri))

    return None
