"""An unreachable source during a refresh serves the cached copy; a 4xx never does (D-074)."""

import json
import urllib.error

import pytest

from corridor.ingest import http


def _cache(monkeypatch, tmp_path, url, body):
    monkeypatch.setattr(http, "RAW_DIR", tmp_path)
    path = http._cache_path("src", url)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(body))
    return path


def test_refresh_falls_back_to_cache_when_the_source_is_unreachable(monkeypatch, tmp_path):
    url = "https://understat.com/getLeagueData/EPL/2026"
    _cache(monkeypatch, tmp_path, url, {"teams": "old"})

    def dns_down(*a, **k):
        raise urllib.error.URLError("nodename nor servname provided, or not known")

    monkeypatch.setattr(http.urllib.request, "urlopen", dns_down)
    assert http.fetch_json("src", url, refresh=True) == {"teams": "old"}


def test_refresh_raises_when_nothing_is_cached(monkeypatch, tmp_path):
    monkeypatch.setattr(http, "RAW_DIR", tmp_path)

    def dns_down(*a, **k):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(http.urllib.request, "urlopen", dns_down)
    with pytest.raises(urllib.error.URLError):
        http.fetch_json("src", "https://understat.com/x", refresh=True)


def test_a_client_error_is_never_masked_by_the_cache(monkeypatch, tmp_path):
    url = "https://understat.com/getLeagueData/EPL/2026"
    _cache(monkeypatch, tmp_path, url, {"teams": "old"})

    def not_found(*a, **k):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(http.urllib.request, "urlopen", not_found)
    with pytest.raises(urllib.error.HTTPError):
        http.fetch_json("src", url, refresh=True)


class _Resp:
    headers: dict = {}

    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_an_error_page_with_status_200_serves_the_cache_and_keeps_it(monkeypatch, tmp_path):
    url = "https://understat.com/getLeagueData/EPL/2026"
    path = _cache(monkeypatch, tmp_path, url, {"teams": "old"})
    page = b"<!DOCTYPE html><html><title>Understat.com</title></html>"
    monkeypatch.setattr(http.urllib.request, "urlopen", lambda *a, **k: _Resp(page))
    assert http.fetch_json("src", url, refresh=True) == {"teams": "old"}
    assert json.loads(path.read_text()) == {"teams": "old"}


def test_an_error_page_with_nothing_cached_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(http, "RAW_DIR", tmp_path)
    monkeypatch.setattr(http.urllib.request, "urlopen", lambda *a, **k: _Resp(b"<html>"))
    with pytest.raises(ValueError):
        http.fetch_json("src", "https://understat.com/x", refresh=True)
