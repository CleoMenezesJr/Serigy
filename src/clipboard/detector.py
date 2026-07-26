# Copyright 2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

"""Clipboard change detection, kept free of GDK so it can be tested.

Wayland only tells a focused client that the selection changed, so copies
made in the background have to be inferred from what the clipboard object
still exposes. Three of those inferences used to be dead ends: a cancelled
sentinel, an image sitting on the clipboard, and a read that stopped working.
"""

from dataclasses import dataclass
from enum import Enum, auto

# Reading a texture receives and decodes the whole image, so ration it.
IMAGE_PROBE_TICKS = 3

# Reads fail transiently while the source app is busy; a streak does not.
PROBE_FAILURES_BEFORE_TRIGGER = 2


class Action(Enum):
    NOTHING = auto()
    # Claim the clipboard: another app copying then cancels our data
    # source, the only notification an unfocused app gets.
    WRITE_SENTINEL = auto()
    # Wake the capture window, which takes focus and reads for real.
    TRIGGER_CAPTURE = auto()
    PROBE_LOCAL = auto()
    PROBE_TEXT = auto()
    PROBE_TEXTURE = auto()


@dataclass(frozen=True)
class ClipboardState:
    is_local: bool
    formats: str
    last_formats: str
    sentinel_written: bool
    image_tick: int = 0

    @property
    def is_empty(self) -> bool:
        return self.formats == ""

    @property
    def has_text(self) -> bool:
        return "text/plain" in self.formats


def decide(state: ClipboardState) -> Action:
    if state.is_local:
        return _decide_local(state)

    if state.formats != state.last_formats:
        return Action.TRIGGER_CAPTURE

    if state.is_empty:
        return Action.WRITE_SENTINEL

    if state.has_text:
        return Action.PROBE_TEXT

    if (state.image_tick + 1) % IMAGE_PROBE_TICKS == 0:
        return Action.PROBE_TEXTURE
    return Action.NOTHING


def _decide_local(state: ClipboardState) -> Action:
    if not state.is_empty:
        # We copied a slot out ourselves.
        return Action.PROBE_LOCAL

    if state.sentinel_written:
        # wl_data_source.cancelled: GDK leaves the clipboard local with
        # NULL content, where every read fails and polling never recovers.
        # Another client took the selection, so go look at it.
        return Action.TRIGGER_CAPTURE

    return Action.WRITE_SENTINEL


def probe_failure_is_conclusive(
    failures: int, already_triggered: bool = False
) -> bool:
    """A read that stops working is the only proof the selection moved.

    Format negotiation stays live without focus, so failure means the
    advertised formats no longer describe reality.

    Once per episode, though: an owner that quit leaves formats nothing can
    read, and the capture window has already looked. Triggering again every
    tick would steal focus once a second forever.
    """
    if already_triggered:
        return False
    return failures >= PROBE_FAILURES_BEFORE_TRIGGER
