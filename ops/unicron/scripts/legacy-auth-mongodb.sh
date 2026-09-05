#!/bin/sh
set -eu

state_dir=/migration
mkdir -p "$state_dir"
chown 1000:1000 "$state_dir"
chmod 700 "$state_dir"
rm -f "$state_dir/source-state"

state=empty
if [ -s "$state_dir/completed" ]; then
  state=completed
else
  # Ignore an empty Docker volume, but never initialize over unrecognized old data.
  for entry in /data/db/* /data/db/.[!.]* /data/db/..?*; do
    [ -e "$entry" ] || continue
    [ "$(basename "$entry")" = lost+found ] && continue
    state=required
    break
  done
fi
printf '%s\n' "$state" > "$state_dir/source-state.tmp"
chmod 644 "$state_dir/source-state.tmp"
mv "$state_dir/source-state.tmp" "$state_dir/source-state"

if [ "$state" = required ]; then
  # This is an existing database. Do not let the upstream entrypoint initialize a new one.
  if [ ! -f /data/db/WiredTiger ] && [ ! -f /data/db/storage.bson ]; then
    echo 'Unrecognized legacy auth data; refusing to start a new MongoDB database.' >&2
    exit 1
  fi
  exec /usr/local/bin/docker-entrypoint.sh mongod --auth --bind_ip_all
fi

# Keep the dependency healthy without invoking MongoDB on fresh or migrated installs.
exec sleep infinity
