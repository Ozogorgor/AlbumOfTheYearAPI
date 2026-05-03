import json
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup
from typing import Optional, Dict, Any, List
import hashlib
from datetime import datetime, timedelta


class AOTY:
    """Main API class with caching support"""

    def __init__(self, cache_ttl: int = 604800):
        self.artist_url = "https://www.albumoftheyear.org/artist/"
        self.cache_ttl = cache_ttl
        self._cache = {}

    def _get_cache_key(self, identifier: str, method: str) -> str:
        return hashlib.md5(f"{identifier}:{method}".encode()).hexdigest()

    def _get_from_cache(self, key: str) -> Optional[Any]:
        if key in self._cache:
            entry = self._cache[key]
            if datetime.now() - entry['timestamp'] < timedelta(seconds=self.cache_ttl):
                return entry['data']
        return None

    def _set_cache(self, key: str, data: Any):
        self._cache[key] = {
            'data': data,
            'timestamp': datetime.now()
        }

    def _fetch_page(self, url: str) -> BeautifulSoup:
        req = Request(url, headers={"User-Agent": "Mozilla/6.0"})
        page = urlopen(req).read()
        return BeautifulSoup(page, "html.parser")

    def artist_critic_score(self, artist_id: str) -> Dict[str, Any]:
        """Get critic score for artist (score + vote count if available)"""
        cache_key = self._get_cache_key(artist_id, 'critic_score')
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        url = f"{self.artist_url}{artist_id}/"
        page = self._fetch_page(url)

        result = {"artist_id": artist_id, "critic_score": None, "vote_count": None}

        # Extract critic score
        critic_elem = page.find(class_="artistCriticScore")
        if critic_elem:
            score_text = critic_elem.get_text(strip=True)
            # Try to extract numeric score
            import re
            match = re.search(r'(\d+)', score_text)
            if match:
                result["critic_score"] = int(match.group(1))

        # Extract vote count (if available in page)
        # Note: AOTY may not expose vote counts directly
        # This is a placeholder for when available

        self._set_cache(cache_key, result)
        return result

    def artist_user_score(self, artist_id: str) -> Dict[str, Any]:
        """Get user score for artist"""
        cache_key = self._get_cache_key(artist_id, 'user_score')
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        url = f"{self.artist_url}{artist_id}/"
        page = self._fetch_page(url)

        result = {"artist_id": artist_id, "user_score": None, "vote_count": None}

        user_elem = page.find(class_="artistUserScore")
        if user_elem:
            score_text = user_elem.get_text(strip=True)
            import re
            match = re.search(r'(\d+)', score_text)
            if match:
                result["user_score"] = int(match.group(1))

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
