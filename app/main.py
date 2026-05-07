import json
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import httpx
from fastapi import FastAPI, HTTPException, Header
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import Json
from starlette.requests import Request

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from albumoftheyearapi import AOTY

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
CACHE_TTL = int(os.getenv("CACHE_TTL", 604800))
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
MB_USER_AGENT = os.getenv(
    "MUSICBRAINZ_USER_AGENT",
    "stui-aoty-bridge/0.1 ( https://github.com/Ozogorgor/AlbumOfTheYearAPI )",
)
MB_BASE_URL = "https://musicbrainz.org/ws/2"

_AOTY_URL_RE = re.compile(
    r"https?://(?:www\.)?albumoftheyear\.org/(artist|album)/([^/?#]+)/?",
    re.I,
)
_MB_TYPE_TO_ENTITY = {
    "artist": "artist",
    "album": "release-group",
    "release": "release",
    "release-group": "release-group",
}


def _aoty_slug_from_url(url: str) -> Optional[Dict[str, str]]:
    """Parse AOTY URL → {kind, slug} or None."""
    m = _AOTY_URL_RE.search(url or "")
    if not m:
        return None
    kind, slug = m.group(1).lower(), m.group(2).strip("/")
    return {"kind": kind, "slug": slug} if slug else None


async def _persist_mapping(mb_id: str, type_: str, slug: str, name: Optional[str]) -> None:
    if not DATABASE_URL:
        return
    try:
        conn = get_db_conn()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO mb_aoty_mapping (mb_id, type, aoty_slug, name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (mb_id, type) DO UPDATE SET
                aoty_slug = EXCLUDED.aoty_slug,
                name = EXCLUDED.name
            """,
            (mb_id, type_, slug, name),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Mapping persist error: {e}")


async def _lookup_via_mb_urlrels(mb_id: str, type_: str) -> Optional[Dict[str, Optional[str]]]:
    """Hit MusicBrainz `?inc=url-rels` for an AOTY URL relation."""
    entity = _MB_TYPE_TO_ENTITY.get(type_)
    if not entity:
        return None
    url = f"{MB_BASE_URL}/{entity}/{mb_id}?inc=url-rels&fmt=json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"User-Agent": MB_USER_AGENT})
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception as e:
        print(f"MB url-rels error for {mb_id}: {e}")
        return None

    name = data.get("name") or data.get("title")
    for rel in data.get("relations") or []:
        target = (rel.get("url") or {}).get("resource", "")
        parsed = _aoty_slug_from_url(target)
        if not parsed:
            continue
        if type_ == "artist" and parsed["kind"] != "artist":
            continue
        if type_ != "artist" and parsed["kind"] != "album":
            continue
        return {"aoty_slug": parsed["slug"], "name": name}
    return None

app = FastAPI(title="AOTY Scraper API")
aoty = AOTY(cache_ttl=CACHE_TTL)


# Database helpers
def get_db_conn():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL, connect_timeout=5)
    return None


async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if ADMIN_API_KEY and x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


async def get_cached(key: str) -> Optional[Dict[str, Any]]:
    if not DATABASE_URL:
        return None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT data, cached_at FROM cache WHERE id_key = %s", (key,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            data, cached_at = row
            if datetime.utcnow() - cached_at < timedelta(seconds=CACHE_TTL):
                return data
    except Exception as e:
        print(f"Cache read error: {e}")
    return None


async def set_cache(key: str, data: Dict[str, Any]):
    if not DATABASE_URL:
        return
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cache (id_key, data, cached_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (id_key) DO UPDATE SET data = EXCLUDED.data, cached_at = EXCLUDED.cached_at
        """, (key, Json(data), datetime.utcnow()))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Cache write error: {e}")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/artist/{artist_id}")
async def get_artist(
    artist_id: str,
    x_api_key: Optional[str] = Header(None)
):
    await verify_api_key(x_api_key)

    cache_key = f"artist_summary:{artist_id}"
    cached = await get_cached(cache_key)
    if cached:
        return cached

    try:
        data = await run_in_threadpool(aoty.get_artist_summary, artist_id)
        await set_cache(cache_key, data)

        # Return 404 if not found
        if not data.get("success") and data.get("error"):
            raise HTTPException(status_code=404, detail=data["error"])

        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {str(e)}")


