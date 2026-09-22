#!/bin/sh
# Build on a workstation/CI, not the GX. Go verifies the pinned module checksums.
# Example: GOOS=linux GOARCH=arm GOARM=7 sh scripts/build-vehicle-engine.sh /tmp/vehicle-engine
set -eu
root=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
output=${1:?Supply an absolute destination for the optional vehicle-engine binary}
case "$output" in /*) ;; *) echo 'Destination must be absolute' >&2; exit 2 ;; esac
cd "$root/vehicle-engine"
CGO_ENABLED=0 python3 build.py build -trimpath -ldflags='-s -w' -o "$output" .
