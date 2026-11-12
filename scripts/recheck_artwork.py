#!/usr/bin/env python3
"""Recheck posts' cover art with the strict matching and all artwork sources.

    python3 scripts/recheck_artwork.py            # every post
    python3 scripts/recheck_artwork.py --missing  # only posts with no cover

    --no-article  skip the Earmilk article image (earmilk.com blocks GitHub's
                  servers); posts with no catalog match are left unchanged
    --no-push     don't run scripts/update_feed.sh; the caller commits posts.json
                  (used by .github/workflows/backfill-artwork.yml)

Older runs of fetch.py could give a post another song's cover (it took the first
iTunes result when the artist didn't match). This looks every post up again with
the new rule (artist AND title must match):

  - match found on iTunes, Deezer or MusicBrainz -> that cover
  - otherwise the Earmilk article's own image
  - nothing matches                       -> no cover (marked no_artwork so the
                                             hourly job doesn't keep retrying)
  - the lookup failed (network/rate limit) -> post left as it is

Apple allows about 20 searches a minute, so this runs slowly (roughly an hour
for ~800 posts). Progress is saved to recheck-progress.json, so if it stops you
can run it again and it carries on. posts.json is only changed at the end, then
scripts/update_feed.sh commits and pushes it like the hourly job does.

Run on the iMac:
    cd ~/earmilk && git pull && caffeinate -i python3 scripts/recheck_artwork.py --missing
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import fetch  # noqa: E402  (fetch.py in the repo root; importing it runs nothing)

PROGRESS = os.path.join(ROOT, 'recheck-progress.json')
fetch.ITUNES_DELAY = 3.2  # stay under Apple's ~20 searches/minute


def load_progress():
    try:
        with open(PROGRESS) as f:
            return json.load(f)
    except Exception:
        return {}


def save_progress(progress):
    tmp = PROGRESS + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(progress, f, indent=1)
    os.replace(tmp, PROGRESS)


def main():
    with open('posts.json') as f:
        posts = json.load(f).get('posts', [])
    progress = load_progress()  # url -> {"artwork": "..."} for posts already checked
    args = sys.argv[1:]
    missing_only = '--missing' in args
    no_article = '--no-article' in args
    no_push = '--no-push' in args
    if no_article:
        fetch.article_image = lambda url: ''
    todo = [p for p in posts if p.get('url') and p['url'] not in progress
            and p.get('artist') and p.get('song')
            and (not missing_only or not p.get('artwork'))]
    print(f'{len(posts)} posts, {len(progress)} already checked, {len(todo)} to go')

    for i, p in enumerate(todo, 1):
        errors_before = fetch.ITUNES_ERRORS
        art = fetch.fetch_artwork(p['artist'], p['song'], p['url'])
        if not art and fetch.ITUNES_ERRORS > errors_before:
            # Couldn't ask Apple (often a rate limit): wait, and leave this post for a later run.
            print(f'[{i}/{len(todo)}] lookup failed, skipping for now: {p["artist"]} - {p["song"]}')
            time.sleep(60)
            continue
        if not art and no_article:
            # Only the article image could help; leave this post for the app/Mac job.
            print(f'[{i}/{len(todo)}] no catalog match, unchanged: {p["artist"]} - {p["song"]}')
            continue
        old = p.get('artwork', '')
        status = 'same' if art == old else ('NEW COVER' if art else 'REMOVED (no match)')
        print(f'[{i}/{len(todo)}] {status}: {p["artist"]} - {p["song"]}')
        progress[p['url']] = {'artwork': art}
        save_progress(progress)

    # Apply the results to a fresh copy of posts.json (the hourly job may have
    # added posts while this ran) and write it the same way fetch.py does.
    with open('posts.json') as f:
        current = json.load(f).get('posts', [])
    changed = 0
    for p in current:
        result = progress.get(p.get('url'))
        if result is None:
            continue
        art = result['artwork']
        if art:
            if p.get('artwork') != art or p.get('no_artwork'):
                changed += 1
            p['artwork'] = art
            p.pop('no_artwork', None)
        else:
            if p.get('artwork') or not p.get('no_artwork'):
                changed += 1
            p['artwork'] = ''
            p['no_artwork'] = True
    fetch.write_posts(current)

    left = sum(1 for p in current if p.get('url') and p['url'] not in progress
               and p.get('artist') and p.get('song')
               and (not missing_only or not p.get('artwork')))
    print(f'Done: {changed} posts changed. {left} still unchecked'
          + (' (run this again to finish them).' if left else '.'))

    if no_push:
        if os.path.exists(PROGRESS):
            os.remove(PROGRESS)
        return
    print('Committing and pushing posts.json with scripts/update_feed.sh...')
    result = subprocess.run(['bash', 'scripts/update_feed.sh'])
    if result.returncode == 0 and not left:
        os.remove(PROGRESS)
        print('All done.')
    sys.exit(result.returncode)


if __name__ == '__main__':
    main()
