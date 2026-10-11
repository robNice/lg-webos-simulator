#!/bin/sh
# Container start: runs as root only to prepare the mapped directories, then drops to PUID:PGID
# (default 10001). The simulator itself never runs as root.
set -eu

if [ "$(id -u)" != "0" ]; then
    exec "$@"    # started with "user:" in compose: nothing to prepare
fi

PUID="${PUID:-10001}"
PGID="${PGID:-10001}"
case "$PUID:$PGID" in
    *[!0-9:]* | :* | *:) echo "PUID and PGID must be numeric" >&2; exit 2 ;;
esac
if [ "$PUID" = "0" ] || [ "$PGID" = "0" ]; then
    echo "refusing to run the simulator as root (PUID/PGID 0)" >&2
    exit 2
fi

config_dir="$(dirname "${LG_TV_SIM_CONFIG:-/config/simulator.toml}")"
mkdir -p /app/.simulator "$config_dir"
# Data volume belongs to the simulator completely; the config directory only at its top level.
if [ "$(stat -c %u:%g /app/.simulator)" != "$PUID:$PGID" ]; then
    chown -R "$PUID:$PGID" /app/.simulator
fi
if [ "$(stat -c %u:%g "$config_dir")" != "$PUID:$PGID" ]; then
    chown "$PUID:$PGID" "$config_dir"
fi

exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups "$@"
