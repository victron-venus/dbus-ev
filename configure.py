#!/usr/bin/env python3
"""Persist installer options in SetupHelper's package options directory."""

import argparse
import json
import os
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ha-mqtt", choices=("on", "off"))
    parser.add_argument("--source", choices=("ha", "mercedes", "evcc"))
    parser.add_argument("--options-file", default="/data/setupOptions/dbus-ev/options.json")
    args = parser.parse_args()
    if args.ha_mqtt is None and args.source is None:
        parser.error("at least one of --ha-mqtt or --source is required")
    path = Path(args.options_file)
    # The local installer explicitly selects this file; no network data selects a path.
    options = {}
    if path.exists():
        saved = path.read_text(encoding="utf-8")  # NOSONAR(S8707)
        options = json.loads(saved)
    if args.ha_mqtt is not None:
        options["HA_MQTT_ENABLED"] = args.ha_mqtt == "on"
    if args.source is not None:
        options["DATA_SOURCE"] = args.source
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".options-", dir=path.parent)
    try:
        # mkstemp created this descriptor in the operator-selected options directory.
        with os.fdopen(fd, "w", encoding="utf-8") as stream:  # NOSONAR(S8707)
            json.dump(options, stream)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("Installer options saved")


if __name__ == "__main__":
    main()
