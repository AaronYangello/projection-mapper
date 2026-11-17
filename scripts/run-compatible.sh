#!/bin/sh
set -eu
repo=$(CDPATH='' cd "$(dirname "$0")/.." && pwd)
native="$repo/compat/pi3"
if [ "$(uname -s)" = Linux ] && [ "$(getconf LONG_BIT)" = 32 ] &&
   [ -r /opt/vc/lib/libbrcmEGL.so ] && [ -r /dev/vchiq ]; then
    if [ ! -x "$native/renderer" ] || [ "$native/renderer.c" -nt "$native/renderer" ]; then
        sh "$native/build.sh"
    fi
    exec python3 "$native/appliance.py" "$@"
fi
exec "$repo/.venv/bin/projection-show" run "$@"
