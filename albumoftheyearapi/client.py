""" All methods used to get site data """

from albumoftheyearapi.user import UserMethods
from albumoftheyearapi.artist import ArtistMethods
from albumoftheyearapi.album import AlbumMethods
from albumoftheyearapi.genre import GenreMethods


class AOTY(UserMethods, ArtistMethods, AlbumMethods, GenreMethods):
    """A light weight python library that acts as an API for https://www.albumoftheyear.org"""

    def __init__(self):
        """Initializes the required variables for getting website data.
        Required for easier caching
        """
        self.user = ""
        self.artist = ""
        self.url = ""
        self.user_url = "https://www.albumoftheyear.org/user/"
        self.artist_url = "https://www.albumoftheyear.org/artist/"
        self.upcoming_album_class = "albumBlock five small"
        self.aoty_albums_per_page = 60
        self.page_limit = 21
        # Genre stuff
        self.genre_base_url = "https://www.albumoftheyear.org/genre/"
        self.genre_page_url = ""
        self.genre_page = None
