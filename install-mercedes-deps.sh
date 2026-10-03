#!/bin/sh
# Provision optional pure-Python dependencies in persistent package-local storage.
# aiohttp, requests, dbus and GLib come from Venus; no system package is replaced.
set -eu
SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
python3 -c 'import aiohttp, requests, dbus; from gi.repository import GLib'
python3 -m pip install --disable-pip-version-check --no-deps --only-binary=:all: --require-hashes \
    --target /data/setupOptions/dbus-ev/python \
    -r "${SCRIPT_DIR}/requirements-mercedes.txt"
