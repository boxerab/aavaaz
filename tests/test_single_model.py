"""The shared-model flag and the up-front model fetch.

A fresh model per connection costs a load on every reconnect, and WhisperLive
closes the socket after END_OF_AUDIO, so a caller who dictates twice pays twice.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from aavaaz.server import AavaazServer


class FakeTranscriptionServer:
    """Enough of WhisperLive to record what Aavaaz asks of it."""

    def __init__(self):
        self.run_kwargs = {}
        self.client_options = None

    def initialize_client(self, websocket, options, *args, **kwargs):
        self.client_options = options

    def run(self, **kwargs):
        self.run_kwargs.update(kwargs)


@pytest.fixture
def whisperlive(monkeypatch):
    fake = FakeTranscriptionServer()
    monkeypatch.setattr("aavaaz.server.TranscriptionServer", lambda: fake)
    monkeypatch.delenv("AAVAAZ_JWT_SECRET", raising=False)
    return fake


def start(whisperlive, **kwargs):
    with patch.object(AavaazServer, "_predownload_model"):
        AavaazServer(**kwargs).run()
    return whisperlive


def test_the_model_is_shared_across_clients_by_default(whisperlive):
    assert start(whisperlive, model="tiny").run_kwargs["single_model"] is True


def test_a_caller_can_turn_sharing_off(whisperlive):
    served = start(whisperlive, model="tiny", single_model=False)
    assert served.run_kwargs["single_model"] is False


def test_a_client_naming_another_model_is_told_it_will_not_get_it(whisperlive, caplog):
    served = start(whisperlive, model="large-v3-turbo")
    with caplog.at_level("WARNING"):
        served.initialize_client(object(), {"model": "tiny"})
    assert "tiny" in caplog.text
    assert "large-v3-turbo" in caplog.text
    # the client still gets served, with the model the server actually holds
    assert served.client_options["model"] == "tiny"


def test_a_client_asking_for_the_served_model_is_not_warned_at(whisperlive, caplog):
    served = start(whisperlive, model="large-v3-turbo")
    with caplog.at_level("WARNING"):
        caplog.clear()  # startup warned about the unset secret, that is not this
        served.initialize_client(object(), {"model": "large-v3-turbo"})
    assert caplog.text == ""


def test_no_warning_when_clients_may_choose(whisperlive, caplog):
    served = start(whisperlive, model="large-v3-turbo", single_model=False)
    with caplog.at_level("WARNING"):
        caplog.clear()
        served.initialize_client(object(), {"model": "tiny"})
    assert caplog.text == ""


@pytest.fixture
def fetched(monkeypatch):
    """Stand in for faster-whisper, which the [whisper] extra may not have installed."""
    names = []
    utils = ModuleType("faster_whisper.utils")
    utils.download_model = lambda name, *a, **k: names.append(name)
    package = ModuleType("faster_whisper")
    package.utils = utils
    monkeypatch.setitem(sys.modules, "faster_whisper", package)
    monkeypatch.setitem(sys.modules, "faster_whisper.utils", utils)
    return names


def test_the_model_is_fetched_before_the_first_client(fetched):
    AavaazServer(model="tiny")._predownload_model()
    assert fetched == ["tiny"]


def test_a_failed_fetch_does_not_stop_the_server(fetched, monkeypatch, caplog):
    def explode(name, *args, **kwargs):
        raise OSError("no route to host")

    sys.modules["faster_whisper.utils"].download_model = explode
    with caplog.at_level("WARNING"):
        AavaazServer(model="tiny")._predownload_model()
    assert "tiny" in caplog.text


def test_a_mocked_faster_whisper_still_starts(monkeypatch, caplog):
    # what CI sees: another test leaves a MagicMock under the name, and importing
    # a submodule of it raises "not a package"
    monkeypatch.setitem(sys.modules, "faster_whisper", MagicMock())
    monkeypatch.delitem(sys.modules, "faster_whisper.utils", raising=False)
    with caplog.at_level("WARNING"):
        AavaazServer(model="tiny")._predownload_model()
    assert "tiny" in caplog.text


def test_an_install_without_faster_whisper_still_starts(monkeypatch, caplog):
    # both entries: a cached submodule is found without consulting the parent
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    monkeypatch.delitem(sys.modules, "faster_whisper.utils", raising=False)
    with caplog.at_level("WARNING"):
        AavaazServer(model="tiny")._predownload_model()
    assert "tiny" in caplog.text


def test_a_custom_model_path_is_left_to_whisperlive(fetched):
    AavaazServer(model="Systran/faster-whisper-tiny")._predownload_model()
    assert fetched == []


def test_a_refused_secret_costs_no_model_download(whisperlive, fetched, monkeypatch):
    monkeypatch.setenv("AAVAAZ_JWT_SECRET", "too-short")
    with pytest.raises(ValueError):
        AavaazServer(model="tiny").run()
    assert fetched == []
