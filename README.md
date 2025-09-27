# AlbumOfTheYearWrapper

A light weight python library that acts as an API for https://www.albumoftheyear.org/
<br>
![Tests](https://github.com/JahsiasWhite/AlbumOfTheYearAPI/workflows/Tests/badge.svg)
<img alt="PyPI" src="https://img.shields.io/pypi/v/album-of-the-year-api">

## Description

Gets data from https://www.albumoftheyear.org/. The website doesn't currently provide API support so web parsing is required to obtain data. Because of this,
and according to https://www.albumoftheyear.org/robots.txt, searching and POST requests are not allowed.

## Installation

```
pip install album-of-the-year-api
```

or upgrade

```
pip install album-of-the-year-api --upgrade
```

## Usage

**Examples**

Here's a quick example of getting a specific users follower count

```
from albumoftheyearapi import AOTY

client = AOTY()
print(client.user_follower_count('jahsias'))

>> 0
```

If you don't need the full functionality, you can also import only the neccesary files

```
from albumoftheyearapi.artist import ArtistMethods

client = ArtistMethods()
print(client.artist_albums('183-kanye-west'))

>> ['Donda 2', 'Donda', 'JESUS IS KING', 'ye', 'The Life of Pablo', 'Yeezus', 'Watch the Throne', 'My Beautiful Dark Twisted Fantasy', '808s & Heartbreak', 'Graduation', 'Late Registration', 'The College Dropout']
```

Notice artists also need their unique id along with their name

Each function also is able to return the data in JSON format

```
from albumoftheyearapi import AOTY

client = AOTY()
print(client.artist_critic_score_json('183-kanye-west'))

>> {"critic_score": "73"}
```

For detailed information, refer to the [Full API Documentation](docs/api_reference.md).
