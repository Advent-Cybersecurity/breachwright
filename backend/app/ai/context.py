"""Shared bounds and delimiters for user-controlled generative AI context."""

import re


MAX_GENERATIVE_CONTEXT_CHARS = 200_000


class AIContextTooLarge(ValueError):
    """Raised before provider use when a generative request is oversized."""


def build_bounded_untrusted_context(
    tag: str,
    content: str,
    *,
    label: str,
    max_chars: int = MAX_GENERATIVE_CONTEXT_CHARS,
) -> str:
    if not re.fullmatch(r"[a-z0-9_]+", tag):
        raise ValueError("Invalid untrusted-context tag")
    if len(content) > max_chars:
        raise AIContextTooLarge(
            f"{label} exceeds the {max_chars:,}-character AI context limit"
        )
    return f"<{tag}>\n{content}\n</{tag}>"
