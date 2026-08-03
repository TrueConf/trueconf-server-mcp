"""Logging helpers: token masking for safe INFO-level logs."""


def mask_token(token: str) -> str:
    """Mask a token for logging: first 6 + '...' + last 4 chars.

    Short tokens (fewer than 10 chars) are fully masked as '***'.
    """
    if len(token) < 10:
        return "***"
    return f"{token[:6]}...{token[-4:]}"
