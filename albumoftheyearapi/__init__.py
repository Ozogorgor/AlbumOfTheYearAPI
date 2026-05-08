import json
import os
import re
import psycopg2
from psycopg2.extras import Json
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup
from typing import Optional, Dict, Any, List
import hashlib
from datetime import datetime, timedelta
import urllib.parse


class AOTY:
    """Main API class with PostgreSQL caching"""

    def __init__(self, cache_ttl: int = 604800):
        self.artist_url = "https://www.albumoftheyear.org/artist/"
        self.album_url = "https://www.albumoftheyear.org/album/"
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

    def _fetch_page_with_url(self, url: str):
        """Fetch and return (soup, final_url_after_redirects)."""
        req = Request(url, headers={"User-Agent": "Mozilla/6.0"})
        resp = urlopen(req)
        final_url = resp.geturl()
        page = BeautifulSoup(resp.read(), "html.parser")
        return page, final_url

    @staticmethod
    def _canonical_aoty_id(slug: str) -> str:
        """AOTY routes by leading numeric ID; the rest is decorative."""
        m = re.match(r"^\d+", slug or "")
        return m.group(0) if m else (slug or "")

    @staticmethod
    def _slug_from_url(url: str) -> Optional[str]:
        """Extract the AOTY slug from a final URL (handles .php and / endings)."""
        if not url:
            return None
        url = url.split("?", 1)[0].split("#", 1)[0]
        if url.endswith(".php"):
            url = url[:-4]
        url = url.rstrip("/")
        tail = url.rsplit("/", 1)[-1]
        return tail or None

    def artist_critic_score(self, artist_id: str) -> Dict[str, Any]:
        """Get critic score + review count for artist"""
        cache_key = self._get_cache_key(artist_id, 'critic_score')
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        url = f"{self.artist_url}{artist_id}/"
        page = self._fetch_page(url)

        result = {"artist_id": artist_id, "critic_score": None, "review_count": None, "success": False, "error": None}

        # Check if page loaded correctly
        if not page.find(class_="artistCriticScore") and "albumoftheyear.org" not in str(page):
            result["error"] = f"Artist page not found or invalid: {artist_id}"
            return result

        # Extract critic score
        critic_elem = page.find(class_="artistCriticScore")
        if critic_elem:
            score_text = critic_elem.get_text(strip=True)
            match = re.search(r'(\d+)', score_text)
            if match:
                result["critic_score"] = int(match.group(1))

        # Extract review count ("Based on X reviews")
        page_text = page.get_text()
        review_match = re.search(r'Based on\s+([\d,]+)\s+reviews?', page_text, re.I)
        if review_match:
            result["review_count"] = int(review_match.group(1).replace(',', ''))

        # Mark success if we got at least one piece of data
        if result["critic_score"] is not None or result["review_count"] is not None:
            result["success"] = True
        else:
            result["error"] = f"Could not extract critic score data for artist: {artist_id}"

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

        result = {"artist_id": artist_id, "user_score": None, "rating_count": None, "success": False, "error": None}

        # Check if page loaded correctly
        if not page.find(class_="artistUserScore") and "albumoftheyear.org" not in str(page):
            result["error"] = f"Artist page not found or invalid: {artist_id}"
            return result

        # Extract user score
        user_elem = page.find(class_="artistUserScore")
        if user_elem:
            score_text = user_elem.get_text(strip=True)
            match = re.search(r'(\d+)', score_text)
            if match:
                result["user_score"] = int(match.group(1))

        # Extract rating count ("Based on X ratings")
        page_text = page.get_text()
        rating_match = re.search(r'Based on\s+([\d,]+)\s+ratings?', page_text, re.I)
        if rating_match:
            result["rating_count"] = int(rating_match.group(1).replace(',', ''))

        # Mark success if we got at least one piece of data
        if result["user_score"] is not None or result["rating_count"] is not None:
            result["success"] = True
        else:
            result["error"] = f"Could not extract user score data for artist: {artist_id}"

        self._set_cache(cache_key, result)
        return result

    def artist_albums(self, artist_id: str) -> Dict[str, Any]:
        """Get list of artist albums"""
        cache_key = self._get_cache_key(artist_id, 'albums')
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        url = f"{self.artist_url}{artist_id}/"
        page = self._fetch_page(url)

        # Check if page loaded correctly
        if "albumoftheyear.org" not in str(page):
            return {"artist_id": artist_id, "albums": [], "success": False, "error": f"Artist page not found or invalid: {artist_id}"}

        albums = []
        album_divs = page.find_all("div", class_="albumTitle")
        for div in album_divs:
            text = div.get_text(strip=True)
            if text:
                albums.append(text)

        result = {"artist_id": artist_id, "albums": albums, "success": True, "error": None}
        if not albums:
            result["success"] = False
            result["error"] = f"No albums found for artist: {artist_id}"

        self._set_cache(cache_key, result)
        return result

    def artist_follower_count(self, artist_id: str) -> Dict[str, Any]:
        """Get follower count"""
        cache_key = self._get_cache_key(artist_id, 'followers')
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        url = f"{self.artist_url}{artist_id}/"
        page = self._fetch_page(url)

        result = {"artist_id": artist_id, "follower_count": 0, "success": False, "error": None}

        # Check if page loaded correctly
        if "albumoftheyear.org" not in str(page):
            result["error"] = f"Artist page not found or invalid: {artist_id}"
            return result

        follow_elem = page.find(class_="followCount")
        if follow_elem:
            text = follow_elem.get_text(strip=True)
            match = re.search(r'(\d+)', text)
            if match:
                result["follower_count"] = int(match.group(1))
                result["success"] = True
        else:
            result["error"] = f"Could not extract follower count for artist: {artist_id}"

        self._set_cache(cache_key, result)
        return result

    def search_album(self, title: str, artist: str = "") -> Optional[str]:
        """Search AOTY for album slug by title and artist"""
        try:
            # Construct search URL
            query = f"{title} {artist}".strip()
            search_url = f"https://www.albumoftheyear.org/search/?q={urllib.parse.quote(query)}"
            page = self._fetch_page(search_url)

            # Look for album links in search results
            for link in page.find_all('a', href=True):
                href = link['href']
                if '/album/' in href:
                    # Extract slug from /album/slug/ pattern
                    slug = href.split('/album/')[-1].strip('/')
                    if slug:
                        return slug

            return None
        except Exception as e:
            print(f"Search error: {e}")
            return None

    def album_summary(self, album_slug: str) -> Dict[str, Any]:
        """Scrape critic + user score and counts from an AOTY album page.

        Sends the request with just the leading numeric ID; AOTY redirects to
        the canonical slug, which is captured in result["canonical_slug"] so
        callers can repair stale mapping-table entries.
        """
        cache_key = self._get_cache_key(album_slug, 'album_summary')
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        canonical_id = self._canonical_aoty_id(album_slug)
        request_url = f"{self.album_url}{canonical_id}/"
        result = {
            "album_slug": album_slug,
            "canonical_slug": None,
            "url": request_url,
            "title": None,
            "artist": None,
            "genre": None,
            "critic_score": None,
            "critic_score_precise": None,
            "review_count": None,
            "user_score": None,
            "user_score_precise": None,
            "rating_count": None,
            "success": False,
            "error": None,
        }

        try:
            page, final_url = self._fetch_page_with_url(request_url)
        except Exception as e:
            result["error"] = f"fetch failed: {e}"
            return result

        result["url"] = final_url
        result["canonical_slug"] = self._slug_from_url(final_url)

        title_elem = page.find("h1", class_="albumTitle")
        if title_elem:
            name = title_elem.find(attrs={"itemprop": "name"})
            result["title"] = (name or title_elem).get_text(strip=True)

        artist_elem = page.find(attrs={"itemprop": "byArtist"})
        if artist_elem:
            artist_name = artist_elem.find(attrs={"itemprop": "name"})
            if artist_name:
                result["artist"] = artist_name.get_text(strip=True)

        critic_elem = page.find(class_="albumCriticScore")
        if critic_elem:
            link = critic_elem.find("a")
            if link:
                txt = link.get_text(strip=True)
                if txt and txt != "NR":
                    try:
                        result["critic_score"] = int(txt)
                    except ValueError:
                        pass
                title = link.get("title")
                if title:
                    try:
                        result["critic_score_precise"] = float(title)
                    except ValueError:
                        pass

        rating_count_elem = page.find(attrs={"itemprop": "ratingCount"})
        if rating_count_elem:
            try:
                result["review_count"] = int(rating_count_elem.get_text(strip=True))
            except ValueError:
                pass

        user_elem = page.find(class_="albumUserScore")
        if user_elem:
            link = user_elem.find("a")
            if link:
                txt = link.get_text(strip=True)
                if txt and txt != "NR":
                    try:
                        result["user_score"] = int(txt)
                    except ValueError:
                        pass
                title = link.get("title")
                if title:
                    try:
                        result["user_score_precise"] = float(title)
                    except ValueError:
                        pass

        # User-rating count lives in <strong> inside .albumUserScoreBox .numReviews;
        # source HTML is "<strong>9</strong>&nbspratings" (literal `&nbsp`, no semicolon).
        user_box = page.find(class_="albumUserScoreBox")
        if user_box:
            num_reviews = user_box.find(class_="numReviews")
            if num_reviews:
                strong = num_reviews.find("strong")
                if strong:
                    try:
                        result["rating_count"] = int(strong.get_text(strip=True).replace(",", ""))
                    except ValueError:
                        pass

        # Genre — single primary genre per album, exposed on AOTY as
        # `<a href="/genre/N-slug/">Display Name</a>` inside one of the
        # `.detailRow` rows under the album header. Cleaner than
        # Last.fm/MB tag clouds (no "album" / "favorite" noise).
        # Scoped to detailRows so unrelated /genre/ links elsewhere on
        # the page (sidebar, recommendations) can't false-positive.
        for row in page.find_all("div", class_="detailRow"):
            link = row.find("a", href=lambda h: h and h.startswith("/genre/"))
            if link:
                txt = link.get_text(strip=True)
                if txt:
                    result["genre"] = txt
                    break

        if result["critic_score"] is not None or result["user_score"] is not None:
            result["success"] = True
        else:
            result["error"] = f"No ratings found for album: {album_slug}"

        self._set_cache(cache_key, result)
        return result

    def get_artist_summary(self, artist_id: str) -> Dict[str, Any]:
        """Get comprehensive artist data"""
        critic = self.artist_critic_score(artist_id)
        user = self.artist_user_score(artist_id)
        albums = self.artist_albums(artist_id)
        followers = self.artist_follower_count(artist_id)

        # Determine overall success
        success = all([
            critic.get("success", False),
            user.get("success", False),
            albums.get("success", False),
            followers.get("success", False)
        ])

        errors = [r.get("error") for r in [critic, user, albums, followers] if r.get("error")]
        error_msg = "; ".join(errors) if errors else None

        return {
            "artist_id": artist_id,
            "critic": critic,
            "user": user,
            "albums": albums.get("albums", []),
            "followers": followers,
            "success": success,
            "error": error_msg
        }
