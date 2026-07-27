# Copyright 2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

"""Which slots answer a shell search, and how a result names one.

Free of GTK and of GSettings on purpose: it takes slots and terms and gives
back ids, which is all the D-Bus layer passes on and all a test needs.
"""

import hashlib
import unicodedata
from urllib.parse import unquote

APP_NAME = "serigy"

# Searching the app by name lists the whole history. One letter would do
# that on the first keystroke of most searches in the overview, so the
# listing waits until the typing looks deliberate.
APP_NAME_MIN_CHARS = 3

_ID_LENGTH = 16


def normalize(text: str) -> str:
    """Fold case and drop accents, so "manutenção" answers "manutencao"."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def basename(uri: str) -> str:
    """The file name a uri ends in, as a person would read it."""
    return unquote(uri.rsplit("/", 1)[-1])


def is_app_name_query(terms: list[str]) -> bool:
    """Is the user typing the app's name rather than looking for content?"""
    if len(terms) != 1:
        return False
    term = normalize(terms[0])
    return len(term) >= APP_NAME_MIN_CHARS and APP_NAME.startswith(term)


def _haystack(slot) -> str:
    """Everything of a slot a term is allowed to match.

    An image has no words of its own; the cached file name is a hash, and
    matching it would only produce results nobody asked for.
    """
    parts = [slot.text]
    if slot.uri:
        parts.append(basename(slot.uri))
    return normalize(" ".join(part for part in parts if part))


def matches(slot, terms: list[str]) -> bool:
    """Every term has to be found; the overview splits on blanks."""
    wanted = [normalize(term) for term in terms if term]
    if not wanted:
        return False
    hay = _haystack(slot)
    return all(term in hay for term in wanted)


def slot_id(slot) -> str:
    """A name for a slot that survives the grid moving underneath it.

    A position would not: a copy landing between the keystroke and the
    Enter shifts every slot by one, and the user would activate a
    neighbour.
    """
    if slot.text:
        return f"t:{_digest(slot.text)}"
    if slot.filename:
        return f"i:{_digest(slot.filename)}"
    if slot.uri:
        return f"f:{_digest(slot.uri)}"
    return ""


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:_ID_LENGTH]


def result_ids(slots, terms: list[str]) -> list[str]:
    """The ids to hand the shell, in grid order, which is recency order."""
    if is_app_name_query(terms):
        chosen = [slot for slot in slots if not slot.is_empty]
    else:
        chosen = [
            slot
            for slot in slots
            if not slot.is_empty and matches(slot, terms)
        ]

    # Two slots holding the same copy share an id, and a list with it twice
    # would ask the shell to draw one result twice.
    seen: set[str] = set()
    ids: list[str] = []
    for slot in chosen:
        identifier = slot_id(slot)
        if identifier and identifier not in seen:
            seen.add(identifier)
            ids.append(identifier)
    return ids


def find(slots, result_id: str):
    """The slot an id names, or None once it has rotated out."""
    if not result_id:
        return None
    for slot in slots:
        if slot_id(slot) == result_id:
            return slot
    return None
