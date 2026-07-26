# Copyright 2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import dataclass


@dataclass
class SlotData:
    text: str = ""
    filename: str = ""
    pin_status: str = ""
    timestamp: str = ""
    mime: str = ""

    @property
    def is_pinned(self) -> bool:
        return self.pin_status == "pinned"

    @property
    def is_empty(self) -> bool:
        return not self.text and not self.filename

    @classmethod
    def from_list(cls, raw: list[str]) -> "SlotData":
        """Convert a raw GSettings list to SlotData.

        Tolerates short lists: slots stored before a field existed simply
        come back empty.
        """

        def safe(val) -> str:
            return str(val) if val is not None else ""

        return cls(
            text=safe(raw[0]) if raw else "",
            filename=safe(raw[1]) if len(raw) > 1 else "",
            pin_status=safe(raw[2]) if len(raw) > 2 else "",
            timestamp=safe(raw[3]) if len(raw) > 3 else "",
            mime=safe(raw[4]) if len(raw) > 4 else "",
        )

    def to_list(self) -> list[str]:
        """Serialize for GSettings storage."""
        return [
            self.text,
            self.filename,
            self.pin_status,
            self.timestamp,
            self.mime,
        ]
