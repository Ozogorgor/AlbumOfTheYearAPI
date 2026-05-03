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


@app.get("/lookup/mb/{mb_id}")
async def lookup_mb_id(
    mb_id: str,
    type: str = "artist",
    x_api_key: Optional[str] = Header(None)
):
    """Lookup MusicBrainz ID → AOTY slug (supports artist + album)"""
    await verify_api_key(x_api_key)
    
    cache_key = f"mb_lookup:{mb_id}:{type}"
    cached = await get_cached(cache_key)
    if cached:
        return cached
    
    try:
        # Query MusicBrainz API
        mb_url = f"https://musicbrainz.org/ws/2/{type}/{mb_id}?fmt=json&inc=url-rels"
        resp = await run_in_threadpool(
            lambda: httpx.get(mb_url, headers={"User-Agent": "AOTYScraper/1.0"})
        )
        
        result = {"mb_id": mb_id, "type": type, "aoty_slug": None, "name": None, "source": None}
        
        if resp.status_code == 200:
            data = resp.json()
            result["name"] = data.get("name") or data.get("title")
            
            # Search for AOTY URL in relations
            for rel in data.get("relations", []):
                url = rel.get("url", {}).get("resource", "")
                if "albumoftheyear.org" in url:
                    if type == "artist" and "/artist/" in url:
                        result["aoty_slug"] = url.split("/artist/")[-1].strip("/")
                        result["source"] = "musicbrainz_url-rel"
                        break
                    elif type in ["release", "release-group"] and "/album/" in url:
                        result["aoty_slug"] = url.split("/album/")[-1].strip("/")
                        result["source"] = "musicbrainz_url-rel"
                        break
            
            # Fallback to mapping table
            if not result["aoty_slug"] and DATABASE_URL:
                try:
                    conn = get_db_conn()
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT aoty_slug, name FROM mb_aoty_mapping WHERE mb_id = %s AND type = %s",
                        (mb_id, type)
                    )
                    row = cur.fetchone()
                    cur.close()
                    conn.close()
                    if row:
                        result["aoty_slug"] = row[0]
                        result["name"] = row[1] or result["name"]
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
    
    # First lookup AOTY slug
    lookup = await lookup_mb_id(mb_album_id, "release", x_api_key)
    
    if not lookup.get("aoty_slug"):
        # Try release-group
        lookup = await lookup_mb_id(mb_album_id, "release-group", x_api_key)
    
    if not lookup.get("aoty_slug"):
        raise HTTPException(status_code=404, detail="AOTY album slug not found for this MB ID")
    
    aoty_slug = lookup["aoty_slug"]
    
    # Get AOTY album data
    cache_key = f"album:{aoty_slug}"
    cached = await get_cached(cache_key)
    if cached:
        return cached
    
    try:
        # For albums, we need to scrape the AOTY album page
        url = f"https://www.albumoftheyear.org/album/{aoty_slug}/"
        page = await run_in_threadpool(
            lambda: BeautifulSoup(urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"})).read(), "html.parser")
        )
        
        result = {"mb_album_id": mb_album_id, "aoty_slug": aoty_slug, "url": url}
        
        # Extract rating
        rating_elem = page.find(class_="albumRating")
        if rating_elem:
            import re
            match = re.search(r'(\d+\.?\d*)', rating_elem.get_text())
            if match:
                result["rating"] = float(match.group(1))
        
        # Extract vote count
        page_text = page.get_text()
        rating_match = re.search(r'Based on\s+([\d,]+)\s+ratings?', page_text, re.I)
        if rating_match:
            result["rating_count"] = int(rating_match.group(1).replace(',', ''))
        
        await set_cache(cache_key, result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {str(e)}")


