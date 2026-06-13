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

def itunes_lookup(artist, song):
    # Returns (artwork_url, genre) from the best iTunes match.
    for q in [artist + ' ' + song, song + ' ' + artist, artist, song]:
        if not q.strip():
            continue
        try:
            url = 'https://itunes.apple.com/search?term=' + urllib.parse.quote(q.strip()) + '&media=music&limit=5&entity=song'
            data = json.loads(fetch_url(url))
            results = data.get('results', [])
            chosen = None
            for r in results:
                if artist and artist.lower() in r.get('artistName', '').lower():
                    chosen = r
                    break
            if chosen is None and results:
                chosen = results[0]
            if chosen:
                art = chosen.get('artworkUrl100', '').replace('100x100bb', '400x400bb')
                genre = chosen.get('primaryGenreName', '')
                if art or genre:
                    return art, genre
        except Exception as e:
            print('iTunes error: ' + str(e))
        time.sleep(0.3)
    return '', ''

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

def fetch_meta(artist, song):
    # One iTunes call gives both artwork and a fallback genre.
    art, genre = itunes_lookup(artist, song)
    if not art and artist and song:
        art = artwork_from_musicbrainz(artist, song)
    return art, genre

def fetch_artwork(artist, song):
    art, _ = fetch_meta(artist, song)
    return art

VERBS = (
    r'shares?|releases?|drops?|returns?|delivers?|unveils?|presents?|'
    r'launches?|announces?|debuts?|steps|marks|dives|channels|hosts|'
    r'explores?|reveals?|offers?|brings?|gives?|puts?\s+out|'
    r'links?\s+up|teams?\s+up|gets?|makes?|takes?|shows?|'
    r'moves?|rebuilds?|slingshots?|lights?\s+up|'
    r'captures?|crafts?|creates?|blends?|fuses?|mixes?|'
    r'turns?|reclaims?|reimagines?|pushes?|reflects?|deals?|finds?|chats?|'
    r'expands?|soars?|ignites?|embraces?|paints?|navigates?|confronts?|'
    r'celebrates?|honors?|taps?|enlists?|recruits?|unleashes?|serves?|'
    r'premieres?|opens?|sets?|drops?|teases?|previews?|spotlights?'
)

def parse_headline(headline):
    # Pattern 1: "Song" is ... Artist
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

    # Pattern 2: Artist's "Song"
    possessive = re.match(r'^(.+?)[\u2019\']s\s+[\u201c"](.+?)[\u201d"]', headline)
    if possessive:
        return possessive.group(1).strip(), possessive.group(2).strip()

    # Pattern 3: Artist VERB ... "Song"
    artist_match = re.match(r'^(.+?)\s+(?:' + VERBS + r')\b', headline, re.IGNORECASE)
    artist = ''
    if artist_match:
        artist = re.sub(r'[\u2019\']s?\s*$', '', artist_match.group(1)).strip()
        artist = re.sub(r'[,;:]+$', '', artist).strip()
        artist = re.sub(r'\s+and\s+', ' & ', artist)

    # Song in smart or regular quotes
    quoted = re.findall(r'[\u201c"]([^\u201d"]{2,80})[\u201d"]', headline)
    song = quoted[0].strip() if quoted else ''

    if artist and song:
        return artist, song
    return '', ''

def extract_from_body(html, headline):
    # Try to get song from quoted strings in article body (first 4000 chars)
    body = html[:4000]

    # Song: first quoted string in body
    quoted = re.findall(r'[\u201c"]([^\u201d"]{2,60})[\u201d"]', body)
    song = quoted[0].strip() if quoted else ''

    # Artist: first <strong> tag in body
    bold = re.findall(r'<strong>([^<]{2,60})</strong>', body)
    artist = bold[0].strip() if bold else ''

    # Clean up artist if it looks like a sentence
    if artist and len(artist.split()) > 5:
        artist = ''

    return artist, song

