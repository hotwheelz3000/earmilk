import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import re
import time
from datetime import datetime

FEED_URL = "https://earmilk.com/feed"

def fetch_url(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")

def fetch_feed():
    return fetch_url(FEED_URL, timeout=15)

def fetch_artwork(search_term):
    try:
        encoded = urllib.parse.quote(search_term.strip())
        url = "https://itunes.apple.com/search?term={}&media=music&limit=1".format(encoded)
        data = json.loads(fetch_url(url))
        if data.get("results"):
            art = data["results"][0].get("artworkUrl100", "")
            if art:
                return art.replace("100x100bb", "400x400bb")
    except Exception as e:
        print("  artwork error: {}".format(e))
    time.sleep(0.4)
    return ""

def extract_artist_song(headline):
    """
    Parse Earmilk blog headlines like:
    - 'Max Nemo shares powerful new album "Nexus"'
    - 'Jill Scott returns with new single "Beautiful People"'
    - 'Haunted Images releases new single "I\'ll Come Around"'
    - 'CAPYAC & Lando Chill deliver groove on "Rye Bread"'
    Returns (artist, song) or ("", headline) if no match.
    """
    # Match quoted song title (smart quotes or regular)
    song_match = re.search(r'[\u201c\u2018"\'](.+?)[\u201d\u2019"\']', headline)
    song = song_match.group(1).strip() if song_match else ""

    # Artist is typically everything before the first verb word
    # Common patterns: "Artist shares/releases/drops/returns with/delivers"
    artist_match = re.match(
        r'^(.+?)\s+(?:shares?|releases?|drops?|returns?|delivers?|unveils?|presents?|launches?|announces?|debuts?|steps|marks|dives|channels|hosts|steps)\b',
        headline, re.IGNORECASE
    )
    artist = artist_match.group(1).strip() if artist_match else ""

    # Clean up artist — remove trailing punctuation
    artist = re.sub(r'[,;]+$', '', artist).strip()

    if artist and song:
        return artist, song
    return "", headline

def parse_date(date_str):
    try:
        dt = datetime.strptime(date_str[:25], "%a, %d %b %Y %H:%M:%S")
        return dt.strftime("%b %-d")
    except Exception:
        return date_str[:10] if date_str else ""

def get_genre(categories):
    skip = {"new music", "music", "news", "featured", "mainstage", "music videos"}
    for c in categories:
        if c.lower() not in skip:
            return c
    return categories[0] if categories else ""

def main():
    # Load existing posts to reuse cached artwork
    try:
        with open("posts.json") as f:
            existing = json.load(f)
        art_cache = {
            (p.get("artist","") + "|" + p.get("song","")): p.get("artwork","")
            for p in existing.get("posts", [])
        }
    except Exception:
        art_cache = {}

    print("Fetching RSS feed...")
    xml = fetch_feed()
    root = ET.fromstring(xml)

    posts = []
    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el  = item.find("link")
        pub_el   = item.find("pubDate")
        cats     = [c.text.strip() for c in item.findall("category") if c.text]

        headline = title_el.text.strip() if title_el is not None and title_el.text else ""
        link     = link_el.text.strip()  if link_el  is not None and link_el.text  else "#"
        date     = parse_date(pub_el.text.strip() if pub_el is not None and pub_el.text else "")
        genre    = get_genre(cats)
        artist, song = extract_artist_song(headline)

        print("  HEADLINE: {}".format(headline))
        print("  -> artist={!r} song={!r}".format(artist, song))

        cache_key = artist + "|" + song
        if cache_key in art_cache and art_cache[cache_key]:
            artwork = art_cache[cache_key]
            print("  -> artwork: cached")
        else:
            search = (artist + " " + song).strip() if artist else song
            artwork = fetch_artwork(search)
            print("  -> artwork: {}".format(artwork[:80] if artwork else "none"))

        posts.append({
            "artist":  artist,
            "song":    song,
            "genre":   genre,
            "date":    date,
            "url":     link,
            "artwork": artwork
        })

    out = {
        "updated": datetime.utcnow().strftime("%b %-d, %Y"),
        "posts": posts
    }

    with open("posts.json", "w") as f:
        json.dump(out, f, indent=2)

    print("Done. Wrote {} posts.".format(len(posts)))

if __name__ == "__main__":
    main()