@app.get("/artist/{artist_id}/critic")
async def get_critic_score(
    artist_id: str,
    x_api_key: Optional[str] = Header(None)
):
    await verify_api_key(x_api_key)

    cache_key = f"critic_score:{artist_id}"
    cached = await get_cached(cache_key)
    if cached:
        return cached

    try:
        data = await run_in_threadpool(aoty.artist_critic_score, artist_id)
        await set_cache(cache_key, data)

        # Return 404 if not found
        if not data.get("success") and data.get("error"):
            raise HTTPException(status_code=404, detail=data["error"])

        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {str(e)}")


@app.get("/artist/{artist_id}/user")
async def get_user_score(
    artist_id: str,
    x_api_key: Optional[str] = Header(None)
):
    await verify_api_key(x_api_key)

    cache_key = f"user_score:{artist_id}"
    cached = await get_cached(cache_key)
    if cached:
        return cached

    try:
        data = await run_in_threadpool(aoty.artist_user_score, artist_id)
        await set_cache(cache_key, data)

        # Return 404 if not found
        if not data.get("success") and data.get("error"):
            raise HTTPException(status_code=404, detail=data["error"])

        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {str(e)}")


@app.get("/artist/{artist_id}/albums")
async def get_albums(
    artist_id: str,
    x_api_key: Optional[str] = Header(None)
):
    await verify_api_key(x_api_key)

    cache_key = f"albums:{artist_id}"
    cached = await get_cached(cache_key)
    if cached:
        return {"artist_id": artist_id, "albums": cached.get("albums", cached) if isinstance(cached, dict) else cached}

    try:
        data = await run_in_threadpool(aoty.artist_albums, artist_id)
        await set_cache(cache_key, data)

        # Return 404 if not found
        if isinstance(data, dict) and not data.get("success") and data.get("error"):
            raise HTTPException(status_code=404, detail=data["error"])

        albums = data.get("albums", data) if isinstance(data, dict) else data
        return {"artist_id": artist_id, "albums": albums}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {str(e)}")


@app.get("/artist/{artist_id}/followers")
async def get_followers(
    artist_id: str,
    x_api_key: Optional[str] = Header(None)
):
    await verify_api_key(x_api_key)

    cache_key = f"followers:{artist_id}"
    cached = await get_cached(cache_key)
    if cached:
        return cached

    try:
        data = await run_in_threadpool(aoty.artist_follower_count, artist_id)
        await set_cache(cache_key, data)

        # Return 404 if not found
        if not data.get("success") and data.get("error"):
            raise HTTPException(status_code=404, detail=data["error"])

        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {str(e)}")


@app.post("/artists/batch")
async def batch_artists(
    request: Request,
    x_api_key: Optional[str] = Header(None)
):
    await verify_api_key(x_api_key)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    artist_ids = body.get("artist_ids", [])
    if not isinstance(artist_ids, list):
        raise HTTPException(status_code=400, detail="artist_ids must be a list")

    async def generate():
        for artist_id in artist_ids:
            cache_key = f"artist_summary:{artist_id}"
            cached = await get_cached(cache_key)
            if cached:
                data = {"artist_id": artist_id, "data": cached, "cached": True}
            else:
                try:
                    result = await run_in_threadpool(aoty.get_artist_summary, artist_id)
                    await set_cache(cache_key, result)
                    data = {"artist_id": artist_id, "data": result, "cached": False}
                except Exception as e:
                    data = {"artist_id": artist_id, "error": str(e)}
            yield f"data: {json.dumps(data)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/lookup/mb/{mb_id}")
async def lookup_mb_id(
    mb_id: str,
    type: str = "artist",
    x_api_key: Optional[str] = Header(None)
):
    """Lookup MusicBrainz ID → AOTY slug.

    Resolution order: response cache → mb_aoty_mapping table → MusicBrainz
    url-rels (low hit rate but free when present; auto-persists on hit).
    """
    await verify_api_key(x_api_key)

    cache_key = f"mb_lookup:{mb_id}:{type}"
    cached = await get_cached(cache_key)
    if cached:
        return cached

    result = {"mb_id": mb_id, "type": type, "aoty_slug": None, "name": None, "source": None}

    if DATABASE_URL:
        try:
            conn = get_db_conn()
            if conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT aoty_slug, name FROM mb_aoty_mapping WHERE mb_id = %s AND type = %s",
                    (mb_id, type),
                )
                row = cur.fetchone()
                cur.close()
                conn.close()
                if row:
                    result["aoty_slug"] = row[0]
                    result["name"] = row[1]
                    result["source"] = "mapping_table"
                    await set_cache(cache_key, result)
                    return result
        except Exception as e:
            print(f"Mapping lookup error: {e}")

    urlrels = await _lookup_via_mb_urlrels(mb_id, type)
    if urlrels and urlrels.get("aoty_slug"):
        result["aoty_slug"] = urlrels["aoty_slug"]
        result["name"] = urlrels.get("name")
        result["source"] = "musicbrainz_urlrels"
        await _persist_mapping(mb_id, type, urlrels["aoty_slug"], urlrels.get("name"))
        await set_cache(cache_key, result)
        return result

    return result