def extract_artist_song(headline, article_html=''):
    # Try headline parsing first
    artist, song = parse_headline(headline)
    if artist and song:
        return artist, song

    # Fall back to article body if available
    if article_html:
        artist, song = extract_from_body(article_html, headline)
        if artist and song:
            return artist, song
        # Partial match - headline artist + body song, or vice versa
        h_artist, h_song = parse_headline(headline)
        b_artist, b_song = extract_from_body(article_html, headline)
        artist = h_artist or b_artist
        song = h_song or b_song
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
        return datetime.now().strftime('%Y') + '0101'

def display_to_sort(display_date):
    try:
        year = datetime.now().year
        dt = datetime.strptime(display_date + ' ' + str(year), '%b %d %Y')
        # A display date with no year that lands in the future is from last year
        if dt.date() > datetime.now().date():
            dt = dt.replace(year=year - 1)
        return dt.strftime('%Y%m%d')
    except Exception:
        return datetime.now().strftime('%Y') + '0101'

def get_genre(categories):
    skip = {
        'new music', 'music', 'news', 'featured', 'mainstage', 'music videos',
        'feature', 'features', 'album reviews', 'album review', 'reviews',
        'premiere', 'premieres', 'exclusive', 'exclusives', 'uncategorized',
        'interview', 'interviews', 'editorial', 'list', 'lists', 'playlist',
        'playlists', 'video', 'videos', 'cinematic'
    }
    for c in categories:
        if c.lower() not in skip:
            return c
    # Everything was a post-type, not a real genre -> leave blank
    return ''

def get_archive_urls(html):
    pattern = r'https://earmilk\.com/20\d{2}/\d{2}/\d{2}/[a-z0-9\-]+/'
    urls = re.findall(pattern, html)
    return list(dict.fromkeys(urls))

BAD_GENRES = {
    'new music', 'music', 'news', 'featured', 'mainstage', 'music videos',
    'feature', 'features', 'album reviews', 'album review', 'reviews',
    'premiere', 'premieres', 'exclusive', 'exclusives', 'uncategorized',
    'interview', 'interviews', 'editorial', 'list', 'lists', 'playlist',
    'playlists', 'video', 'videos', 'cinematic'
}

def clean_song(song):
    s = (song or '').strip()
    # strip surrounding quotes
    s = s.strip('\u201c\u201d"\'')
    # strip trailing punctuation like a stray comma/period from a sentence
    s = re.sub(r'[\s,;:.\u2014\-]+$', '', s)
    s = s.strip()
    return s

def _leading_name(text):
    # Pull the leading run of Capitalized / ALL-CAPS words (an artist name)
    # up to the first lowercase word (usually the verb).
    tokens = text.split()
    name = []
    connectors = {'&', 'x', '+', 'and', 'feat.', 'feat', 'ft.', 'ft'}
    for t in tokens:
        bare = t.strip('\u201c\u201d"\'.,')
        if not bare:
            break
        if t.lower() in connectors:
            name.append('&' if t.lower() in {'&', 'and'} else t)
            continue
        # Capitalized word, ALL-CAPS, or a name with apostrophe-s
        if bare[0].isupper():
            name.append(t)
        else:
            break
    return ' '.join(name).strip()

def clean_artist(artist, song=''):
    a = (artist or '').strip()
    # If the whole sentence got captured, cut it at the first action verb
    m = re.match(r'^(.+?)\s+(?:' + VERBS + r')\b', a, re.IGNORECASE)
    if m:
        a = m.group(1).strip()
    # A quoted song leaked in: '"Song" by Artist' -> keep what follows "by"
    if re.search(r'[\u201c\u201d"]', a) and re.search(r'\bby\b', a, re.IGNORECASE):
        mb = re.search(r'\bby\s+(.+)$', a, re.IGNORECASE)
        if mb:
            a = mb.group(1).strip()
    # 'With "Song," Artist ...' -> keep what follows the comma
    elif a.lower().startswith('with ') and ',' in a:
        a = a.split(',')[-1].strip()
    # Still sentence-like? Salvage the leading capitalized name run instead.
    if len(a.split()) > 6:
        salvaged = _leading_name(a)
        if salvaged and len(salvaged.split()) <= 6:
            a = salvaged
    a = re.sub(r'[\u2019\']s?\s*$', '', a).strip()
    a = re.sub(r'[,;:]+$', '', a).strip()
    a = a.strip('\u201c\u201d"\'').strip()
    if len(a.split()) > 6:
        return ''
    # A lone function word means we captured a sentence start, not a name
    if a.lower() in {'this', 'that', 'the', 'a', 'an', 'i', 'we', 'he', 'she',
                     'they', 'it', 'my', 'our', 'his', 'her', 'their', 'on'}:
        return ''
    return a

