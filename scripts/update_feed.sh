#!/bin/bash
# Hourly local feed update, run by launchd (see scripts/com.earmilk.feed.plist).
# Runs fetch.py and commits/pushes posts.json to main if it changed.
#
# The Shortcut workflow (.github/workflows/feed-from-shortcut.yml) also pushes
# posts.json, so pulls rebase with scripts/merge_posts.py merging posts.json
# post-by-post (no conflicts, no lost posts), and a rejected push is retried
# after pulling again.
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:/usr/local/bin:/usr/bin:/bin"
export GIT_TERMINAL_PROMPT=0
cd "$(dirname "$0")/.." || exit 1

MERGE_DRIVER="merge.posts-union.driver=python3 scripts/merge_posts.py %O %A %B"

pull() {
    if git -c "$MERGE_DRIVER" pull -q --rebase --autostash origin main; then
        return 0
    fi
    git rebase --abort 2>/dev/null
    return 1
}

echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') ==="

git checkout -q main || exit 1
if ! pull; then
    echo "git pull failed; skipping this run"
    exit 1
fi

if ! python3 fetch.py; then
    echo "fetch.py failed; nothing committed"
    git checkout -q -- posts.json
    exit 1
fi

if ! git diff --quiet -- posts.json; then
    git add posts.json
    git -c user.name="earmilk-feed (launchd)" \
        -c user.email="hotwheelz3000@users.noreply.github.com" \
        commit -q -m "chore: update feed $(date +'%Y-%m-%d %H:%M %Z')"
    echo "committed posts.json"
fi

# Push anything unpushed, including commits left over from earlier failed pushes.
# If the Shortcut workflow pushed first, pull (merging posts.json) and retry.
for attempt in 1 2 3 4 5; do
    if [ -z "$(git log origin/main..main --oneline)" ]; then
        exit 0
    fi
    if git push -q origin main; then
        echo "pushed"
        exit 0
    fi
    echo "git push failed (attempt $attempt); pulling and retrying"
    sleep $((attempt * 5))
    if ! pull; then
        echo "git pull failed; will retry next run"
        exit 1
    fi
done
echo "git push failed after 5 attempts"
exit 1
