"""Socket Gateway JWT authentication module."""

from urllib.parse import parse_qs

from jose import JWTError

from app.infrastructure.security.jwt import decode_access_token


def _extract_token_from_query(environ: dict) -> str | None:
    """Extract token from query string.

    Args:
        environ: WSGI environ dict from connection

    Returns:
        Token string if found, None otherwise
    """
    query_string = environ.get("QUERY_STRING", "")
    params = parse_qs(query_string)
    tokens = params.get("token", [])
    return tokens[0] if tokens else None


async def authenticate(auth: dict | None, environ: dict | None = None) -> dict | None:
    """Validate JWT token from socket auth object or query params.

    Token is extracted from:
    1. auth object: {"token": "jwt-string"} (preferred)
    2. query params: ?token=jwt-string (fallback for Postman testing)

    Args:
        auth: Auth object from client connection
        environ: WSGI environ dict (optional, for query param fallback)

    Returns:
        {"user_id": str} if valid, None if invalid/missing/expired
    """
    token = None

    # Try auth object first
    if auth is not None:
        token = auth.get("token")

    # Fallback to query params if no token in auth
    if not token and environ is not None:
        token = _extract_token_from_query(environ)

    if not token:
        return None

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
        return {"user_id": user_id}
    except JWTError:
        return None
