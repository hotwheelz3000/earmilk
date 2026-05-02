import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import re
import time
from datetime import datetime, timezone, timedelta

FEED_URL = 'https://earmilk.com/feed'

def fetch_url(url, timeout=10):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode('utf-8')

def fetch_artwork(artist, song):
    try:
        q = urllib.parse.quote((artist + ' ' + song).strip())
        url = 'https://itunes.apple.com/search?term=' + q + '&media=music&limit=1'
        data = json.loads(fetch_url(url))
        if data.get('results'):
            art = data['results'][0].get('artworkUrl100', '')
            if art:
                return art.replace('100x100bb', '400x400bb')
    except Exception as e:
        print('  artwork error: ' + str(e))
    time.sleep(0.4)
    return ''

VERBS = (
    r'shares?|releases?|drops?|returns?|delivers?|unveils?|presents?|'
    r'launches?|announces?|debuts?|steps|marks|dives|channels|hosts|'
    r'explores?|reveals?|offers?|brings?|gives?|puts?\s+out|'
    r'links?\s+up|teams?\s+up|gets?|makes?|takes?|shows?|'
    r'moves?|rebuilds?|slingshots?|lights?\s+up|'
    r'captures?|crafts?|creates?|blends?|fuses?|mixes?'
)

def extract_artist_song(headline):
    song_first = re.match(r'^\u201c(.+?)\u201d\s+is\s+', headline, re.IGNORECASE)
    if song_first:
        song = song_first.group(1).strip()
        rest = re.sub(r'\bat\s+(her|his|its)\s+\w+\s*$', '', headline, flags=re.IGNORECASE)
        names = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', rest)
        skip = {'Wash', 'Rock', 'Riser', 'The', 'At', 'Her', 'His'}
        names = [n for n in names if n not in skip]
        artist = names[-1] if names else ''
        if artist and song:
            return artist, song

    possessive = re.match(r'^(.+?)[\u2019\']s\s+\u201c(.+?)\u201d', headline)
    if possessive:
        return possessive.group(1).strip(), possessive.group(2).strip()

    artist_match = re.match(r'^(.+?)\s+(?:' + VERBS + r')\b', headline, re.IGNORECASE)
    artist = ''
    if artist_match:
        artist = re.sub(r'[\u2019\']s?\s*$', '', artist_match.group(1)).strip()
        artist = re.sub(r'[,;:]+$', '', artist).strip()
        artist = re.sub(r'\s+and\s+', ' & ', artist)

    quoted = re.findall(r'\u201c([^\u201d]{3,80})\u201d', headline)
    song = quoted[0].strip() if quoted else ''

    if artist and song:
        return artist, song
    return '', ''

def parse_date(date_str):
    try:
        dt = datetime.strptime(date_str[:25], '%a, %d %b %Y %H:%M:%S')
        return dt.strftime('%b %-d')
    except Exception:
        return date_str[:10] if date_str else ''

def parse_sort_date(date_str):
    try:
        dt = datetime.strptime(date_str[:25], '%a, %d %b %Y %H:%M:%S')
        return dt.strftime('%Y%m%d')
    except Exception:
        return '20260101'

def display_to_sort(display_date):
    try:
        dt = datetime.strptime(display_date + ' 2026', '%b %d %Y')
        return dt.strftime('%Y%m%d')
    except Exception:
        return '20260101'

def get_genre(categories):
    skip = {'new music', 'music', 'news', 'featured', 'mainstage', 'music videos'}
    for c in categories:
        if c.lower() not in skip:
            return c
    return categories[0] if categories else ''

