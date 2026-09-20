#!/bin/sh
# Provision optional pure-Python dependencies in persistent package-local storage.
# aiohttp, requests, dbus and GLib come from Venus; no system package is replaced.
set -eu
python3 -c 'import aiohttp, requests, dbus; from gi.repository import GLib'
python3 -m pip install --disable-pip-version-check --no-deps --only-binary=:all: \
    --target /data/setupOptions/dbus-ev/python \
    'protobuf==6.33.6' 'paho-mqtt==2.1.0'
