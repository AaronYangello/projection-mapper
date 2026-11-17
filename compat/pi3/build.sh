#!/bin/sh
set -eu
cd "$(dirname "$0")"
export TMPDIR="$PWD"
cc -std=c99 -O2 -Wall -Wextra -Werror -I/opt/vc/include renderer.c \
  -L/opt/vc/lib -Wl,-rpath,/opt/vc/lib -lbrcmEGL -lbrcmGLESv2 -lbcm_host \
  -l:libasound.so.2 -lz -lm -o renderer
