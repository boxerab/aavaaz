"""Integration tests for the auth module."""

from unittest.mock import MagicMock

import pytest

from aavaaz.api.auth import configure_auth, create_token, require_auth, verify_token


class TestJWT:
    def setup_method(self):
        configure_auth("test-secret-key", api_keys=["key-123"])

    def test_create_and_verify_token(self):
        token = create_token("user1", expires_in=3600)
        payload = verify_token(token)
        assert payload["sub"] == "user1"

    def test_expired_token(self):
        import jwt as pyjwt

        token = create_token("user1", expires_in=-1)
        with pytest.raises(pyjwt.ExpiredSignatureError):
            verify_token(token)

    def test_invalid_token(self):
        import jwt as pyjwt

        with pytest.raises(pyjwt.InvalidTokenError):
            verify_token("not.a.valid.token")

    def test_custom_claims(self):
        token = create_token("user1", role="admin")
        payload = verify_token(token)
        assert payload["role"] == "admin"

    def test_no_secret_raises(self):
        configure_auth("", api_keys=[])
        with pytest.raises(ValueError):
            create_token("user1")


class TestRequireAuth:
    def setup_method(self):
        configure_auth("test-secret", api_keys=["valid-key"])

    @pytest.mark.asyncio
    async def test_api_key_auth(self):
        request = MagicMock()
        request.headers = {"X-API-Key": "valid-key"}
        result = await require_auth(request, credentials=None)
        assert result["sub"] == "api_key"

    @pytest.mark.asyncio
    async def test_bearer_token_auth(self):
        from fastapi.security import HTTPAuthorizationCredentials

        token = create_token("testuser")
        request = MagicMock()
        request.headers = {}
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        result = await require_auth(request, credentials=creds)
        assert result["sub"] == "testuser"

    @pytest.mark.asyncio
    async def test_no_credentials_raises_401(self):
        from fastapi import HTTPException

        request = MagicMock()
        request.headers = {}
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(request, credentials=None)
        assert exc_info.value.status_code == 401


