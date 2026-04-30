import urllib.request
import xml.etree.ElementTree as ET
import json
import re
from datetime import datetime

FEED_URL = "https://earmilk.com/feed"

def fetch_feed():
    req = urllib.request.Request(
        FEED_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; EarmilkBot/1.0)"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")

def parse_title(title):
    # Try "Artist - Song" pattern
    dash = re.match(r'^(.+?)\s*[-]\s*["\u201c]?(.+?)["\u201d]?\s*$', title)
    if dash:
        return dash.group(1).strip(), dash.group(2).strip()
    # Try "Song by Artist"
    by = re.match(r'^["\u201c]?(.+?)["\u201d]?\s+by\s+(.+)$', title, re.IGNORECASE)
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
    xml = fetch_feed()
    root = ET.fromstring(xml)
    ns = {"content": "http://purl.org/rss/1.0/modules/content/"}

    posts = []
    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pub_el = item.find("pubDate")
        cats = [c.text.strip() for c in item.findall("category") if c.text]

        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        link = link_el.text.strip() if link_el is not None and link_el.text else "#"
        date = parse_date(pub_el.text.strip() if pub_el is not None and pub_el.text else "")
        genre = get_genre(cats)
        artist, song = parse_title(title)

        posts.append({
            "artist": artist,
            "song": song,
            "genre": genre,
            "date": date,
            "url": link
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
