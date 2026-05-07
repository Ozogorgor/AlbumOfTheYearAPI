"""Tests for the FastAPI wrapper in app/main.py.

These do not hit the real AOTY site, MusicBrainz, or Postgres — every
external dependency is mocked. Run with `pytest test_fastapi.py`.
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

# Stub heavy/optional deps so tests don't require them installed.
for _mod in ("psycopg2", "psycopg2.extras"):
    sys.modules.setdefault(_mod, MagicMock())

# Module-level config is read at import; pin a key so auth tests can flex it.
os.environ["ADMIN_API_KEY"] = "test-secret"

from app import main  # noqa: E402

main.ADMIN_API_KEY = "test-secret"


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def no_db(monkeypatch):
    """Default: pretend the DB is offline so cache and mapping table miss."""
    monkeypatch.setattr(main, "DATABASE_URL", None)
    monkeypatch.setattr(main, "get_db_conn", lambda: None)


@pytest.fixture
def fake_db(monkeypatch):
    """Helper to install a MagicMock cursor as the DB."""
    monkeypatch.setattr(main, "DATABASE_URL", "postgres://fake")
    cur = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cur
    monkeypatch.setattr(main, "get_db_conn", lambda: conn)
    return cur


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_auth_rejects_missing_key(client):
    r = client.get("/artist/183-kanye-west")
    assert r.status_code == 401


def test_auth_rejects_bad_key(client):
    r = client.get("/artist/183-kanye-west", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_artist_endpoint_calls_scraper(client, monkeypatch):
    summary = {
        "artist_id": "183-kanye-west",
        "critic": {"critic_score": 79},
        "user": {"user_score": 82},
        "success": True,
    }
    monkeypatch.setattr(main.aoty, "get_artist_summary", lambda aid: summary)
    r = client.get("/artist/183-kanye-west", headers={"X-API-Key": "test-secret"})
    assert r.status_code == 200
    assert r.json()["critic"]["critic_score"] == 79


def test_artist_endpoint_404_on_scraper_error(client, monkeypatch):
    monkeypatch.setattr(
        main.aoty,
        "get_artist_summary",
        lambda aid: {"success": False, "error": "Artist page not found"},
    )
    r = client.get("/artist/nope", headers={"X-API-Key": "test-secret"})
    assert r.status_code == 404


def test_aoty_slug_from_url():
    f = main._aoty_slug_from_url
    assert f("https://www.albumoftheyear.org/artist/183-kanye-west/") == {
        "kind": "artist",
        "slug": "183-kanye-west",
    }
    assert f("http://albumoftheyear.org/album/2546-dom-family-of-love") == {
        "kind": "album",
        "slug": "2546-dom-family-of-love",
    }
    assert f("https://example.com/artist/foo") is None
    assert f("") is None
    assert f(None) is None


def test_lookup_mb_table_hit(client, fake_db):
    fake_db.fetchone.return_value = ("183-kanye-west", "Kanye West")
    r = client.get(
        "/lookup/mb/abc-123?type=artist",
        headers={"X-API-Key": "test-secret"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["aoty_slug"] == "183-kanye-west"
    assert body["source"] == "mapping_table"
    assert body["name"] == "Kanye West"


def test_lookup_mb_falls_through_to_urlrels(client, monkeypatch):
    """Mapping-table miss triggers MB url-rels lookup; on hit we persist."""
    monkeypatch.setattr(
        main,
        "_lookup_via_mb_urlrels",
        AsyncMock(return_value={"aoty_slug": "999-test", "name": "Test"}),
    )
    persist = AsyncMock()
    monkeypatch.setattr(main, "_persist_mapping", persist)

    r = client.get(
        "/lookup/mb/some-mb-id?type=artist",
        headers={"X-API-Key": "test-secret"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["aoty_slug"] == "999-test"
    assert body["source"] == "musicbrainz_urlrels"
    persist.assert_awaited_once()


def test_lookup_mb_total_miss_returns_null_slug(client, monkeypatch):
    monkeypatch.setattr(main, "_lookup_via_mb_urlrels", AsyncMock(return_value=None))
    r = client.get(
        "/lookup/mb/unmappable?type=artist",
        headers={"X-API-Key": "test-secret"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["aoty_slug"] is None
    assert body["source"] is None


def test_album_mb_endpoint_uses_scraper(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "_lookup_via_mb_urlrels",
        AsyncMock(return_value={"aoty_slug": "2546-dom-family-of-love", "name": "Family of Love"}),
    )
    monkeypatch.setattr(main, "_persist_mapping", AsyncMock())
    monkeypatch.setattr(
        main.aoty,
        "album_summary",
        lambda slug: {
            "album_slug": slug,
            "critic_score": 73,
            "user_score": 67,
            "success": True,
        },
    )
    r = client.get(
        "/album/mb/release-mbid-xyz",
        headers={"X-API-Key": "test-secret"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["critic_score"] == 73
    assert body["user_score"] == 67
    assert body["mb_album_id"] == "release-mbid-xyz"


def test_album_mb_404_when_no_mapping(client, monkeypatch):
    monkeypatch.setattr(main, "_lookup_via_mb_urlrels", AsyncMock(return_value=None))
    r = client.get("/album/mb/no-mapping", headers={"X-API-Key": "test-secret"})
    assert r.status_code == 404


def test_artists_batch_streams_sse(client, monkeypatch):
    monkeypatch.setattr(
        main.aoty,
        "get_artist_summary",
        lambda aid: {"artist_id": aid, "success": True},
    )
    payload = {"artist_ids": ["183-kanye-west", "1669-dom"]}
    with client.stream(
        "POST",
        "/artists/batch",
        json=payload,
        headers={"X-API-Key": "test-secret"},
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = b"".join(r.iter_bytes()).decode()

    events = [
        json.loads(line[len("data: "):])
        for line in body.strip().split("\n\n")
        if line.startswith("data: ")
    ]
    assert len(events) == 2
    assert events[0]["artist_id"] == "183-kanye-west"
    assert events[1]["artist_id"] == "1669-dom"


def test_artists_batch_rejects_bad_payload(client):
    r = client.post(
        "/artists/batch",
        json={"artist_ids": "not-a-list"},
        headers={"X-API-Key": "test-secret"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_lookup_via_mb_urlrels_extracts_aoty_url():
    """Parse a real-shaped MB url-rels response."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json = MagicMock(
        return_value={
            "name": "Some Artist",
            "relations": [
                {"url": {"resource": "https://www.allmusic.com/artist/mn-1"}},
                {"url": {"resource": "https://www.albumoftheyear.org/artist/183-kanye-west/"}},
            ],
        }
    )

    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=fake_response)
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.main.httpx.AsyncClient", return_value=fake_client):
        result = await main._lookup_via_mb_urlrels("mb-id-abc", "artist")

    assert result == {"aoty_slug": "183-kanye-west", "name": "Some Artist"}


@pytest.mark.asyncio
async def test_lookup_via_mb_urlrels_no_aoty_link():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json = MagicMock(
        return_value={"name": "X", "relations": [{"url": {"resource": "https://example.com"}}]}
    )
    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=fake_response)
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.main.httpx.AsyncClient", return_value=fake_client):
        result = await main._lookup_via_mb_urlrels("mb-id-abc", "artist")

    assert result is None
