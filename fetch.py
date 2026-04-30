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

def fetch_artwork(artist, song):
    try:
        q = urllib.parse.quote((artist + " " + song).strip())
        url = "https://itunes.apple.com/search?term={}&media=music&limit=1".format(q)
        data = json.loads(fetch_url(url))
        if data.get("results"):
            art = data["results"][0].get("artworkUrl100", "")
            if art:
                return art.replace("100x100bb", "400x400bb")
    except Exception as e:
        print("  artwork error: {}".format(e))
    time.sleep(0.4)
    return ""

VERBS = (
    r'shares?|releases?|drops?|returns?|delivers?|unveils?|presents?|'
    r'launches?|announces?|debuts?|steps|marks|dives|channels|hosts|'
    r'explores?|reveals?|offers?|brings?|gives?|puts?\s+out|'
    r'links?\s+up|teams?\s+up|gets?|makes?|takes?|shows?'
)

def extract_artist_song(headline):
    # Extract artist: everything before the first verb
    artist = ""
    artist_match = re.match(r'^(.+?)\s+(?:' + VERBS + r')\b', headline, re.IGNORECASE)
    if artist_match:
        artist = re.sub(r"'s?\s*$", "", artist_match.group(1)).strip()
        artist = re.sub(r'[,;:]+$', '', artist).strip()

    # Extract song: quoted strings longer than 2 chars
    quoted = re.findall(r'[\u201c\u2018"]([^"\u201d\u2019]{3,60})[\u201d\u2019"]', headline)
    # Also try regular quotes
    if not quoted:
        quoted = re.findall(r'"([^"]{3,60})"', headline)

    song = quoted[-1].strip() if quoted else ""

    if artist and song:
        return artist, song

    # Fall back: if we got artist but no song, or vice versa, skip this post
    return "", ""

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
    # Load existing posts to preserve clean data and cached artwork
    try:
        with open("posts.json") as f:
            existing = json.load(f)
        existing_posts = existing.get("posts", [])
        # Build lookup by URL to avoid duplicates
        url_map = {p["url"]: p for p in existing_posts}
        art_cache = {
            p.get("artist","") + "|" + p.get("song",""): p.get("artwork","")
            for p in existing_posts
        }
    except Exception:
        url_map = {}
        art_cache = {}

    print("Fetching RSS feed...")
    xml = fetch_feed()
    root = ET.fromstring(xml)

    new_posts = []
    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el  = item.find("link")
        pub_el   = item.find("pubDate")
        cats     = [c.text.strip() for c in item.findall("category") if c.text]

        headline = title_el.text.strip() if title_el is not None and title_el.text else ""
        link     = link_el.text.strip()  if link_el  is not None and link_el.text  else "#"
        date     = parse_date(pub_el.text.strip() if pub_el is not None and pub_el.text else "")
        genre    = get_genre(cats)

        # If we already have a clean version of this post, keep it
        if link in url_map:
            existing_post = url_map[link]
            # Just update artwork if missing
            if not existing_post.get("artwork"):
                a = existing_post.get("artist","")
                s = existing_post.get("song","")
                if a and s:
                    existing_post["artwork"] = fetch_artwork(a, s)
            new_posts.append(existing_post)
            print("  KEPT: {} - {}".format(url_map[link].get("artist","?"), url_map[link].get("song","?")))
            continue

        # New post — try to parse artist/song from headline
        artist, song = extract_artist_song(headline)
        print("  NEW: {!r} -> artist={!r} song={!r}".format(headline, artist, song))

        if not artist or not song:
            # Skip posts we can't cleanly parse
            print("  -> SKIPPED (could not parse)")
            continue

        cache_key = artist + "|" + song
        if cache_key in art_cache and art_cache[cache_key]:
            artwork = art_cache[cache_key]
        else:
            artwork = fetch_artwork(artist, song)
            print("  -> artwork: {}".format(artwork[:60] if artwork else "none"))

        new_posts.append({
            "artist":  artist,
            "song":    song,
            "genre":   genre,
            "date":    date,
            "url":     link,
            "artwork": artwork
        })

    out = {
        "updated": datetime.utcnow().strftime("%b %-d, %Y"),
        "posts": new_posts
    }

    with open("posts.json", "w") as f:
        json.dump(out, f, indent=2)

    print("Done. Wrote {} posts.".format(len(new_posts)))

if __name__ == "__main__":
    main()
