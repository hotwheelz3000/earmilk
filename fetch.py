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

def fetch_artwork(artist, song, title):
    # Try artist+song first, fall back to full title
    queries = []
    if artist and song:
        queries.append(artist + " " + song)
    queries.append(title)

    for q in queries:
        try:
            encoded = urllib.parse.quote(q.strip())
            url = "https://itunes.apple.com/search?term={}&media=music&limit=1".format(encoded)
            data = json.loads(fetch_url(url))
            if data.get("results"):
                art = data["results"][0].get("artworkUrl100", "")
                if art:
                    return art.replace("100x100bb", "400x400bb")
        except Exception as e:
            print("  artwork fetch failed for {!r}: {}".format(q, e))
        time.sleep(0.5)
    return ""

def parse_title(title):
    # "Artist - Song" or "Artist - "Song""
    dash = re.match(r'^(.+?)\s*\u2013\s*[\u201c"]?(.+?)[\u201d"]?\s*$', title)
    if not dash:
        dash = re.match(r'^(.+?)\s+-\s+[\u201c"]?(.+?)[\u201d"]?\s*$', title)
    if dash:
        return dash.group(1).strip(), dash.group(2).strip()
    # "Song" by Artist
    by = re.match(r'^[\u201c"]?(.+?)[\u201d"]?\s+by\s+(.+)$', title, re.IGNORECASE)
    if by:
        return by.group(2).strip(), by.group(1).strip()
    return "", title

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

        title  = title_el.text.strip() if title_el is not None and title_el.text else ""
        link   = link_el.text.strip()  if link_el  is not None and link_el.text  else "#"
        date   = parse_date(pub_el.text.strip() if pub_el is not None and pub_el.text else "")
        genre  = get_genre(cats)
        artist, song = parse_title(title)

        print("  {} | {} | {}".format(artist, song, title))

        cache_key = artist + "|" + song
        if cache_key in art_cache and art_cache[cache_key]:
            artwork = art_cache[cache_key]
            print("    -> cached artwork")
        else:
            artwork = fetch_artwork(artist, song, title)
            print("    -> artwork: {}".format(artwork[:60] if artwork else "none"))

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

    print("Wrote {} posts to posts.json".format(len(posts)))

if __name__ == "__main__":
    main()
