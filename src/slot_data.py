# Copyright 2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import dataclass


@dataclass
class SlotData:
    text: str = ""
    filename: str = ""
    pin_status: str = ""
    timestamp: str = ""

    @property
    def is_pinned(self) -> bool:
        return self.pin_status == "pinned"

    @property
    def is_empty(self) -> bool:
        return not self.text and not self.filename

    @classmethod
    def from_list(cls, raw: list[str]) -> "SlotData":
        """Convert a raw GSettings list to SlotData. Safe with short/None values."""

        def safe(val) -> str:
            return str(val) if val is not None else ""

        return cls(
            text=safe(raw[0]) if len(raw) > 0 else "",
            filename=safe(raw[1]) if len(raw) > 1 else "",
            pin_status=safe(raw[2]) if len(raw) > 2 else "",
            timestamp=safe(raw[3]) if len(raw) > 3 else "",
        )

    def to_list(self) -> list[str]:
        """Serialize to a 4-element list for GSettings storage."""
        return [self.text, self.filename, self.pin_status, self.timestamp]

