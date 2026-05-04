import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import re
import time
from datetime import datetime, timezone, timedelta

FEED_PAGES = [
    'https://earmilk.com/feed',
    'https://earmilk.com/feed?paged=2',
    'https://earmilk.com/feed?paged=3',
    'https://earmilk.com/feed?paged=4',
    'https://earmilk.com/feed?paged=5',
]

def fetch_url(url, timeout=10):
    req = urllib.request.Request(url, headers={'User-Agent': 'EarmilkFeed/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode('utf-8')

def artwork_from_itunes(artist, song):
    for q in [artist + ' ' + song, song + ' ' + artist, artist]:
        try:
            url = 'https://itunes.apple.com/search?term=' + urllib.parse.quote(q) + '&media=music&limit=5&entity=song'
            data = json.loads(fetch_url(url))
            results = data.get('results', [])
            for r in results:
                if artist.lower() in r.get('artistName', '').lower():
                    art = r.get('artworkUrl100', '').replace('100x100bb', '400x400bb')
                    if art:
                        return art
            if results:
                art = results[0].get('artworkUrl100', '').replace('100x100bb', '400x400bb')
                if art:
                    return art
        except Exception as e:
            print('iTunes error: ' + str(e))
        time.sleep(0.3)
    return ''

def artwork_from_musicbrainz(artist, song):
    try:
        q = urllib.parse.quote('"' + song + '" AND artist:"' + artist + '"')
        url = 'https://musicbrainz.org/ws/2/recording?query=' + q + '&limit=3&fmt=json'
        data = json.loads(fetch_url(url))
        for rec in data.get('recordings', []):
            for release in rec.get('releases', []):
                rid = release.get('id', '')
                if not rid:
                    continue
                try:
                    art_url = 'https://coverartarchive.org/release/' + rid + '/front-500'
                    req = urllib.request.Request(art_url, headers={'User-Agent': 'EarmilkFeed/1.0'})
                    with urllib.request.urlopen(req, timeout=6) as resp:
                        if resp.status == 200:
                            return resp.url
                except Exception:
                    continue
                time.sleep(0.2)
    except Exception as e:
        print('MusicBrainz error: ' + str(e))
    time.sleep(0.5)
    return ''

def fetch_artwork(artist, song):
    art = artwork_from_itunes(artist, song)
    if art:
        return art
    return artwork_from_musicbrainz(artist, song)

VERBS = (
    r'shares?|releases?|drops?|returns?|delivers?|unveils?|presents?|'
    r'launches?|announces?|debuts?|steps|marks|dives|channels|hosts|'
    r'explores?|reveals?|offers?|brings?|gives?|puts?\s+out|'
    r'links?\s+up|teams?\s+up|gets?|makes?|takes?|shows?|'
    r'moves?|rebuilds?|slingshots?|lights?\s+up|'
    r'captures?|crafts?|creates?|blends?|fuses?|mixes?|'
    r'turns?|reclaims?|reimagines?|pushes?|reflects?|deals?|finds?|chats?'
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

def get_archive_urls(html):
    pattern = r'https://earmilk\.com/2026/\d{2}/\d{2}/[a-z0-9\-]+/'
    urls = re.findall(pattern, html)
    return list(dict.fromkeys(urls))

def scrape_archive_page(url, url_to_post, song_to_post, existing_posts):
    try:
        html = fetch_url(url, timeout=15)
        article_urls = get_archive_urls(html)
        print('  Found ' + str(len(article_urls)) + ' article URLs on ' + url)
        added = 0
        for art_url in article_urls:
            if art_url in url_to_post:
                continue
            try:
                art_html = fetch_url(art_url, timeout=10)
                title_match = re.search(r'<title>([^<]+)\s*[–-]\s*EARMILK', art_html)
                if not title_match:
                    continue
                headline = title_match.group(1).strip()
                date_match = re.search(r'"datePublished":"(\d{4}-\d{2}-\d{2})', art_html)
                sort_date = date_match.group(1).replace('-', '') if date_match else '20260101'
                month_day = datetime.strptime(sort_date, '%Y%m%d').strftime('%b %-d') if sort_date != '20260101' else ''
                cat_matches = re.findall(r'"category"[^>]*>([^<]+)<', art_html)
                genre = get_genre([c.strip() for c in cat_matches if c.strip()])
                artist, song = extract_artist_song(headline)
                print('  ARCHIVE: ' + repr(headline) + ' -> ' + repr(artist) + ' / ' + repr(song))
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
                    'date': month_day,
                    'sort_date': sort_date,
                    'url': art_url,
                    'artwork': artwork
                }
                existing_posts.append(new_post)
                url_to_post[art_url] = new_post
                song_to_post[song_key] = new_post
                print('  -> ADDED: ' + artist + ' - ' + song)
                added += 1
                time.sleep(0.5)
            except Exception as e:
                print('  Article error: ' + str(e))
        return added
    except Exception as e:
        print('Archive page error: ' + str(e))
        return 0

def parse_feed(xml, url_to_post, song_to_post, existing_posts):
    root = ET.fromstring(xml)
    added = 0
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
        print('NEW: ' + repr(headline) + ' -> ' + repr(artist) + ' / ' + repr(song))
        if not artist or not song:
            print('SKIPPED')
            continue
        song_key = artist.lower() + '|' + song.lower()
        if song_key in song_to_post:
            print('DUPLICATE SKIPPED')
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
        print('ADDED: ' + artist + ' - ' + song)
        added += 1
    return added

def get_recent_archive_dates():
    dates = []
    now = datetime.now(timezone(timedelta(hours=-7)))
    for i in range(7):
        d = now - timedelta(days=i)
        dates.append(d.strftime('%Y/%m/%d'))
    return dates

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
            print('fetching artwork: ' + p['artist'] + ' - ' + p['song'])
            p['artwork'] = fetch_artwork(p['artist'], p['song'])
        if not p.get('sort_date'):
            p['sort_date'] = display_to_sort(p.get('date', 'Jan 1'))

    total_added = 0

    print('Fetching RSS feeds...')
    for feed_url in FEED_PAGES:
        try:
            xml = fetch_url(feed_url, timeout=15)
            added = parse_feed(xml, url_to_post, song_to_post, existing_posts)
            total_added += added
            print('RSS page added ' + str(added) + ' posts')
            time.sleep(1)
        except Exception as e:
            print('RSS error: ' + str(e))

    print('Scraping daily archive pages...')
    for date_path in get_recent_archive_dates():
        archive_url = 'https://earmilk.com/' + date_path + '/'
        print('Checking: ' + archive_url)
        added = scrape_archive_page(archive_url, url_to_post, song_to_post, existing_posts)
        total_added += added
        time.sleep(1)

    existing_posts.sort(key=lambda p: p.get('sort_date', '20260101'), reverse=True)
    out = {
        'updated': datetime.now(timezone(timedelta(hours=-7))).strftime('%b %-d, %Y %I:%M %p PT'),
        'posts': existing_posts
    }
    with open('posts.json', 'w') as f:
        json.dump(out, f, indent=2)
    print('Done. Total added: ' + str(total_added) + '. Total posts: ' + str(len(existing_posts)))

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('Fatal error: ' + str(e))
        import sys
        sys.exit(0)
