#!/bin/sh
# Install (or reinstall) the scheduled United page update for this user.
# Remove with: launchctl bootout gui/$(id -u)/com.corridor.united-update && rm ~/Library/LaunchAgents/com.corridor.united-update.plist
set -eu
REPO=$(cd "$(dirname "$0")/../.." && pwd)
UV=$(command -v uv)
DEST="$HOME/Library/LaunchAgents/com.corridor.united-update.plist"
mkdir -p "$REPO/data/logs" "$HOME/Library/LaunchAgents"
sed -e "s#__UV__#$UV#g" -e "s#__REPO__#$REPO#g" -e "s#__HOME__#$HOME#g" \
  "$REPO/ops/launchd/com.corridor.united-update.plist" > "$DEST"
plutil -lint "$DEST"
launchctl bootout "gui/$(id -u)/com.corridor.united-update" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "installed: $DEST (runs 10:31 and 14:31)"
