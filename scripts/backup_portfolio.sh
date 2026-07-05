#!/bin/bash
# Daily portfolio DB backup — WAL-safe (VACUUM INTO), 30-day rotation.
# Destination is inside ~/Documents which syncs to iCloud (Desktop & Documents
# sync), giving an off-machine copy without extra services.
set -u
DEST="$HOME/Documents/backup/valuescope"
SRC="/Users/Alan/valuescope/data"
mkdir -p "$DEST"
DAY=$(date +%Y%m%d)
for db in portfolio portfolio_child; do
  f="$SRC/$db.db"
  out="$DEST/$db-$DAY.db"
  [ -f "$f" ] || continue
  [ -f "$out" ] && continue
  /usr/bin/sqlite3 "$f" "VACUUM INTO '$out'" || echo "backup failed: $db"
done
find "$DEST" -name '*.db' -mtime +30 -delete
echo "$(date '+%F %T') portfolio backup done -> $DEST"