class TestJwksVerification:
    """RS256 verification against a provider JWKS, with the HTTP fetch mocked."""

    JWKS_URL = "https://idp.example.com/.well-known/jwks.json"
    ISSUER = "https://idp.example.com/realms/aavaaz"
    AUDIENCE = "aavaaz-dashboard"

    @pytest.fixture(autouse=True)
    def _restore_jwks(self):
        from aavaaz.api import auth

        previous = (auth._JWKS_URL, auth._JWT_ISSUER, auth._JWT_AUDIENCE)
        configure_auth("hs256-secret-for-the-other-branch")
        yield
        auth.configure_jwks(*previous)

    @staticmethod
    def _private_key():
        from cryptography.hazmat.primitives.asymmetric import rsa

        return rsa.generate_private_key(public_exponent=65537, key_size=2048)

    @staticmethod
    def _jwk(private_key, kid):
        import json

        import jwt as pyjwt

        jwk = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
        jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
        return jwk

    @staticmethod
    def _serve_jwks(keys_by_call):
        """Patch the JWKS fetch, returning the recorded request URLs.

        `keys_by_call` is a list of key lists, one per expected fetch.
        """
        import json
        from unittest.mock import patch

        calls = []

        class _Response:
            def __init__(self, payload):
                self._payload = payload

            def read(self):
                return json.dumps(self._payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

        def _urlopen(url, timeout=None):
            keys = keys_by_call[min(len(calls), len(keys_by_call) - 1)]
            calls.append(url)
            return _Response({"keys": keys})

        return patch("aavaaz.api.auth.urllib.request.urlopen", _urlopen), calls

    def _token(self, private_key, kid, **overrides):
        import time

        import jwt as pyjwt

        payload = {
            "sub": "sso-user",
            "email": "sso@example.com",
            "iss": self.ISSUER,
            "aud": self.AUDIENCE,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        payload.update(overrides)
        return pyjwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})

    def test_rs256_token_verified_end_to_end(self):
        from aavaaz.api import auth

        private_key = self._private_key()
        auth.configure_jwks(self.JWKS_URL, self.ISSUER, self.AUDIENCE)
        served, calls = self._serve_jwks([[self._jwk(private_key, "key-1")]])

        with served:
            claims = verify_token(self._token(private_key, "key-1"))

        assert claims["sub"] == "sso-user"
        assert claims["email"] == "sso@example.com"
        assert calls == [self.JWKS_URL]

    def test_jwks_is_cached_across_tokens(self):
        from aavaaz.api import auth

        private_key = self._private_key()
        auth.configure_jwks(self.JWKS_URL, self.ISSUER, self.AUDIENCE)
        served, calls = self._serve_jwks([[self._jwk(private_key, "key-1")]])

        with served:
            verify_token(self._token(private_key, "key-1"))
            verify_token(self._token(private_key, "key-1"))

        assert len(calls) == 1

    def test_unknown_kid_refetches_the_key_set(self):
        from aavaaz.api import auth

        old_key = self._private_key()
        new_key = self._private_key()
        auth.configure_jwks(self.JWKS_URL, self.ISSUER, self.AUDIENCE)
        served, calls = self._serve_jwks(
            [[self._jwk(old_key, "key-1")], [self._jwk(new_key, "key-2")]]
        )

        with served:
            verify_token(self._token(old_key, "key-1"))
            claims = verify_token(self._token(new_key, "key-2"))

        assert claims["sub"] == "sso-user"
        assert len(calls) == 2

    def test_kid_absent_from_jwks_is_rejected(self):
        import jwt as pyjwt

        from aavaaz.api import auth

        private_key = self._private_key()
        auth.configure_jwks(self.JWKS_URL, self.ISSUER, self.AUDIENCE)
        served, _ = self._serve_jwks([[self._jwk(private_key, "key-1")]])

        with served, pytest.raises(pyjwt.InvalidTokenError):
            verify_token(self._token(private_key, "key-absent"))

    def test_token_signed_by_another_key_is_rejected(self):
        import jwt as pyjwt

        from aavaaz.api import auth

        published_key = self._private_key()
        attacker_key = self._private_key()
        auth.configure_jwks(self.JWKS_URL, self.ISSUER, self.AUDIENCE)
        served, _ = self._serve_jwks([[self._jwk(published_key, "key-1")]])

        with served, pytest.raises(pyjwt.InvalidSignatureError):
            verify_token(self._token(attacker_key, "key-1"))

    def test_wrong_issuer_is_rejected(self):
        import jwt as pyjwt

        from aavaaz.api import auth

        private_key = self._private_key()
        auth.configure_jwks(self.JWKS_URL, self.ISSUER, self.AUDIENCE)
        served, _ = self._serve_jwks([[self._jwk(private_key, "key-1")]])

        with served, pytest.raises(pyjwt.InvalidIssuerError):
            verify_token(self._token(private_key, "key-1", iss="https://evil.example"))

    def test_wrong_audience_is_rejected(self):
        import jwt as pyjwt

        from aavaaz.api import auth

        private_key = self._private_key()
        auth.configure_jwks(self.JWKS_URL, self.ISSUER, self.AUDIENCE)
        served, _ = self._serve_jwks([[self._jwk(private_key, "key-1")]])

        with served, pytest.raises(pyjwt.InvalidAudienceError):
            verify_token(self._token(private_key, "key-1", aud="someone-else"))

    def test_rs256_without_jwks_url_is_rejected(self):
        import jwt as pyjwt

        from aavaaz.api import auth

        private_key = self._private_key()
        auth.configure_jwks("")

        with pytest.raises(pyjwt.InvalidTokenError):
            verify_token(self._token(private_key, "key-1"))

    def test_hs256_still_works_while_jwks_is_configured(self):
        from aavaaz.api import auth

        auth.configure_jwks(self.JWKS_URL, self.ISSUER, self.AUDIENCE)
        configure_auth("test-secret-key")
        assert verify_token(create_token("hs-user"))["sub"] == "hs-user"

    @pytest.mark.asyncio
    async def test_require_auth_accepts_an_rs256_bearer(self):
        from fastapi.security import HTTPAuthorizationCredentials

        from aavaaz.api import auth

        private_key = self._private_key()
        auth.configure_jwks(self.JWKS_URL, self.ISSUER, self.AUDIENCE)
        served, _ = self._serve_jwks([[self._jwk(private_key, "key-1")]])
        request = MagicMock()
        request.headers = {}
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=self._token(private_key, "key-1")
        )

        with served:
            claims = await require_auth(request, credentials=credentials)

        assert claims["sub"] == "sso-user"

    def test_self_host_saas_router_accepts_rs256_bearer(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from aavaaz.api import auth, saas

        private_key = self._private_key()
        auth.configure_jwks(self.JWKS_URL, self.ISSUER, self.AUDIENCE)
        served, _ = self._serve_jwks([[self._jwk(private_key, "key-1")]])

        app = FastAPI()
        app.include_router(saas.router)
        headers = {"Authorization": f"Bearer {self._token(private_key, 'key-1')}"}

        with served:
            response = TestClient(app).get("/v1/saas/subscription", headers=headers)

        assert response.status_code == 200
        assert response.json()["plan"] == "free"
