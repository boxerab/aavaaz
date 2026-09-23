"""
JWT-based authentication and API key access control for Aavaaz REST API.

Two token flavours are accepted: HS256 signed with ``AAVAAZ_JWT_SECRET``, and
RS256 verified against the JWKS of an identity provider (Cognito, Keycloak,
Auth0, Okta) configured through ``AAVAAZ_JWT_JWKS_URL`` / ``AAVAAZ_JWT_ISSUER``
/ ``AAVAAZ_JWT_AUDIENCE``.
"""

import json
import logging
import os
import time
import urllib.request
from http import HTTPStatus

import jwt
from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

_security = HTTPBearer(auto_error=False)

JWT_SECRET_ENV = "AAVAAZ_JWT_SECRET"

# Marker a browser offers as `new WebSocket(url, ["bearer", token])`.
BEARER_SUBPROTOCOL = "bearer"

_BEARER_SCHEME = "Bearer "
_WEBSOCKET_UNAUTHORIZED_BODY = "Unauthorized\n"
_PLATFORM_REQUIRED_CLAIMS = ["exp", "sub"]
# geolang mcp, geolang tool and agora feed tokens, in that order
_OTHER_SERVICE_TOKEN_CLAIMS = ("geolang_use", "token_use", "agora_use")

# HS256 signs with the secret itself, so a short one is worth guessing offline.
# The rest of the platform refuses to start under this, and a gate that is weaker
# than the services behind it protects nothing.
MINIMUM_JWT_SECRET_BYTES = 32

# Default secret — MUST be overridden via AAVAAZ_JWT_SECRET env var
_JWT_SECRET = os.environ.get(JWT_SECRET_ENV, "")
_JWT_ALGORITHM = "HS256"
_JWKS_ALGORITHM = "RS256"
_JWKS_FETCH_TIMEOUT_SECONDS = 5
_API_KEYS: set[str] = set()

_JWKS_URL = os.environ.get("AAVAAZ_JWT_JWKS_URL", "")
_JWT_ISSUER = os.environ.get("AAVAAZ_JWT_ISSUER", "")
_JWT_AUDIENCE = os.environ.get("AAVAAZ_JWT_AUDIENCE", "")
_jwks_keys: dict[str, jwt.PyJWK] = {}


def configure_auth(jwt_secret: str, api_keys: list[str] | None = None):
    """Configure authentication settings."""
    global _JWT_SECRET, _API_KEYS
    _JWT_SECRET = jwt_secret
    if api_keys:
        _API_KEYS = set(api_keys)


def configure_jwks(jwks_url: str, issuer: str = "", audience: str = ""):
    """Point RS256 verification at an identity provider's JWKS endpoint."""
    global _JWKS_URL, _JWT_ISSUER, _JWT_AUDIENCE
    _JWKS_URL = jwks_url
    _JWT_ISSUER = issuer
    _JWT_AUDIENCE = audience
    _jwks_keys.clear()


def _fetch_jwks() -> dict:
    with urllib.request.urlopen(_JWKS_URL, timeout=_JWKS_FETCH_TIMEOUT_SECONDS) as response:
        return json.loads(response.read())


def _signing_key(kid: str) -> jwt.PyJWK:
    """Return the JWKS key for a kid, re-fetching the key set if it is unknown."""
    if kid not in _jwks_keys:
        _jwks_keys.clear()
        for key in jwt.PyJWKSet.from_dict(_fetch_jwks()).keys:
            _jwks_keys[key.key_id] = key
    key = _jwks_keys.get(kid)
    if key is None:
        raise jwt.InvalidTokenError(f"No JWKS key for kid '{kid}'")
    return key


def _verify_jwks_token(token: str) -> dict:
    if not _JWKS_URL:
        raise jwt.InvalidTokenError("RS256 token received but AAVAAZ_JWT_JWKS_URL is not set")
    key = _signing_key(jwt.get_unverified_header(token).get("kid", ""))
    return jwt.decode(
        token,
        key.key,
        algorithms=[_JWKS_ALGORITHM],
        issuer=_JWT_ISSUER or None,
        audience=_JWT_AUDIENCE or None,
        options={"verify_aud": bool(_JWT_AUDIENCE)},
    )


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
    """Verify and decode a JWT token, by JWKS for RS256 and by secret otherwise."""
    if jwt.get_unverified_header(token).get("alg") == _JWKS_ALGORITHM:
        return _verify_jwks_token(token)
    if not _JWT_SECRET:
        raise ValueError("JWT secret not configured")
    return verify_platform_token(token, _JWT_SECRET)


def _websocket_token(headers) -> str | None:
    """The token on a websocket handshake.

    A browser cannot set a header on a handshake, so it offers the token as the
    second subprotocol after the ``bearer`` marker. Non-browser clients may send
    an ``Authorization`` header instead.
    """
    authorization = headers.get("Authorization", "")
    if authorization.startswith(_BEARER_SCHEME):
        return authorization[len(_BEARER_SCHEME):] or None
    marker, _, token = headers.get("Sec-WebSocket-Protocol", "").partition(",")
    if marker.strip() != BEARER_SUBPROTOCOL:
        return None
    return token.strip() or None


def verify_platform_token(token: str, secret: str) -> dict:
    """Verify a platform token: HS256, ``exp`` and ``sub`` required, no ``aud``.

    Every platform service validates the same way, so a session token minted for
    another service, which carries an ``aud``, cannot be replayed here even
    though both are signed with the shared secret.
    """
    claims = jwt.decode(
        token,
        secret,
        algorithms=[_JWT_ALGORITHM],
        options={"require": _PLATFORM_REQUIRED_CLAIMS, "verify_aud": False},
    )
    if "aud" in claims:
        raise jwt.InvalidAudienceError("a platform token carries no aud")
    if not claims["sub"]:
        raise jwt.InvalidTokenError("the token names no subject")
    if any(claim in claims for claim in _OTHER_SERVICE_TOKEN_CLAIMS):
        raise jwt.InvalidTokenError("the token is scoped to another service")
    return claims


def websocket_platform_auth(secret: str):
    """Build the WhisperLive ``websocket_auth`` callable for a shared secret."""

    def check(connection, request):
        token = _websocket_token(request.headers)
        try:
            if token is None:
                raise jwt.InvalidTokenError("no bearer token offered")
            verify_platform_token(token, secret)
        except jwt.InvalidTokenError:
            # no reason in the response, it would separate expired from wrongly signed
            return connection.respond(HTTPStatus.UNAUTHORIZED, _WEBSOCKET_UNAUTHORIZED_BODY)
        return None

    return check


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(_security),
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
