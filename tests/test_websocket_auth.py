"""Tests for the platform JWT check on the transcription websocket."""

import threading
import time
from contextlib import contextmanager
from http import HTTPStatus

import jwt
import pytest
from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect
from websockets.sync.server import serve

from aavaaz.api.auth import (
    BEARER_SUBPROTOCOL,
    JWT_SECRET_ENV,
    MINIMUM_JWT_SECRET_BYTES,
    websocket_platform_auth,
)
from aavaaz.server import AavaazServer

SECRET = "0123456789abcdef0123456789abcdef"
OTHER_SECRET = "ffffffffffffffffffffffffffffffff"
UNAUTHORIZED = (HTTPStatus.UNAUTHORIZED, "Unauthorized\n")


def make_token(secret=SECRET, expires_in=3600, **claims):
    payload = {"sub": "user-1", "exp": int(time.time()) + expires_in, **claims}
    return jwt.encode(payload, secret, algorithm="HS256")


class FakeConnection:
    def respond(self, status, body):
        return (status, body)


class FakeRequest:
    def __init__(self, headers):
        self.headers = headers


def check_headers(headers, secret=SECRET):
    return websocket_platform_auth(secret)(FakeConnection(), FakeRequest(headers))


def subprotocol_offer(token):
    return {"Sec-WebSocket-Protocol": f"{BEARER_SUBPROTOCOL}, {token}"}


def select_bearer(connection, subprotocols):
    return BEARER_SUBPROTOCOL if BEARER_SUBPROTOCOL in subprotocols else None


@contextmanager
def running_socket(secret=SECRET):
    """A websocket server guarded by the same check `aavaaz serve` installs."""

    def echo_subprotocol(connection):
        connection.send(connection.subprotocol or "")

    server = serve(
        echo_subprotocol,
        "127.0.0.1",
        0,
        process_request=websocket_platform_auth(secret),
        select_subprotocol=select_bearer,
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"ws://127.0.0.1:{server.socket.getsockname()[1]}"
    finally:
        server.shutdown()


def test_a_valid_token_connects_and_bearer_is_selected():
    token = make_token()
    with (
        running_socket() as url,
        connect(url, subprotocols=[BEARER_SUBPROTOCOL, token]) as client,
    ):
        assert client.subprotocol == BEARER_SUBPROTOCOL
        assert client.recv() == BEARER_SUBPROTOCOL


def test_a_bad_token_is_refused_on_the_handshake():
    token = make_token(secret=OTHER_SECRET)
    with running_socket() as url, pytest.raises(InvalidStatus) as refusal:
        connect(url, subprotocols=[BEARER_SUBPROTOCOL, token])
    assert refusal.value.response.status_code == HTTPStatus.UNAUTHORIZED


def test_a_valid_subprotocol_offer_passes_the_check():
    assert check_headers(subprotocol_offer(make_token())) is None


def test_an_authorization_header_passes_the_check():
    assert check_headers({"Authorization": f"Bearer {make_token()}"}) is None


def test_an_expired_token_is_refused():
    assert check_headers(subprotocol_offer(make_token(expires_in=-1))) == UNAUTHORIZED


def test_a_token_signed_with_another_secret_is_refused():
    assert check_headers(subprotocol_offer(make_token(secret=OTHER_SECRET))) == UNAUTHORIZED


def test_a_token_carrying_an_audience_is_refused():
    token = make_token(aud="aavaaz-session")
    assert check_headers(subprotocol_offer(token)) == UNAUTHORIZED


def test_a_token_without_a_subject_is_refused():
    for token in (make_token(sub=""), jwt.encode({"exp": 2 ** 31}, SECRET, algorithm="HS256")):
        assert check_headers(subprotocol_offer(token)) == UNAUTHORIZED


def test_a_token_without_an_expiry_is_refused():
    token = jwt.encode({"sub": "user-1"}, SECRET, algorithm="HS256")
    assert check_headers(subprotocol_offer(token)) == UNAUTHORIZED


def test_an_unsigned_token_is_refused():
    token = jwt.encode({"sub": "user-1", "exp": 2 ** 31}, key="", algorithm="none")
    assert check_headers(subprotocol_offer(token)) == UNAUTHORIZED


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Sec-WebSocket-Protocol": BEARER_SUBPROTOCOL},
        {"Sec-WebSocket-Protocol": "bearer, "},
        {"Sec-WebSocket-Protocol": f"{make_token()}, {BEARER_SUBPROTOCOL}"},
        {"Authorization": "Bearer "},
    ],
)
def test_a_handshake_offering_no_token_is_refused(headers):
    assert check_headers(headers) == UNAUTHORIZED


def test_an_unset_secret_leaves_the_socket_open(monkeypatch, caplog):
    monkeypatch.delenv(JWT_SECRET_ENV, raising=False)
    with caplog.at_level("WARNING"):
        assert AavaazServer()._websocket_auth() is None
    assert JWT_SECRET_ENV in caplog.text


def test_a_set_secret_installs_the_check(monkeypatch):
    monkeypatch.setenv(JWT_SECRET_ENV, SECRET)
    check = AavaazServer()._websocket_auth()
    assert check(FakeConnection(), FakeRequest(subprotocol_offer(make_token()))) is None


def test_a_secret_too_short_to_be_worth_having_refuses_to_start(monkeypatch):
    monkeypatch.setenv(JWT_SECRET_ENV, "a" * (MINIMUM_JWT_SECRET_BYTES - 1))
    with pytest.raises(ValueError) as refused:
        AavaazServer()._websocket_auth()
    assert JWT_SECRET_ENV in str(refused.value)
    assert str(MINIMUM_JWT_SECRET_BYTES) in str(refused.value)


def test_a_secret_of_exactly_the_minimum_is_accepted(monkeypatch):
    monkeypatch.setenv(JWT_SECRET_ENV, "a" * MINIMUM_JWT_SECRET_BYTES)
    assert AavaazServer()._websocket_auth() is not None


def test_the_length_is_bytes_not_characters(monkeypatch):
    # 31 characters that encode to more than 32 bytes: counting characters would
    # wrongly refuse this one
    monkeypatch.setenv(JWT_SECRET_ENV, "é" * 31)
    assert AavaazServer()._websocket_auth() is not None
