"""Keep-awake estilo woke-dyno: sin hilos ni HTTP real en tests."""
import threading

import pytest

import app.services.keep_awake as keep_awake
from app.core.config import settings
from app.services.keep_awake import (
    keep_awake_configured,
    maybe_start_keep_awake,
    ping_once,
    reset_keep_awake_state,
    start_keep_awake,
)


@pytest.fixture(autouse=True)
def _no_threads(monkeypatch):
    monkeypatch.setattr(settings, "KEEP_AWAKE_ENABLED", False)
    monkeypatch.setattr(settings, "KEEP_AWAKE_URL", "")
    reset_keep_awake_state()
    yield
    reset_keep_awake_state()


class _FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_disabled_by_default():
    assert keep_awake_configured() is False
    assert maybe_start_keep_awake() is None


def test_needs_flag_and_absolute_url(monkeypatch):
    monkeypatch.setattr(settings, "KEEP_AWAKE_URL", "https://api.example.com/health")
    assert keep_awake_configured() is False  # falta el flag
    monkeypatch.setattr(settings, "KEEP_AWAKE_ENABLED", True)
    assert keep_awake_configured() is True
    monkeypatch.setattr(settings, "KEEP_AWAKE_URL", "localhost:8000/health")
    assert keep_awake_configured() is False  # no es absoluta


def test_ping_once_ok(monkeypatch):
    monkeypatch.setattr(
        keep_awake.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(200)
    )
    assert ping_once("https://api.example.com/health") is True


def test_ping_once_fails_silently(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("sin red")

    monkeypatch.setattr(keep_awake.urllib.request, "urlopen", boom)
    assert ping_once("https://api.example.com/health") is False
    monkeypatch.setattr(
        keep_awake.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(500)
    )
    assert ping_once("https://api.example.com/health") is False


def test_start_spawns_one_daemon_thread_pinging_the_url():
    calls = []
    stop = threading.Event()

    def fake_ping(url):
        calls.append(url)
        stop.set()  # el hilo real seguiría; en tests paramos tras el primer ping
        return True

    def fake_sleep(seconds):
        assert seconds == 10 * 60

    thread = start_keep_awake(
        "https://api.example.com/health", minutes=10, ping=fake_ping, sleep=fake_sleep, stop=stop
    )
    assert isinstance(thread, threading.Thread)
    assert thread.daemon is True
    thread.join(timeout=5)
    assert calls == ["https://api.example.com/health"]
    # Segunda llamada no duplica el hilo.
    assert (
        start_keep_awake("https://api.example.com/health", minutes=10, ping=fake_ping, sleep=fake_sleep) is None
    )


def test_start_rejects_bad_url():
    assert start_keep_awake("localhost:8000/health", minutes=10) is None
    assert start_keep_awake("https://api.example.com/health", minutes=0) is None


def test_maybe_starts_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "KEEP_AWAKE_ENABLED", True)
    monkeypatch.setattr(settings, "KEEP_AWAKE_URL", "https://api.example.com/health")
    monkeypatch.setattr(settings, "KEEP_AWAKE_MINUTES", 10)

    started = {}

    def fake_start(url=None, minutes=None, ping=None, sleep=None):
        started["args"] = (url, minutes)
        return "thread"

    monkeypatch.setattr(keep_awake, "start_keep_awake", fake_start)
    assert maybe_start_keep_awake() == "thread"
    assert started["args"] == (None, None)  # usa los settings por defecto
