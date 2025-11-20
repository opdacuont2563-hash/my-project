"""
Security utilities for authentication and data protection.
Includes token validation, HN masking, and encryption helpers.
"""

import hashlib
import secrets
from typing import Optional

from ..config import get_settings


def mask_hn(hn: Optional[str]) -> Optional[str]:
    """
    Mask Hospital Number for display.
    Shows first 6 digits + XXX (e.g., 590166XXX).

    Args:
        hn: Hospital Number (9 digits)

    Returns:
        Masked HN string or original if invalid
    """
    if not hn or not isinstance(hn, str):
        return hn

    hn = hn.strip()
    if len(hn) < 3:
        return hn

    # Standard masking: show first 6, mask last 3
    if len(hn) >= 6:
        return hn[:6] + "XXX"

    # Fallback: mask last 3 characters
    return hn[:-3] + "XXX"


def validate_token(token: str) -> bool:
    """
    Validate authentication token.

    Args:
        token: Token to validate

    Returns:
        True if token is valid, False otherwise
    """
    if not token or not isinstance(token, str):
        return False

    settings = get_settings()
    return token.strip() == settings.surgibot_secret


def generate_token(length: int = 64) -> str:
    """
    Generate a secure random token.

    Args:
        length: Token length in characters

    Returns:
        Secure random token string
    """
    return secrets.token_urlsafe(length)


def hash_hn(hn: str, salt: Optional[str] = None) -> str:
    """
    Create a secure hash of Hospital Number for indexing/lookup.

    Args:
        hn: Hospital Number
        salt: Optional salt value

    Returns:
        Hashed HN string
    """
    if not salt:
        settings = get_settings()
        salt = settings.surgibot_secret

    combined = f"{hn}{salt}"
    return hashlib.sha256(combined.encode()).hexdigest()


def verify_hn_hash(hn: str, hn_hash: str, salt: Optional[str] = None) -> bool:
    """
    Verify Hospital Number against its hash.

    Args:
        hn: Hospital Number to verify
        hn_hash: Hash to verify against
        salt: Optional salt value

    Returns:
        True if hash matches, False otherwise
    """
    computed_hash = hash_hn(hn, salt)
    return secrets.compare_digest(computed_hash, hn_hash)


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


class AuthorizationError(Exception):
    """Raised when authorization fails."""

    pass
