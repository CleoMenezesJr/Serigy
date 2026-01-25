# Copyright 2026 Cleo Menezes Jr.
# SPDX-License-Identifier: GPL-3.0-or-later

"""Content type detection for clipboard items.

Detection strategy:
1. Check MIME type first (from clipboard metadata if available)
2. Analyze ENTIRE content (not fragments)
3. Use Python native tools (urllib.parse, ast, compiled regex)
"""

import ast
import re
from enum import Enum

from urllib.parse import urlparse


class ContentType(Enum):
    """Clipboard content types with icon mapping."""

    IMAGE = ("image", "image-x-generic-symbolic")
    FILE = ("file", "folder-symbolic")
    LINK = ("link", "web-browser-symbolic")
    EMAIL = ("email", "mail-symbolic")
    PHONE = ("phone", "phone-symbolic")
    COLOR = ("color", "color-picker-symbolic")
    CODE = ("code", "code-symbolic")
    TEXT = ("text", "text-x-generic-symbolic")

    @property
    def icon(self) -> str:
        return self.value[1]

    @property
    def type_id(self) -> str:
        return self.value[0]


# Compiled patterns (loaded once at module import)
_EMAIL = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
_PHONE = re.compile(r"^[\d\s\-+().]{7,20}$")
_COLOR_HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_COLOR_RGB = re.compile(
    r"^rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\)$", re.I
)

# Code detection patterns - language keywords and syntax
_CODE_KEYWORDS = re.compile(
    r"\b(def|class|import|from|return|if|else|elif|for|while|"
    r"function|const|let|var|async|await|try|catch|throw|"
    r"public|private|static|void|int|string|bool)\b"
)
_CODE_SYNTAX = re.compile(
    r"(->|=>|::|&&|\|\||[{}\[\]();])"
)


def detect(text: str, mime: str | None = None) -> ContentType:
    """Detect content type.

    MIME checked first, then heuristics on full content.
    """
    # MIME-based detection
    if mime:
        if mime.startswith("image/"):
            return ContentType.IMAGE
        if mime.startswith("application/"):
            return ContentType.FILE

    text = text.strip()
    if not text:
        return ContentType.TEXT

    # Single-line exact matches (entire content must match)
    if _is_url(text):
        return ContentType.LINK
    if _EMAIL.fullmatch(text):
        return ContentType.EMAIL
    if _PHONE.fullmatch(text.replace(" ", "")):
        return ContentType.PHONE
    if _COLOR_HEX.fullmatch(text) or _COLOR_RGB.fullmatch(text):
        return ContentType.COLOR
    if _is_code(text):
        return ContentType.CODE

    return ContentType.TEXT


def _is_url(text: str) -> bool:
    """Check if entire text is a valid URL."""
    if "\n" in text or " " in text:
        return False
    try:
        parsed = urlparse(text)
        valid_schemes = ("http", "https", "ftp", "file")
        return parsed.scheme in valid_schemes and bool(
            parsed.netloc or parsed.path
        )
    except Exception:
        return False


def _is_code(text: str) -> bool:
    """Detect if text is programming code.

    Uses multiple strategies:
    1. Try to parse as Python AST (catches Python code)
    2. Check for programming keywords
    3. Check for code syntax patterns
    """
    lines = text.split("\n")
    if len(lines) < 2:
        return False

    # Strategy 1: Try to parse as valid Python
    try:
        ast.parse(text)
        # If it parses and has multiple statements, likely code
        return True
    except SyntaxError:
        pass

    # Strategy 2: Check for programming keywords (2+ keywords)
    keyword_matches = len(_CODE_KEYWORDS.findall(text))
    if keyword_matches >= 2:
        return True

    # Strategy 3: Check for code syntax patterns (3+ patterns)
    syntax_matches = len(_CODE_SYNTAX.findall(text))
    if syntax_matches >= 3:
        return True

    return False