@app.get("/artist/mb/{mb_artist_id}")
async def get_artist_by_mb(
    mb_artist_id: str,
    x_api_key: Optional[str] = Header(None)
):
    """Get AOTY artist data directly from MusicBrainz artist ID"""
    await verify_api_key(x_api_key)

    # First lookup AOTY slug
    lookup = await lookup_mb_id(mb_artist_id, "artist", x_api_key)

    if not lookup.get("aoty_slug"):
        raise HTTPException(status_code=404, detail="AOTY slug not found for this MB ID")

    aoty_slug = lookup["aoty_slug"]

    # Get AOTY data using slug
    cache_key = f"artist_summary:{aoty_slug}"
    cached = await get_cached(cache_key)
    if cached:
        return cached

    try:
        data = await run_in_threadpool(aoty.get_artist_summary, aoty_slug)
        await set_cache(cache_key, data)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {str(e)}")


@app.get("/album/mb/{mb_album_id}")
async def get_album_by_mb(
    mb_album_id: str,
    x_api_key: Optional[str] = Header(None)
):
    """Get AOTY album data directly from MusicBrainz release/release-group ID"""
    await verify_api_key(x_api_key)

    lookup = await lookup_mb_id(mb_album_id, "release", x_api_key)
    if not lookup.get("aoty_slug"):
        lookup = await lookup_mb_id(mb_album_id, "release-group", x_api_key)
    if not lookup.get("aoty_slug"):
        lookup = await lookup_mb_id(mb_album_id, "album", x_api_key)

    if not lookup.get("aoty_slug"):
        raise HTTPException(status_code=404, detail="AOTY album slug not found for this MB ID")

    aoty_slug = lookup["aoty_slug"]

    cache_key = f"album_summary:{aoty_slug}"
    cached = await get_cached(cache_key)
    if cached:
        return {"mb_album_id": mb_album_id, "lookup_source": lookup.get("source"), **cached}

    try:
        data = await run_in_threadpool(aoty.album_summary, aoty_slug)
        canonical = data.get("canonical_slug")
        # Self-heal: if AOTY redirected us to a different slug, the stored
        # mapping was wrong (or out of date). Persist the correction so the
        # next request hits the right URL directly.
        if (
            canonical
            and lookup.get("source") == "mapping_table"
            and canonical != aoty_slug
        ):
            await _persist_mapping(
                mb_album_id, lookup.get("type"), canonical, data.get("title")
            )
            data["healed_from_slug"] = aoty_slug
        await set_cache(cache_key, data)
        return {"mb_album_id": mb_album_id, "lookup_source": lookup.get("source"), **data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {str(e)}")


@app.post("/mapping")
async def add_mapping(
    request: Request,
    x_api_key: Optional[str] = Header(None)
):
    """Add hand-curated MB → AOTY mapping"""
    await verify_api_key(x_api_key)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    mb_id = body.get("mb_id")
    aoty_slug = body.get("aoty_slug")
    map_type = body.get("type", "artist")
    name = body.get("name")

    if not mb_id or not aoty_slug:
        raise HTTPException(status_code=400, detail="mb_id and aoty_slug are required")

    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="Database not configured")

    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO mb_aoty_mapping (mb_id, type, aoty_slug, name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (mb_id, type) DO UPDATE SET
                aoty_slug = EXCLUDED.aoty_slug,
                name = EXCLUDED.name
        """, (mb_id, map_type, aoty_slug, name))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "ok", "mb_id": mb_id, "aoty_slug": aoty_slug, "type": map_type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
