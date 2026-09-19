#!/usr/bin/env bash
# Start the native Pi output as an Openbox-managed, maximized window.
set -euo pipefail

root_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
project_path=${PROJECTION_SHOW_PROJECT:-"$root_dir/projects/installation/project.yaml"}
data_root=${PROJECTION_SHOW_DATA_ROOT:-"$root_dir/appliance-data"}
host=${PROJECTION_SHOW_HOST:-127.0.0.1}
title="Projection Show · Native Output"

if command -v wmctrl >/dev/null 2>&1; then
    (
        # Openbox registers the GLFW client shortly after its first frame.
        sleep 2
        for _ in {1..16}; do
            if wmctrl -r "$title" -b add,maximized_vert,maximized_horz 2>/dev/null; then
                wmctrl -a "$title" 2>/dev/null || true
                exit 0
            fi
            sleep 0.25
        done
    ) &
fi

exec "$root_dir/.venv/bin/projection-show" run \
    --project "$project_path" \
    --role appliance \
    --data-root "$data_root" \
    --graphics-backend gles \
    --windowed \
    --host "$host"
