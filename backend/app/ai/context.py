"""Shared bounds and delimiters for user-controlled generative AI context."""

import re


MAX_GENERATIVE_CONTEXT_CHARS = 200_000

SENSITIVE_FIELD_NAMES = (
    "password|passwd|api[_-]?key|client[_-]?secret|access[_-]?token|"
    "refresh[_-]?token|session[_-]?token|private[_-]?key"
)

SENSITIVE_HEADER_NAMES = (
    "authorization|proxy-authorization|cookie|set-cookie|x-api-key|api-key|"
    "x-auth-token"
)
PRIVATE_KEY_MARKERS = tuple(
    (
        f"-----BEGIN {key_type}PRIVATE KEY-----",
        f"-----END {key_type}PRIVATE KEY-----",
    )
    for key_type in ("", "RSA ", "EC ", "OPENSSH ")
)


def _redact_private_keys(content: str) -> str:
    pieces = []
    cursor = 0
    while cursor < len(content):
        starts = [
            (content.find(begin, cursor), begin, end)
            for begin, end in PRIVATE_KEY_MARKERS
        ]
        starts = [item for item in starts if item[0] >= 0]
        if not starts:
            pieces.append(content[cursor:])
            break
        start, begin, end = min(starts, key=lambda item: item[0])
        end_at = content.find(end, start + len(begin))
        if end_at < 0:
            pieces.append(content[cursor:])
            break
        pieces.append(content[cursor:start])
        pieces.append("[REDACTED_PRIVATE_KEY]")
        cursor = end_at + len(end)
    return "".join(pieces)


class AIContextTooLarge(ValueError):
    """Raised before provider use when a generative request is oversized."""


def redact_sensitive_text(content: str) -> str:
    """Conservatively remove common credentials while preserving security context."""
    redacted = re.sub(
        rf"(?im)(^|[ \t\"'])((?:{SENSITIVE_HEADER_NAMES})[ \t]*:[ \t]*)[^\r\n]*",
        r"\1\2[REDACTED]",
        content,
    )
    redacted = re.sub(
        rf"(?i)([\"'](?:{SENSITIVE_FIELD_NAMES})[\"']\s*:\s*[\"'])(.*?)([\"'])",
        r"\1[REDACTED]\3",
        redacted,
    )
    redacted = re.sub(
        rf"(?im)^(\s*(?:{SENSITIVE_FIELD_NAMES})\s*=\s*)[^\r\n]+",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)([?&](?:access_token|api_key|token|key|secret|password)=)[^&#\s]+",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
        "[REDACTED_AWS_ACCESS_KEY]",
        redacted,
    )
    redacted = re.sub(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b",
        "[REDACTED_JWT]",
        redacted,
    )
    return _redact_private_keys(redacted)


def build_bounded_untrusted_context(
    tag: str,
    content: str,
    *,
    label: str,
    max_chars: int = MAX_GENERATIVE_CONTEXT_CHARS,
    redact_sensitive: bool | None = None,
) -> str:
    if not re.fullmatch(r"[a-z0-9_]+", tag):
        raise ValueError("Invalid untrusted-context tag")
    if len(content) > max_chars:
        raise AIContextTooLarge(
            f"{label} exceeds the {max_chars:,}-character AI context limit"
        )
    if redact_sensitive is None:
        from app.config import settings

        redact_sensitive = settings.ai_redact_sensitive_data
    if redact_sensitive:
        content = redact_sensitive_text(content)
    return f"<{tag}>\n{content}\n</{tag}>"
