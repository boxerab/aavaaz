"""
JWT-based authentication and API key access control for Aavaaz REST API.
"""

import hashlib
import hmac
import logging
import os
import time
from typing import Optional

import jwt
from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

_security = HTTPBearer(auto_error=False)

# Default secret — MUST be overridden via AAVAAZ_JWT_SECRET env var
_JWT_SECRET = os.environ.get("AAVAAZ_JWT_SECRET", "")
_JWT_ALGORITHM = "HS256"
_API_KEYS: set[str] = set()


def configure_auth(jwt_secret: str, api_keys: Optional[list[str]] = None):
    """Configure authentication settings."""
    global _JWT_SECRET, _API_KEYS
    _JWT_SECRET = jwt_secret
    if api_keys:
        _API_KEYS = set(api_keys)


def create_token(subject: str, expires_in: int = 3600, **claims) -> str:
    """Create a signed JWT token."""
    if not _JWT_SECRET:
        raise ValueError("JWT secret not configured — set AAVAAZ_JWT_SECRET")
    payload = {
        "sub": subject,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in,
        **claims,
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """Verify and decode a JWT token."""
    if not _JWT_SECRET:
        raise ValueError("JWT secret not configured")
    return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])


async def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_security),
) -> dict:
    """FastAPI dependency that requires valid authentication.

    Supports both JWT bearer tokens and API keys (via X-API-Key header).
    """
    # Check API key header first
    api_key = request.headers.get("X-API-Key")
    if api_key and api_key in _API_KEYS:
        return {"sub": "api_key", "key": api_key}

    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        return verify_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
