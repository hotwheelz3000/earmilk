import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import re
import time
from datetime import datetime, timezone, timedelta

FEED_URL = "https://earmilk.com/feed"

def fetch_url(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")

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
    artist_match = re.match(r'^(.+?)\s+(?:' + VERBS + r')\b', headline, re.IGNORECASE)
    artist = ""
    if artist_match:
        artist = re.sub(r"'s?\s*$", "", artist_match.group(1)).strip()
        artist = re.sub(r'[,;:]+$', '', artist).strip()
    quoted = re.findall(r'[\u201c\u2018"]([^"\u201d\u2019]{3,60})[\u201d\u2019"]', headline)
    if not quoted:
        quoted = re.findall(r'"([^"]{3,60})"', headline)
    song = quoted[-1].strip() if quoted else ""
    if artist and song:
        return artist, song
    return "", ""

def parse_date(date_str):
    try:
        dt = datetime.strptime(date_str[:25], "%a, %d %b %Y %H:%M:%S")
        return dt.strftime("%b %-d")
    except Exception:
        return date_str[:10] if date_str else ""

def parse_sort_date(date_str):
    try:
        dt = datetime.strptime(date_str[:25], "%a, %d %b %Y %H:%M:%S")
        return dt.strftime("%Y%m%d")
    except Exception:
        return "20260101"

def display_to_sort(display_date):
    try:
        dt = datetime.strptime(display_date + " 2026", "%b %d %Y")
        return dt.strftime("%Y%m%d")
    except Exception:
        return "20260101"

def get_genre(categories):
    skip = {"new music", "music", "news", "featured", "mainstage", "music videos"}
    for c in categories:
        if c.lower() not in skip:
            return c
    return categories[0] if categories else ""

def main():
    try:
        with open("posts.json")
