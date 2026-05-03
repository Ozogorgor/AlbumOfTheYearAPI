import os
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Header
from fastapi.concurrency import run_in_threadpool
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
        return data
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
        return data
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
        return data
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
        return {"artist_id": artist_id, "albums": cached}
    
    try:
        data = await run_in_threadpool(aoty.artist_albums, artist_id)
        await set_cache(cache_key, data)
        return {"artist_id": artist_id, "albums": data}
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
        return data
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
        import json
        for artist_id in artist_ids:
            cache_key = f"artist_summary:{artist_id}"
            cached = await get_cached(cache_key)
            if cached:
                yield f"data: {json.dumps({'artist_id': artist_id, 'data': cached, 'cached': True})}\n\n"
            else:
                try:
                    data = await run_in_threadpool(aoty.get_artist_summary, artist_id)
                    await set_cache(cache_key, data)
                    yield f"data: {json.dumps({'artist_id': artist_id, 'data': data, 'cached': False})}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'artist_id': artist_id, 'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/lookup/mb/{mb_artist_id}")
async def lookup_mb_artist(
    mb_artist_id: str,
    x_api_key: Optional[str] = Header(None)
):
    """Lookup MusicBrainz artist ID → AOTY slug using MB url-rels"""
    await verify_api_key(x_api_key)
    
    cache_key = f"mb_lookup:{mb_artist_id}"
    cached = await get_cached(cache_key)
    if cached:
        return cached
    
    try:
        # Strategy (a): Check MusicBrainz url-rels for AOTY URL
        import httpx
        mb_url = f"https://musicbrainz.org/ws/2/artist/{mb_artist_id}?fmt=json&inc=url-rels"
        resp = await run_in_threadpool(
            lambda: httpx.get(mb_url, headers={"User-Agent": "AOTYScraper/1.0"})
        )
        
        result = {"mb_artist_id": mb_artist_id, "aoty_slug": None, "source": None}
        
        if resp.status_code == 200:
            data = resp.json()
            # Search for AOTY URL in relations
            for rel in data.get("relations", []):
                url = rel.get("url", {}).get("resource", "")
                if "albumoftheyear.org/artist/" in url:
                    # Extract slug from URL
                    slug = url.split("/artist/")[-1].strip("/")
                    result["aoty_slug"] = slug
                    result["source"] = "musicbrainz_url-rel"
                    break
            
            # If not found, try MB mapping table
            if not result["aoty_slug"] and DATABASE_URL:
                try:
                    conn = get_db_conn()
                    cur = conn.cursor()
                    cur.execute("SELECT aoty_slug FROM mb_aoty_mapping WHERE mb_artist_id = %s", (mb_artist_id,))
                    row = cur.fetchone()
                    cur.close()
                    conn.close()
                    if row:
                        result["aoty_slug"] = row[0]
                        result["source"] = "mapping_table"
                except Exception as e:
                    print(f"Mapping lookup error: {e}")
        
        if result["aoty_slug"]:
            await set_cache(cache_key, result)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lookup failed: {str(e)}")


@app.get("/artist/mb/{mb_artist_id}")
async def get_artist_by_mb(
    mb_artist_id: str,
    x_api_key: Optional[str] = Header(None)
):
    """Get AOTY artist data directly from MusicBrainz ID"""
    await verify_api_key(x_api_key)
    
    # First lookup AOTY slug
    cache_key = f"mb_lookup:{mb_artist_id}"
    cached = await get_cached(cache_key)
    
    if cached and cached.get("aoty_slug"):
        aoty_slug = cached["aoty_slug"]
    else:
        # Lookup from MB
        import httpx
        mb_url = f"https://musicbrainz.org/ws/2/artist/{mb_artist_id}?fmt=json&inc=url-rels"
        resp = await run_in_threadpool(
            lambda: httpx.get(mb_url, headers={"User-Agent": "AOTYScraper/1.0"})
        )
        
        aoty_slug = None
        if resp.status_code == 200:
            data = resp.json()
            for rel in data.get("relations", []):
                url = rel.get("url", {}).get("resource", "")
                if "albumoftheyear.org/artist/" in url:
                    aoty_slug = url.split("/artist/")[-1].strip("/")
                    break
        
        if not aoty_slug:
            raise HTTPException(status_code=404, detail="AOTY slug not found for this MB ID")
    
    # Get AOTY data using slug
    cache_key2 = f"artist_summary:{aoty_slug}"
    cached2 = await get_cached(cache_key2)
    if cached2:
        return cached2
    
    try:
        data = await run_in_threadpool(aoty.get_artist_summary, aoty_slug)
        await set_cache(cache_key2, data)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {str(e)}")


# Mapping table management (Strategy c)
@app.post("/mapping")
async def add_mapping(
    request: Request,
    x_api_key: Optional[str] = Header(None)
):
    await verify_api_key(x_api_key)
    
    try:
        body = await request.json()
        mb_id = body.get("mb_artist_id")
        aoty_slug = body.get("aoty_slug")
        artist_name = body.get("artist_name", "")
        
        if not mb_id or not aoty_slug:
            raise HTTPException(status_code=400, detail="mb_artist_id and aoty_slug required")
        
        if DATABASE_URL:
            try:
                conn = get_db_conn()
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO mb_aoty_mapping (mb_artist_id, aoty_slug, artist_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (mb_artist_id) DO UPDATE SET aoty_slug = EXCLUDED.aoty_slug
                """, (mb_id, aoty_slug, artist_name))
                conn.commit()
                cur.close()
                conn.close()
                return {"status": "ok", "mb_artist_id": mb_id, "aoty_slug": aoty_slug}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
        else:
            raise HTTPException(status_code=500, detail="Database not configured")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")

