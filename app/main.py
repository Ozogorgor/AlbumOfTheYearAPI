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
    if DATABASE_URL:
        try:
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute("SELECT data, cached_at FROM cache WHERE id_key = %s", (cache_key,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row:
                data, cached_at = row
                if datetime.utcnow() - cached_at < timedelta(seconds=CACHE_TTL):
                    return data
        except Exception:
            pass
    
    try:
        data = await run_in_threadpool(aoty.get_artist_summary, artist_id)
        
        if DATABASE_URL:
            try:
                conn = get_db_conn()
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO cache (id_key, data, cached_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id_key) DO UPDATE SET data = EXCLUDED.data, cached_at = EXCLUDED.cached_at
                """, (cache_key, Json(data), datetime.utcnow()))
                conn.commit()
                cur.close()
                conn.close()
            except Exception as e:
                print(f"Cache write error: {e}")
        
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {str(e)}")


@app.get("/artist/{artist_id}/critic")
async def get_critic_score(
    artist_id: str,
    x_api_key: Optional[str] = Header(None)
):
    await verify_api_key(x_api_key)
    
    try:
        data = await run_in_threadpool(aoty.artist_critic_score, artist_id)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {str(e)}")


@app.get("/artist/{artist_id}/user")
async def get_user_score(
    artist_id: str,
    x_api_key: Optional[str] = Header(None)
):
    await verify_api_key(x_api_key)
    
    try:
        data = await run_in_threadpool(aoty.artist_user_score, artist_id)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {str(e)}")


@app.get("/artist/{artist_id}/albums")
async def get_albums(
    artist_id: str,
    x_api_key: Optional[str] = Header(None)
):
    await verify_api_key(x_api_key)
    
    try:
        data = await run_in_threadpool(aoty.artist_albums, artist_id)
        return {"artist_id": artist_id, "albums": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {str(e)}")


@app.get("/artist/{artist_id}/followers")
async def get_followers(
    artist_id: str,
    x_api_key: Optional[str] = Header(None)
):
    await verify_api_key(x_api_key)
    
    try:
        data = await run_in_threadpool(aoty.artist_follower_count, artist_id)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {str(e)}")
