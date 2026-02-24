# API Documentation

## Table of Contents

- [Artist Methods](#artist-methods)
- [Album Methods](#album-methods)
- [User Methods](#user-methods)

## Artist Methods

An artist id is a unique number followed by the artist's display name.<br>
EX: 589-the-strokes

`artist_albums(artist)`
<br>Returns a list of all albums by an artist
<br> Parameters:

- artist - artist id

`artist_mixtapes(artist)`
<br>Returns a list of all mixtapes by an artist
<br>Parameters:

- artist - artist id

`artist_eps(artist)`
<br>Returns a list of all eps by an artist
<br>Parameters:

- artist - artist id

`artist_singles(artist)`
<br>Returns a list of all singles by an artist
<br>Parameters:

- artist - artist id

`artist_name(artist)`
<br>Returns the name of the artist
<br>Parameters:

- artist - artist id

`artist_critic_score(artist)`
<br>Returns the critic score of the artist
<br>Parameters:

- artist - artist id

`artist_user_score(artist)`
<br>Returns the user score of the artist
<br>Parameters:

- artist - artist id

`artist_total_score(artist)`
<br>Returns the average of the critic and users score of the artist
<br>Parameters:

- artist - artist id

`artist_follower_count(artist)`
<br>Returns the follower count of the artist
<br>Parameters:

- artist - artist id

`artist_details(artist)`
<br>Returns the detials of the artist
<br>Parameters:

- artist - artist id

`artist_top_songs(artist)`
<br>Returns a list of the top songs of the artist
<br>Parameters:

- artist - artist id

`artist_live_albums(artist, as_json=False)`
<br>Returns a list of all live albums by an artist
<br>Parameters:

- artist - artist id
- as_json (bool, optional): If True, returns the result as a JSON string. Defaults to False.

`artist_compilations(artist, as_json=False)`
<br>Returns a list of all compilations by an artist
<br>Parameters:

- artist - artist id
- as_json (bool, optional): If True, returns the result as a JSON string. Defaults to False.

`artist_appears_on(artist, as_json=False)`
<br>Returns a list of albums the artist appears on
<br>Parameters:

- artist - artist id
- as_json (bool, optional): If True, returns the result as a JSON string. Defaults to False.

`similar_artists(artist)`
<br>Returns a list of similar artists to the given artist
<br>Parameters:

- artist - artist id

## Album Methods

`upcoming_releases_by_limit(total)`
<br>Returns a list of size total comtaining upcoming album releases
<br>Parameters:

- total - integer

`upcoming_releases_by_page(page_number)`
<br>Returns a list of upcoming album releases on the given page idx
<br>Parameters:

- page_number - integer

`upcoming_releases_by_date(month, day)`
<br>Returns a list of upcoming album releases on the given date
<br>Parameters:

- month - integer
- day - integer

## User Methods

`user_rating_count(user)`
<br>Returns the number of ratings by a user
<br>Parameters:

- user - username

`user_review_count(user)`
<br>Returns the number of reviews by a user
<br>Parameters:

- user - username

`user_list_count(user)`
<br>Returns the number of lists by a user
<br>Parameters:

- user - username

`user_follower_count(user)`
<br>Returns the number of followers a user has
<br>Parameters:

- user - username

`user_about(user)`
<br>Returns the about page of a user
<br>Parameters:

- user - username

`user_rating_distribution(user)`
<br>Returns a list of a users rating distribution
<br>Parameters:

- user - username

`user_ratings(user, page=1)`
<br>Returns a list of the user's ratings from a single ratings page.
<br>Parameters:

- user (str): The username to fetch ratings for.
- page (int, optional): Which ratings page to fetch. Defaults to 1.

`user_ratings_all(user, max_pages=None)`
<br>Returns a list of all the user's ratings across all pages.
<br>Parameters:

- user (str): The username to fetch ratings for.
- max_pages (int, optional): Maximum number of pages to fetch. If None, fetches until no more ratings exist.
  Useful for limiting requests on users with very large rating histories.

`user_perfect_scores(user)`
<br>Returns a list of the users perfect scores
<br>Parameters:

- user - username

`user_liked_music(user)`
<br>Returns a list of the users liked music
<br>Parameters:

- user - username

`user_reviews(user, page=1, as_json=False)`
<br>Returns a list of the user's reviews from a single reviews page. Each entry contains the artist, album, rating, and review text (may be truncated for long reviews).
<br>Parameters:

- user (str): The username to fetch reviews for.
- page (int, optional): Which reviews page to fetch. Defaults to 1.
- as_json (bool, optional): If True, returns the result as a JSON string. Defaults to False.