def clean_genre(genre):
    g = (genre or '').strip()
    if g.lower() in BAD_GENRES:
        return ''
    # Real genres are short; a long phrase is a mis-tagged title/sentence
    if len(g.split()) > 3:
        return ''
    return g


    if url in url_to_post:
        return False
    song = clean_song(song)
    artist = clean_artist(artist, song)
    genre = clean_genre(genre)
    if not artist or not song:
        print('  SKIPPED (no artist/song): ' + url)
        return False
    song_key = artist.lower() + '|' + song.lower()
    if song_key in song_to_post:
        print('  DUPLICATE SKIPPED: ' + artist + ' - ' + song)
        return False
    artwork, itunes_genre = fetch_meta(artist, song)
    # Earmilk had no real genre tag -> fall back to iTunes' genre
    if not genre and itunes_genre:
        genre = clean_genre(itunes_genre)
    new_post = {
        'artist': artist,
        'song': song,
        'genre': genre,
        'date': date,
        'sort_date': sort_date,
        'url': url,
        'artwork': artwork
    }
    existing_posts.append(new_post)
    url_to_post[url] = new_post
    song_to_post[song_key] = new_post
    print('ADDED: ' + artist + ' - ' + song)
    return True

def scrape_archive_page(url, url_to_post, song_to_post, existing_posts):
    try:
        html = fetch_url(url, timeout=15)
        article_urls = get_archive_urls(html)
        print('  Found ' + str(len(article_urls)) + ' URLs on ' + url)
        added = 0
        for art_url in article_urls:
            if art_url in url_to_post:
                continue
            try:
                art_html = fetch_url(art_url, timeout=10)
                title_match = re.search(r'<title>([^<]+?)\s*[–\-]\s*EARMILK', art_html)
                if not title_match:
                    continue
                headline = title_match.group(1).strip()
                date_match = re.search(r'"datePublished":"(\d{4}-\d{2}-\d{2})', art_html)
                sort_date = date_match.group(1).replace('-', '') if date_match else datetime.now().strftime('%Y') + '0101'
                try:
                    month_day = datetime.strptime(sort_date, '%Y%m%d').strftime('%b %-d')
                except Exception:
                    month_day = ''
                cat_matches = re.findall(r'rel="category[^"]*">([^<]+)<', art_html)
                genre = get_genre([c.strip() for c in cat_matches if c.strip()])
                artist, song = extract_artist_song(headline, art_html)
                print('  ARCHIVE: ' + repr(headline[:60]) + ' -> ' + repr(artist) + ' / ' + repr(song[:40]))
                if add_post(existing_posts, url_to_post, song_to_post, artist, song, genre, month_day, sort_date, art_url):
                    added += 1
                time.sleep(0.5)
            except Exception as e:
                print('  Article error: ' + str(e))
        return added
    except Exception as e:
        print('Archive error: ' + str(e))
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

        artist, song = parse_headline(headline)
        # If headline parse fails, fetch the article body
        if not artist or not song:
            try:
                art_html = fetch_url(link, timeout=10)
                artist, song = extract_artist_song(headline, art_html)
                time.sleep(0.5)
            except Exception:
                pass

        print('RSS: ' + repr(headline[:60]) + ' -> ' + repr(artist) + ' / ' + repr(song[:40]))
        if add_post(existing_posts, url_to_post, song_to_post, artist, song, genre, date, sort_date, link):
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

    print('Scraping archive pages...')
    for date_path in get_recent_archive_dates():
        archive_url = 'https://earmilk.com/' + date_path + '/'
        print('Checking: ' + archive_url)
        added = scrape_archive_page(archive_url, url_to_post, song_to_post, existing_posts)
        total_added += added
        time.sleep(1)

    existing_posts.sort(key=lambda p: p.get('sort_date') or '00000000', reverse=True)
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
