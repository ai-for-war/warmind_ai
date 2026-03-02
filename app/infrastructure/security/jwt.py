"""JWT token utilities using python-jose."""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config.settings import get_settings


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create JWT access token with expiration.

    Args:
        data: Payload data to encode in the token
        expires_delta: Optional custom expiration time delta.
                      Defaults to JWT_EXPIRATION_DAYS from settings.

    Returns:
        Encoded JWT token string
    """
    settings = get_settings()

    to_encode = data.copy()
    now = datetime.now(timezone.utc)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.JWT_EXPIRATION_DAYS)

    to_encode.update(
        {
            "exp": expire,
            "iat": now,
        }
    )

    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    """Decode and verify JWT token.

    Args:
        token: JWT token string to decode

    Returns:
        Decoded token payload as dictionary

    Raises:
        JWTError: If token is invalid or expired
    """
    settings = get_settings()

    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
