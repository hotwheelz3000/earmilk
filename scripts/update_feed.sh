#!/bin/bash
# Hourly local feed update, run by launchd (see scripts/com.earmilk.feed.plist).
# Runs fetch.py and commits/pushes posts.json to main if it changed.
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:/usr/local/bin:/usr/bin:/bin"
export GIT_TERMINAL_PROMPT=0
cd "$(dirname "$0")/.." || exit 1

echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') ==="

git checkout -q main || exit 1
if ! git pull -q --rebase --autostash origin main; then
    echo "git pull failed; skipping this run"
    git rebase --abort 2>/dev/null
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
if [ -n "$(git log origin/main..main --oneline)" ]; then
    git push -q origin main && echo "pushed" || { echo "git push failed"; exit 1; }
fi