def main():
    try:
        with open('posts.json') as f:
            existing = json.load(f)
        existing_posts = existing.get('posts', [])
    except Exception:
        existing_posts = []

    url_to_post = {p['url']: p for p in existing_posts}
    song_to_post = {(p.get('artist', '').lower() + '|' + p.get('song', '').lower()): p for p in existing_posts}
    print('Loaded ' + str(len(existing_posts)) + ' existing posts')

    for p in existing_posts:
        if not p.get('artwork') and p.get('artist') and p.get('song'):
            print('  fetching artwork: ' + p['artist'] + ' - ' + p['song'])
            p['artwork'] = fetch_artwork(p['artist'], p['song'])
        if not p.get('sort_date'):
            p['sort_date'] = display_to_sort(p.get('date', 'Jan 1'))

    print('Fetching RSS feed...')
    try:
        xml = fetch_url(FEED_URL, timeout=15)
        root = ET.fromstring(xml)

        for item in root.findall('.//item'):
            title_el = item.find('title')
            link_el = item.find('link')
            pub_el = item.find('pubDate')
            cats = [c.text.strip() for c in item.findall('category') if c.text]

            headline = title_el.text.strip() if title_el is not None and title_el.text else ''
            link = link_el.text.strip().split('?')[0] if link_el is not None and link_el.text else '#'
            pub_raw = pub_el.text.strip() if pub_el is not None and pub_el.text else ''
            date = parse_date(pub_raw)
            sort_date = parse_sort_date(pub_raw)
            genre = get_genre(cats)

            if link in url_to_post:
                continue

            artist, song = extract_artist_song(headline)
            print('  NEW: ' + repr(headline) + ' -> ' + repr(artist) + ' / ' + repr(song))

            if not artist or not song:
                print('  -> SKIPPED')
                continue

            song_key = artist.lower() + '|' + song.lower()
            if song_key in song_to_post:
                print('  -> DUPLICATE SKIPPED')
                continue

            artwork = fetch_artwork(artist, song)
            new_post = {
                'artist': artist,
                'song': song,
                'genre': genre,
                'date': date,
                'sort_date': sort_date,
                'url': link,
                'artwork': artwork
            }
            existing_posts.append(new_post)
            url_to_post[link] = new_post
            song_to_post[song_key] = new_post
            print('  -> ADDED: ' + artist + ' - ' + song)

    except Exception as e:
        print('RSS fetch error: ' + str(e))

    existing_posts.sort(key=lambda p: p.get('sort_date', '20260101'), reverse=True)

    out = {
        'updated': datetime.now(timezone(timedelta(hours=-7))).strftime('%b %-d, %Y %I:%M %p PT'),
        'posts': existing_posts
    }

    with open('posts.json', 'w') as f:
        json.dump(out, f, indent=2)

    print('Done. Total ' + str(len(existing_posts)) + ' posts.')

if __name__ == '__main__':
    main()import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import re
import time
from datetime import datetime, timezone, timedelta

FEED_URL = 'https://earmilk.com/feed'

def fetch_url(url, timeout=10):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode('utf-8')

def fetch_artwork(artist, song):
    try:
        q = urllib.parse.quote((artist + ' ' + song).strip())
        url = 'https://itunes.apple.com/search?term=' + q + '&media=music&limit=1'
        data = json.loads(fetch_url(url))
        if data.get('results'):
            art = data['results'][0].get('artworkUrl100', '')
            if art:
                return art.replace('100x100bb', '400x400bb')
    except Exception as e:
        print('  artwork error: ' + str(e))
    time.sleep(0.4)
    return ''

VERBS = (
    r'shares?|releases?|drops?|returns?|delivers?|unveils?|presents?|'
    r'launches?|announces?|debuts?|steps|marks|dives|channels|hosts|'
    r'explores?|reveals?|offers?|brings?|gives?|puts?\s+out|'
    r'links?\s+up|teams?\s+up|gets?|makes?|takes?|shows?|'
    r'moves?|rebuilds?|slingshots?|lights?\s+up|'
    r'captures?|crafts?|creates?|blends?|fuses?|mixes?'
)

def extract_artist_song(headline):
    song_first = re.match(r'^\u201c(.+?)\u201d\s+is\s+', headline, re.IGNORECASE)
    if song_first:
        song = song_first.group(1).strip()
        rest = re.sub(r'\bat\s+(her|his|its)\s+\w+\s*$', '', headline, flags=re.IGNORECASE)
        names = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', rest)
        skip = {'Wash', 'Rock', 'Riser', 'The', 'At', 'Her', 'His'}
        names = [n for n in names if n not in skip]
        artist = names[-1] if names else ''
        if artist and song:
            return artist, song

    possessive = re.match(r'^(.+?)[\u2019\']s\s+\u201c(.+?)\u201d', headline)
    if possessive:
        return possessive.group(1).strip(), possessive.group(2).strip()

    artist_match = re.match(r'^(.+?)\s+(?:' + VERBS + r')\b', headline, re.IGNORECASE)
    artist = ''
    if artist_match:
        artist = re.sub(r'[\u2019\']s?\s*$', '', artist_match.group(1)).strip()
        artist = re.sub(r'[,;:]+$', '', artist).strip()
        artist = re.sub(r'\s+and\s+', ' & ', artist)

    quoted = re.findall(r'\u201c([^\u201d]{3,80})\u201d', headline)
    song = quoted[0].strip() if quoted else ''

    if artist and song:
        return artist, song
    return '', ''

