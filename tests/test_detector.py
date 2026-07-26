# Copyright 2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

"""Regression tests for clipboard change detection.

Every test named `test_dead_end_*` pins down a state the monitor used to
enter and never leave, which is what made captures stop depending on
whether the last copy had been text or an image.
"""

import importlib.util
import os
import unittest

# Loaded straight from its file: importing serigy.clipboard would pull in
# the GDK-backed modules, and the whole point of this one is that it needs
# no display, no compositor and no GTK to be exercised.
_SPEC = importlib.util.spec_from_file_location(
    "serigy_detector",
    os.path.join(
        os.path.dirname(__file__), "..", "src", "clipboard", "detector.py"
    ),
)
detector = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(detector)

IMAGE_PROBE_TICKS = detector.IMAGE_PROBE_TICKS
Action = detector.Action
ClipboardState = detector.ClipboardState
decide = detector.decide
probe_failure_is_conclusive = detector.probe_failure_is_conclusive

TEXT = "gchararray text/plain text/plain;charset=utf-8"
IMAGE = "GdkTexture GdkPixbuf image/png"


def state(**kwargs) -> ClipboardState:
    defaults = {
        "is_local": False,
        "formats": TEXT,
        "last_formats": TEXT,
        "sentinel_written": False,
    }
    return ClipboardState(**{**defaults, **kwargs})


class TestDeadEnds(unittest.TestCase):
    """The three states that used to swallow copies forever."""

    def test_dead_end_cancelled_sentinel_wakes_the_capture_window(self):
        # After wl_data_source.cancelled GDK reports the clipboard as
        # local with NULL content. Reads fail forever; the old code
        # probed, gave up and returned, so every later copy was lost.
        self.assertEqual(
            decide(
                state(
                    is_local=True,
                    formats="",
                    last_formats=TEXT,
                    sentinel_written=True,
                )
            ),
            Action.TRIGGER_CAPTURE,
        )

    def test_dead_end_local_and_empty_rearms_the_sentinel(self):
        # Same local-and-empty state but with no sentinel outstanding:
        # nothing was copied, we are simply deaf until we claim the
        # clipboard again.
        self.assertEqual(
            decide(state(is_local=True, formats="", sentinel_written=False)),
            Action.WRITE_SENTINEL,
        )

    def test_dead_end_image_on_clipboard_still_has_a_detector(self):
        # Non-empty, non-text formats used to reach a branch that did
        # nothing at all, so a copy made after an image was invisible.
        action = decide(
            state(
                formats=IMAGE,
                last_formats=IMAGE,
                image_tick=IMAGE_PROBE_TICKS - 1,
            )
        )
        self.assertEqual(action, Action.PROBE_TEXTURE)

    def test_dead_end_failed_probe_triggers_instead_of_latching(self):
        # A failed read used to set a latch that only a `changed` signal
        # could clear — and that signal never arrives without focus.
        self.assertFalse(probe_failure_is_conclusive(1))
        self.assertTrue(probe_failure_is_conclusive(2))


class TestNormalOperation(unittest.TestCase):
    def test_format_change_triggers_capture(self):
        self.assertEqual(
            decide(state(formats=IMAGE, last_formats=TEXT)),
            Action.TRIGGER_CAPTURE,
        )

    def test_text_on_clipboard_is_polled_by_hash(self):
        self.assertEqual(decide(state()), Action.PROBE_TEXT)

    def test_empty_and_unowned_claims_the_clipboard(self):
        self.assertEqual(
            decide(state(formats="", last_formats="")),
            Action.WRITE_SENTINEL,
        )

    def test_our_own_copy_out_is_probed_not_captured(self):
        # Copying a slot out makes us the owner with real content; that
        # must not be re-captured as if the user had copied it.
        self.assertEqual(
            decide(state(is_local=True, formats=TEXT)), Action.PROBE_LOCAL
        )

    def test_texture_probe_is_rationed_across_ticks(self):
        actions = [
            decide(state(formats=IMAGE, last_formats=IMAGE, image_tick=tick))
            for tick in range(IMAGE_PROBE_TICKS)
        ]
        self.assertEqual(actions.count(Action.PROBE_TEXTURE), 1)
        self.assertEqual(actions.count(Action.NOTHING), IMAGE_PROBE_TICKS - 1)


if __name__ == "__main__":
    unittest.main()
