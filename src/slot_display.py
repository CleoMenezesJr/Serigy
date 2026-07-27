# Copyright 2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

"""How a slot is worded wherever it is shown.

The card in the grid and the result in the shell overview describe the same
slot, so the wording lives here instead of inside whichever widget needed it
first.
"""

import time
from gettext import gettext as _


def relative_time(timestamp: str) -> str:
    """Turn a stored epoch into how long ago it was."""
    if not timestamp:
        return ""

    try:
        ts: int = int(timestamp)
    except ValueError:
        return ""

    diff: int = int(time.time()) - ts
    if diff < 60:
        return _("Just now")
    if diff < 3600:
        return _("{} min ago").format(diff // 60)
    if diff < 86400:
        return _("{} hr ago").format(diff // 3600)
    return _("{} days ago").format(diff // 86400)


def summary(text: str, limit: int = 60) -> str:
    """One line standing in for a whole copy.

    A result row shows a single line of a fixed width, so the newlines and
    the runs of blanks that survive a copy would only spend room.
    """
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"
