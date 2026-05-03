import json
import os
import psycopg2
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup
from typing import Optional, Dict, Any, List
import hashlib
from datetime import datetime, timedelta


class AOTY:
    """Main API class with PostgreSQL caching"""

    def __init__(self, cache_ttl: int = 604800):
        self.artist_url = "https://www.albumoftheyear.org/artist/"
        self.cache_ttl = cache_ttl
        self.database_url = os.getenv("DATABASE_URL")

    def _get_cache_key(self, identifier: str, method: str) -> str:
        return hashlib.md5(f"{identifier}:{method}".encode()).hexdigest()

    def _get_db_conn(self):
        if self.database_url:
            return psycopg2.connect(self.database_url, connect_timeout=5)
        return None

    def _get_from_cache(self, key: str) -> Optional[Any]:
        if not self.database_url:
            return None
        try:
            conn = self._get_db_conn()
            cur = conn.cursor()
            cur.execute("SELECT data, cached_at FROM cache WHERE id_key = %s", (key,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row:
                data, cached_at = row
                if datetime.utcnow() - cached_at < timedelta(seconds=self.cache_ttl):
                    return data
        except Exception as e:
            print(f"Cache read error: {e}")
        return None

    def _set_cache(self, key: str, data: Any):
        if not self.database_url:
            return
        try:
            conn = self._get_db_conn()
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

    def _fetch_page(self, url: str) -> BeautifulSoup:
        req = Request(url, headers={"User-Agent": "Mozilla/6.0"})
        page = urlopen(req).read()
        return BeautifulSoup(page, "html.parser")

    def artist_critic_score(self, artist_id: str) -> Dict[str, Any]:
        """Get critic score + review count for artist"""
        cache_key = self._get_cache_key(artist_id, 'critic_score')
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        url = f"{self.artist_url}{artist_id}/"
        page = self._fetch_page(url)

        result = {"artist_id": artist_id, "critic_score": None, "review_count": None}

        # Extract critic score
        critic_elem = page.find(class_="artistCriticScore")
        if critic_elem:
            score_text = critic_elem.get_text(strip=True)
            import re
            match = re.search(r'(\d+)', score_text)
            if match:
                result["critic_score"] = int(match.group(1))

        # Extract review count ("Based on X reviews")
        page_text = page.get_text()
        review_match = re.search(r'Based on\s+([\d,]+)\s+reviews?', page_text, re.I)
        if review_match:
            result["review_count"] = int(review_match.group(1).replace(',', ''))

        self._set_cache(cache_key, result)
        return result

    def artist_user_score(self, artist_id: str) -> Dict[str, Any]:
        """Get user score + rating count for artist"""
        cache_key = self._get_cache_key(artist_id, 'user_score')
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        url = f"{self.artist_url}{artist_id}/"
        page = self._fetch_page(url)

        result = {"artist_id": artist_id, "user_score": None, "rating_count": None}

        # Extract user score
        user_elem = page.find(class_="artistUserScore")
        if user_elem:
            score_text = user_elem.get_text(strip=True)
            import re
            match = re.search(r'(\d+)', score_text)
            if match:
                result["user_score"] = int(match.group(1))

        # Extract rating count ("Based on X ratings")
        page_text = page.get_text()
        rating_match = re.search(r'Based on\s+([\d,]+)\s+ratings?', page_text, re.I)
        if rating_match:
            result["rating_count"] = int(rating_match.group(1).replace(',', ''))

        self._set_cache(cache_key, result)
        return result

    def artist_albums(self, artist_id: str) -> List[str]:
        """Get list of artist albums"""
        cache_key = self._get_cache_key(artist_id, 'albums')
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        url = f"{self.artist_url}{artist_id}/"
        page = self._fetch_page(url)

        albums = []
        album_divs = page.find_all("div", class_="albumTitle")
        for div in album_divs:
            text = div.get_text(strip=True)
            if text:
                albums.append(text)

        self._set_cache(cache_key, albums)
        return albums

    def artist_follower_count(self, artist_id: str) -> Dict[str, Any]:
        """Get follower count"""
        cache_key = self._get_cache_key(artist_id, 'followers')
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        url = f"{self.artist_url}{artist_id}/"
        page = self._fetch_page(url)

        result = {"artist_id": artist_id, "follower_count": 0}

        follow_elem = page.find(class_="followCount")
        if follow_elem:
            text = follow_elem.get_text(strip=True)
            import re
            match = re.search(r'(\d+)', text)
            if match:
                result["follower_count"] = int(match.group(1))

        self._set_cache(cache_key, result)
        return result

    def get_artist_summary(self, artist_id: str) -> Dict[str, Any]:
        """Get comprehensive artist data"""
        return {
            "artist_id": artist_id,
            "critic": self.artist_critic_score(artist_id),
            "user": self.artist_user_score(artist_id),
            "albums": self.artist_albums(artist_id),
            "followers": self.artist_follower_count(artist_id)
        }
