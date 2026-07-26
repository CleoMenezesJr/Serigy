# Copyright 2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

"""On-disk storage for clipboard images.

Images used to be written to the cache directory, which the system is free to
sweep at any time, so a purge silently emptied slots the user had pinned.
They now live in the data directory, and whatever the sweep left behind is
moved there on startup.
"""

import logging
import shutil
from collections.abc import Iterable
from pathlib import Path


def images_dir() -> Path:
    # GLib is imported per call so this module stays importable without a GI
    # stack; nothing in it needs GTK.
    from gi.repository import GLib

    return Path(GLib.get_user_data_dir()) / "serigy" / "images"


def legacy_dir() -> Path:
    from gi.repository import GLib

    return Path(GLib.get_user_cache_dir()) / "tmp"


def image_path(filename: str) -> Path:
    """Where `filename` lives.

    Falls back to the pre-migration location so an image that could not be
    moved is still readable instead of lost.
    """
    path = images_dir() / filename
    if not path.exists() and (legacy_dir() / filename).exists():
        return legacy_dir() / filename
    return path


def store_image(pixbuf, filename: str) -> bool:
    """Write `pixbuf` as `filename`, reporting whether it ended up on disk."""
    path = images_dir() / filename
    if path.exists():
        return True

    fmt = filename.rsplit(".", 1)[-1] if "." in filename else "png"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        pixbuf.savev(str(path), fmt, [], [])
    except Exception as e:
        logging.error("Failed to save clipboard image %s: %s", filename, e)
        return False
    return True


def remove_image(filename: str, keep: Iterable[str] = ()) -> None:
    """Delete `filename`, unless something in `keep` still names it.

    The filename is the content hash, so two slots holding the same image
    share one file on disk and clearing one of them must not blank the other.
    """
    if not filename or filename in set(keep):
        return

    for path in (images_dir() / filename, legacy_dir() / filename):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            logging.warning("Could not remove %s: %s", path, e)


def migrate(filenames: Iterable[str]) -> set[str]:
    """Move still-cached images into the data directory.

    Returns the names found in neither location: a cache purge already took
    those, and their slots would sit there unable to render.
    """
    target = images_dir()
    legacy = legacy_dir()
    missing: set[str] = set()

    for filename in filenames:
        if not filename or (target / filename).exists():
            continue

        source = legacy / filename
        if not source.exists():
            missing.add(filename)
            continue

        try:
            target.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target / filename))
        except OSError as e:
            logging.warning("Could not migrate %s: %s", filename, e)

    return missing
