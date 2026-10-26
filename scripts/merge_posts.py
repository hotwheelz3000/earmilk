#!/usr/bin/env python3
"""Git merge driver for posts.json: keeps every post from both sides.

Both the Mac launchd job (scripts/update_feed.sh) and the Shortcut workflow
(.github/workflows/feed-from-shortcut.yml) rewrite posts.json, always touching
the same lines ("updated" and new posts at the top), so git's line merge
conflicts. This merges by post URL instead:

  - every post on either side is kept (matched by URL + artist + song; a few
    old posts share a URL like https://earmilk.com/music/)
  - a post on both sides keeps our copy, with empty fields filled from theirs
    (e.g. artwork one side backfilled)
  - artist+song duplicates are dropped, as fetch.py's add_post does
  - sorted newest first, as fetch.py writes it
  - "updated" is the later of the two times

Registered via .gitattributes (posts.json merge=posts-union) and enabled per
command with:
  git -c merge.posts-union.driver='python3 scripts/merge_posts.py %O %A %B' ...
Usage: merge_posts.py BASE OURS THEIRS  (result is written to OURS)
"""
import json
import sys
from datetime import datetime


def load(path):
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def updated_time(s):
    try:
        return datetime.strptime((s or '').replace(' PT', ''), '%b %d, %Y %I:%M %p')
    except Exception:
        return datetime.min


def merge(ours, theirs):
    posts, by_id = [], {}
    for side in (ours.get('posts', []), theirs.get('posts', [])):
        for p in side:
            if not isinstance(p, dict):
                continue
            pid = (p.get('url') or '', (p.get('artist') or '').lower(), (p.get('song') or '').lower())
            if pid in by_id:
                kept = by_id[pid]
                for k, v in p.items():
                    if v and not kept.get(k):
                        kept[k] = v
                continue
            p = dict(p)
            posts.append(p)
            by_id[pid] = p

    seen, unique = set(), []
    for p in posts:
        key = (p.get('artist') or '').lower() + '|' + (p.get('song') or '').lower()
        if key != '|' and key in seen:
            continue
        seen.add(key)
        unique.append(p)
    unique.sort(key=lambda p: p.get('sort_date') or '00000000', reverse=True)

    updated = max(ours.get('updated'), theirs.get('updated'), key=updated_time)
    return {'updated': updated or ours.get('updated') or theirs.get('updated'), 'posts': unique}


def main():
    if len(sys.argv) != 4:
        sys.exit('usage: merge_posts.py BASE OURS THEIRS')
    _, ours_path, theirs_path = sys.argv[1:]
    ours, theirs = load(ours_path), load(theirs_path)
    if not ours.get('posts') and not theirs.get('posts'):
        sys.exit(1)  # nothing parseable: let git report a conflict
    with open(ours_path, 'w') as f:
        json.dump(merge(ours, theirs), f, indent=2)


if __name__ == '__main__':
    main()
