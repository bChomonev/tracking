"""Polite, cached JSON fetching. Each URL is fetched once and kept under ``data/raw/`` so
we never re-hit a source for data we already have, and keep the raw payload if a source
changes shape or disappears."""

import gzip
import hashlib
import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[4] / "data"
RAW_DIR = DATA_DIR / "raw"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)
MIN_INTERVAL_S = 1.5

_last_request = 0.0


def _cache_path(source: str, url: str) -> Path:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1])[-80:]
    digest = hashlib.sha1(url.encode()).hexdigest()[:10]
    return RAW_DIR / source / f"{slug}_{digest}.json"


def fetch_text(source: str, url: str, *, max_age_h: float | None = None) -> str:
    """Like fetch_json for plain-text files (CSV). ``max_age_h``: refetch a cached copy older
    than this (for files the source keeps updating, e.g. the current season's odds)."""
    global _last_request
    path = _cache_path(source, url).with_suffix(".txt")
    if path.exists() and (
        max_age_h is None or time.time() - path.stat().st_mtime < max_age_h * 3600
    ):
        return path.read_text()
    wait = MIN_INTERVAL_S - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8-sig", errors="replace")
    _last_request = time.monotonic()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return body


def fetch_json(
    source: str, url: str, *, headers: dict[str, str] | None = None, refresh: bool = False
) -> Any:
    global _last_request
    path = _cache_path(source, url)
    if path.exists() and not refresh:
        return json.loads(path.read_text())

    wait = MIN_INTERVAL_S - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    _last_request = time.monotonic()

    data = json.loads(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data