def parse_date(date_str):
    try:
        dt = datetime.strptime(date_str[:25], '%a, %d %b %Y %H:%M:%S')
        return dt.strftime('%b %-d')
    except Exception:
        return date_str[:10] if date_str else ''

def parse_sort_date(date_str):
    try:
        dt = datetime.strptime(date_str[:25], '%a, %d %b %Y %H:%M:%S')
        return dt.strftime('%Y%m%d')
    except Exception:
        return '20260101'

def display_to_sort(display_date):
    try:
        dt = datetime.strptime(display_date + ' 2026', '%b %d %Y')
        return dt.strftime('%Y%m%d')
    except Exception:
        return '20260101'

def get_genre(categories):
    skip = {'new music', 'music', 'news', 'featured', 'mainstage', 'music videos'}
    for c in categories:
        if c.lower() not in skip:
            return c
    return categories[0] if categories else ''

def main():
    try:
        with open('posts.json') as f:
            existing = json.load(f)
        existing_posts = existing.get('posts', [])
    except Exception:
        existing_posts = []

    url_to_post = {p['url']: p for p in existing_posts}
    song_to_post = {(p.get('artist', '').lower() + '|' + p.get('song', '').lower()): p for p in existing_posts}
    print('Loaded ' + str(len(existing_posts)) + ' existing posts')

    for p in existing_posts:
        if not p.get('artwork') and p.get('artist') and p.get('song'):
            print('  fetching artwork: ' + p['artist'] + ' - ' + p['song'])
            p['artwork'] = fetch_artwork(p['artist'], p['song'])
        if not p.get('sort_date'):
            p['sort_date'] = display_to_sort(p.get('date', 'Jan 1'))

    print('Fetching RSS feed...')
    try:
        xml = fetch_url(FEED_URL, timeout=15)
        root = ET.fromstring(xml)

        for item in root.findall('.//item'):
            title_el = item.find('title')
            link_el = item.find('link')
            pub_el = item.find('pubDate')
            cats = [c.text.strip() for c in item.findall('category') if c.text]

            headline = title_el.text.strip() if title_el is not None and title_el.text else ''
            link = link_el.text.strip() if link_el is not None and link_el.text else '#'
            pub_raw = pub_el.text.strip() if pub_el is not None and pub_el.text else ''
            date = parse_date(pub_raw)
            sort_date = parse_sort_date(pub_raw)
            genre = get_genre(cats)

            if link in url_to_post:
                continue

            artist, song = extract_artist_song(headline)
            print('  NEW: ' + repr(headline) + ' -> ' + repr(artist) + ' / ' + repr(song))

            if not artist or not song:
                print('  -> SKIPPED')
                continue

            song_key = artist.lower() + '|' + song.lower()
            if song_key in song_to_post:
                print('  -> DUPLICATE SKIPPED')
                continue

            artwork = fetch_artwork(artist, song)
            new_post = {
                'artist': artist,
                'song': song,
                'genre': genre,
                'date': date,
                'sort_date': sort_date,
                'url': link,
                'artwork': artwork
            }
            existing_posts.append(new_post)
            url_to_post[link] = new_post
            song_to_post[song_key] = new_post
            print('  -> ADDED: ' + artist + ' - ' + song)

    except Exception as e:
        print('RSS fetch error: ' + str(e))

    existing_posts.sort(key=lambda p: p.get('sort_date', '20260101'), reverse=True)

    out = {
        'updated': datetime.now(timezone(timedelta(hours=-7))).strftime('%b %-d, %Y %I:%M %p PT'),
        'posts': existing_posts
    }

    with open('posts.json', 'w') as f:
        json.dump(out, f, indent=2)

    print('Done. Total ' + str(len(existing_posts)) + ' posts.')

if __name__ == '__main__':
    main()
